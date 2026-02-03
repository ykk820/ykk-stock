import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import openai
import math

st.set_page_config(page_title="🇺🇸 Moat Hunter (Pure)", layout="wide")
st.title("🇺🇸 Moat Hunter (美股極簡版)")
st.markdown("### 策略：巴菲特 vs 伍德 (單引擎雙人格)")

# --- 設定與清單 ---
CALENDAR_DATA = {
    "FOMC": [{"date": "2026-03-18"}, {"date": "2026-04-29"}, {"date": "2026-06-17"}]
}

TREND_THEMES = {
    "🔥 自選監控": [], 
    "📊 指數 ETF": {"tickers": ['VOO', 'QQQ', 'TLT', 'SMH']},
    "⚡️ AI 電力": {"tickers": ['CEG', 'VST', 'NEE', 'CCJ']},
    "🧠 AI 基建": {"tickers": ['NVDA', 'TSM', 'AVGO', 'MSFT', 'PLTR']},
    "🛒 抗衰退": {"tickers": ['COST', 'KO', 'PEP', 'MCD']}
}
KNOWN_ETFS = ['VOO', 'QQQ', 'SPY', 'TLT', 'SMH', 'SOXX', 'XLK', 'SCHD']

if 'watchlist_us' not in st.session_state: st.session_state.watchlist_us = ['VOO', 'NVDA'] 
if 'ai_response_us_conservative' not in st.session_state: st.session_state.ai_response_us_conservative = None
if 'ai_response_us_growth' not in st.session_state: st.session_state.ai_response_us_growth = None

# --- 側邊欄 ---
st.sidebar.header("🚀 設定")
api_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
selected_theme = st.sidebar.selectbox("板塊:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控":
    new = st.sidebar.text_input("➕ 代號:").upper().strip()
    if st.sidebar.button("新增") and new: 
        if new not in st.session_state.watchlist_us: st.session_state.watchlist_us.append(new)
    if st.session_state.watchlist_us:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_us)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_us.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_us
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]

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

def get_fomc():
    today = datetime.now().date()
    for m in CALENDAR_DATA["FOMC"]:
        d = datetime.strptime(m["date"], "%Y-%m-%d").date()
        if d >= today: return (d - today).days
    return 0

def calc_graham(info):
    try:
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        return math.sqrt(22.5 * eps * bvps) if eps > 0 and bvps > 0 else 0
    except: return 0

def ask_ai(api_key, persona, macro, days, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','葛拉漢價','評分原因']].to_dict('records')
        
        if persona == "conservative":
            sys_msg = "你是巴菲特風格的價值投資者。保守、看重安全邊際。"
            user_msg = f"宏觀: 利率{macro['rate']:.1f}%, VIX {macro['vix']:.1f}, FOMC剩{days}天。分析: {picks}。若價格高於葛拉漢價請警告風險。"
        else:
            sys_msg = "你是凱薩琳伍德風格的成長型投資者。看重破壞式創新、未來潛力。"
            user_msg = f"宏觀: 利率{macro['rate']:.1f}%, VIX {macro['vix']:.1f}。分析: {picks}。忽略短期估值，專注未來護城河與成長爆發力。"

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system", "content": sys_msg}, {"role":"user", "content": user_msg}]
        )
        return res.choices[0].message.content
    except Exception as e: return f"AI 分析失敗: {str(e)}"

def score_us_stock(rsi, peg, margin, roe, change, macro):
    score = 50; det = []
    if macro['vix']>30: score+=20; det.append("🩸恐慌")
    if margin>10: score+=20; det.append("🏰低估")
    if roe>15: score+=10; det.append("✅ROE優")
    if peg>0 and peg<1.2: score+=15; det.append("💎PEG低")
    if rsi<30: score+=15; det.append("📉超賣")
    if change<-2: score+=10; det.append("🔥大跌")
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    mac = get_us_macro()
    sl = []
    bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        try:
            s = yf.Ticker(t)
            h = s.history(period="1y")
            if h.empty or len(h)<200: continue
            
            cur = h['Close'].iloc[-1]
            chg = ((cur-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100
            
            delta = h['Close'].diff()
            gain = (delta.where(delta>0, 0)).rolling(14).mean()
            loss = (-delta.where(delta<0, 0)).rolling(14).mean().replace(0, 0.001)
            rsi = 100 - (100/(1 + (gain/loss))).iloc[-1]
            
            info = s.info
            g = calc_graham(info)
            m = ((g-cur)/cur)*100 if g>0 else 0
            peg = info.get('pegRatio', 0)
            roe = (info.get('returnOnEquity', 0) or 0)*100
            
            sc, re = score_us_stock(rsi, peg, m, roe, chg, mac)
            sl.append({"代號":t, "現價":f"{cur:.2f}", "葛拉漢價":f"{g:.2f}" if g>0 else "-", "邊際":f"{m:.1f}%", "分數":int(sc), "評分原因":re})
        except: pass
        bar.progress((i+1)/len(tickers))
        
    return pd.DataFrame(sl), mac

# --- UI ---
days = get_fomc()
c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描美股'):
    ds, mac = get_data(target_tickers)
    c1.metric("利率預期", f"{mac['rate']:.2f}%")
    c2.metric("VIX", f"{mac['vix']:.2f}")
    c3.metric("FOMC", f"剩 {days} 天")
    
    if api_key:
        with st.spinner("🤖 雙人格分析中..."):
            st.session_state.ai_response_us_conservative = ask_ai(api_key, "conservative", mac, days, ds)
            st.session_state.ai_response_us_growth = ask_ai(api_key, "growth", mac, days, ds)
    
    if st.session_state.ai_response_us_conservative:
        st.write("### 🤖 觀點對決")
        t1, t2 = st.tabs(["🧐 巴菲特 (價值)", "✨ 伍德 (成長)"])
        with t1: st.info(st.session_state.ai_response_us_conservative)
        with t2: st.success(st.session_state.ai_response_us_growth)

    def hi(v): return 'background-color: #1b5e20; color: white; font-weight: bold;' if v>=80 else 'background-color: #c8e6c9; color: black;' if v>=60 else ''
    st.subheader("🏢 掃描結果")
    if not ds.empty: st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(hi, subset=['分數']))
    else: st.warning("無數據")
