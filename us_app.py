import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import openai
import math

st.set_page_config(page_title="🇺🇸 Moat Hunter (Strategic)", layout="wide")
st.title("🇺🇸 Moat Hunter (2026 戰略佈局版)")
st.markdown("### 策略：PLTR 商業大腦 + GOOGL 價值回歸 + IPO 埋伏")

# --- 1. 戰略日曆 (使用者指定 + FOMC) ---
# Anduril 因為還沒上市，無法抓股價，所以放在這裡做文字提醒
STRATEGIC_CALENDAR = [
    {"日期": "2026-02-02", "事件": "📊 PLTR 財報", "重點": "營收年增70%，商業增長137% (已驗證)"},
    {"日期": "2026-03-18", "事件": "🏛️ FOMC 會議", "重點": "利率決策 + SEP 經濟預測"},
    {"日期": "2026-04-29", "事件": "🏛️ FOMC 會議", "重點": "常規會議"},
    {"日期": "2026-06-17", "事件": "🏛️ FOMC 會議", "重點": "年中重點會議"},
    {"日期": "2026-H2",    "事件": "🦄 Anduril IPO", "重點": "目標估值450億，國防獨角獸 (資金預備)"},
]

# --- 2. 投資清單 ---
TREND_THEMES = {
    "🎯 2026 核心戰略": {
        "logic": "PLTR成長爆發 + GOOGL利空抄底 + 數據二線股",
        "tickers": ['PLTR', 'GOOGL', 'IOT', 'RXRX']
    },
    "⛓️ 核心供應鏈": {
        "logic": "半導體設備 (ASML/AMAT) 與 台積電",
        "tickers": ['ASML', 'AMAT', 'TSM', 'KLAC'] 
    },
    "🚀 強勁需求": {
        "logic": "AI 算力 (NVDA) 與 電力 (VST)",
        "tickers": ['NVDA', 'AVGO', 'VST', 'CEG'] 
    }
}

if 'watchlist_us' not in st.session_state: st.session_state.watchlist_us = ['PLTR', 'GOOGL'] 
if 'ai_response_us_conservative' not in st.session_state: st.session_state.ai_response_us_conservative = None
if 'ai_response_us_growth' not in st.session_state: st.session_state.ai_response_us_growth = None

# --- 側邊欄 ---
st.sidebar.header("🚀 設定")
api_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
selected_theme = st.sidebar.selectbox("投資主題:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控":
    new = st.sidebar.text_input("➕ 代號:").upper().strip()
    if st.sidebar.button("新增") and new: 
        if new not in st.session_state.watchlist_us: st.session_state.watchlist_us.append(new)
    target_tickers = st.session_state.watchlist_us
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]
    st.sidebar.info(f"💡 {TREND_THEMES[selected_theme]['logic']}")

# --- 核心函式 ---
@st.cache_data(ttl=300)
def get_us_macro():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        tnx = yf.Ticker("^TNX").history(period="5d")['Close'].iloc[-1]
        fed = yf.Ticker("ZQ=F").history(period="5d")
        rate = 100 - fed['Close'].iloc[-1] if not fed.empty else 0
        return {"vix": vix, "tnx": tnx, "rate": rate}
    except: return {"vix": 20, "tnx": 4.0, "rate": 0}

def ask_ai(api_key, persona, macro, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(5)[['代號','現價','毛利率','PEG','評分原因']].to_dict('records')
        
        if persona == "conservative":
            sys_msg = "你是巴菲特風格的價值投資者。你關注 GOOGL 的利空是否創造了安全邊際。"
            user_msg = f"宏觀: 利率{macro['rate']:.1f}%, VIX {macro['vix']:.1f}。分析: {picks}。請特別點評 GOOGL 是否超跌？以及 PLTR 的高估值風險。"
        else:
            sys_msg = "你是凱薩琳伍德風格的成長型投資者。你對 PLTR 的商業大腦轉型感到興奮。"
            user_msg = f"宏觀: VIX {macro['vix']:.1f}。分析: {picks}。請分析 PLTR 轉型商業大腦的潛力，以及 Samsara(IOT) 和 Recursion(RXRX) 的數據規模效應。"

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system", "content": sys_msg}, {"role":"user", "content": user_msg}]
        )
        return res.choices[0].message.content
    except Exception as e: return f"AI 分析失敗: {str(e)}"

def score_us_stock(rsi, peg, margin, roe, change, macro):
    score = 50; det = []
    
    # 特殊個股邏輯
    # IOT (Samsara) 和 RXRX 通常虧損，看重營收成長與PEG，不看ROE
    
    if margin > 60: score += 20; det.append("🏰軟體級護城河") # PLTR/GOOGL 通常很高
    elif margin > 40: score += 10; det.append("💎高毛利")
    
    if roe > 20: score += 15; det.append("👑ROE優")
    
    if peg > 0 and peg < 1.5: score += 15; det.append("🚀PEG合理")
    elif peg > 3: score -= 5; det.append("⚠️高估值")
    
    if macro['vix'] > 30: score += 15; det.append("🩸恐慌買點")
    if rsi < 35: score += 15; det.append("📉超賣")
    if change < -3: score += 10; det.append("🔥大跌")
    
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    mac = get_us_macro()
    sl = []
    bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        try:
            s = yf.Ticker(t)
            h = s.history(period="1y")
            if h.empty: continue
            
            cur = h['Close'].iloc[-1]
            chg = ((cur-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100
            
            delta = h['Close'].diff()
            gain = (delta.where(delta>0, 0)).rolling(14).mean()
            loss = (-delta.where(delta<0, 0)).rolling(14).mean().replace(0, 0.001)
            rsi = 100 - (100/(1 + (gain/loss))).iloc[-1]
            
            info = s.info
            peg = info.get('pegRatio', 0)
            roe = (info.get('returnOnEquity', 0) or 0)*100
            margin = (info.get('grossMargins', 0) or 0) * 100
            
            sc, re = score_us_stock(rsi, peg, margin, roe, chg, mac)
            sl.append({
                "代號":t, 
                "現價":f"{cur:.2f}", 
                "毛利率":f"{margin:.1f}%", 
                "PEG":f"{peg:.2f}" if peg else "-", 
                "分數":int(sc), 
                "評分原因":re
            })
        except: pass
        bar.progress((i+1)/len(tickers))
        
    return pd.DataFrame(sl), mac

# --- UI ---
c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描 2026 戰略'):
    ds, mac = get_data(target_tickers)
    c1.metric("利率預期", f"{mac['rate']:.2f}%")
    c2.metric("VIX", f"{mac['vix']:.2f}")
    c3.metric("美債 10Y", f"{mac['tnx']:.2f}%")
    
    # 顯示戰略日曆
    st.markdown("### 🗓️ 關鍵戰略日曆 (Anduril IPO 監控)")
    cal_df = pd.DataFrame(STRATEGIC_CALENDAR)
    st.table(cal_df)

    if api_key:
        with st.spinner("🤖 雙人格 (巴菲特 vs 伍德) 分析中..."):
            st.session_state.ai_response_us_conservative = ask_ai(api_key, "conservative", mac, ds)
            st.session_state.ai_response_us_growth = ask_ai(api_key, "growth", mac, ds)
    
    if st.session_state.ai_response_us_conservative:
        st.write("### 🤖 觀點對決")
        t1, t2 = st.tabs(["🧐 巴菲特 (價值/GOOGL)", "✨ 伍德 (成長/PLTR)"])
        with t1: st.info(st.session_state.ai_response_us_conservative)
        with t2: st.success(st.session_state.ai_response_us_growth)

    def hi(v): return 'background-color: #1b5e20; color: white; font-weight: bold;' if v>=80 else 'background-color: #c8e6c9; color: black;' if v>=60 else ''
    st.subheader("🏢 掃描結果")
    if not ds.empty: st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(hi, subset=['分數']))
    else: st.warning("無數據")
