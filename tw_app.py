import streamlit as st
import yfinance as yf
import pandas as pd
import openai
import math

st.set_page_config(page_title="🇹🇼 Moat Hunter (Pure)", layout="wide")
st.title("🇹🇼 Moat Hunter (台股極簡版)")
st.markdown("### 策略：外資 vs 產業 (單引擎雙人格) + 護城河")

# --- 設定與清單 ---
TREND_THEMES = {
    "🔥 自選監控": [], 
    "👑 半導體護國群山": {"tickers": ['2330.TW', '2454.TW', '3711.TW', '2303.TW', '3034.TW']},
    "🤖 AI 硬體供應鏈": {"tickers": ['2317.TW', '2382.TW', '2308.TW', '3231.TW', '3017.TW']},
    "💎 隱形冠軍": {"tickers": ['3008.TW', '2395.TW', '1590.TW', '2327.TW', '3661.TW']},
    "🌐 網通與高速傳輸": {"tickers": ['2345.TW', '2379.TW', '4966.TW', '6271.TW']}
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '2317.TW'] 
if 'ai_response_tw_conservative' not in st.session_state: st.session_state.ai_response_tw_conservative = None
if 'ai_response_tw_growth' not in st.session_state: st.session_state.ai_response_tw_growth = None

# --- 側邊欄 ---
st.sidebar.header("🚀 設定")
api_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
selected_theme = st.sidebar.selectbox("產業鏈:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控":
    new = st.sidebar.text_input("➕ 新增代號:").upper().strip()
    if st.sidebar.button("新增") and new:
        if new.isdigit(): new = f"{new}.TW"
        if new not in st.session_state.watchlist_tw: st.session_state.watchlist_tw.append(new)
    if st.session_state.watchlist_tw:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_tw)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_tw.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_tw
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]

# --- 核心函式 ---
@st.cache_data(ttl=300)
def get_tw_macro():
    try:
        twd = yf.Ticker("TWD=X").history(period="5d")
        rate = twd['Close'].iloc[-1]
        chg = ((rate - twd['Close'].iloc[-2])/twd['Close'].iloc[-2])*100
        sox = yf.Ticker("^SOX").history(period="5d")
        sox_chg = ((sox['Close'].iloc[-1]-sox['Close'].iloc[-2])/sox['Close'].iloc[-2])*100
        return {"twd": rate, "twd_chg": chg, "sox": sox_chg}
    except: return {"twd": 32.0, "twd_chg": 0, "sox": 0}

def calc_graham(info):
    try:
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        return math.sqrt(22.5 * eps * bvps) if eps > 0 and bvps > 0 else 0
    except: return 0

def ask_ai(api_key, persona, macro, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
        
        if persona == "conservative":
            sys_msg = "你是保守派的外資分析師。嚴格控管風險。"
            user_msg = f"宏觀: 美金兌台幣{macro['twd']:.2f} (變動{macro['twd_chg']:.2f}%), 費半{macro['sox']:.2f}%。分析: {picks}。重點分析匯率風險與股價是否過熱。"
        else:
            sys_msg = "你是積極派的產業研究員。看重技術護城河與未來趨勢。"
            user_msg = f"宏觀: 費半{macro['sox']:.2f}%。分析: {picks}。重點分析毛利率是否代表具備定價權？在供應鏈中是否不可或缺？鼓勵抓住長期機會。"

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system", "content": sys_msg}, {"role":"user", "content": user_msg}]
        )
        return res.choices[0].message.content
    except Exception as e: return f"AI 分析失敗: {str(e)}"

def score_industry_stock(rsi, pe, margin, roe, change, safety, macro):
    score = 50; det = []
    if margin > 50: score += 20; det.append("🏰強護城河")
    elif margin > 30: score += 15; det.append("💎高毛利")
    elif margin < 10: score -= 10; det.append("🔨毛利低")
    if roe > 20: score += 15; det.append("👑ROE頂級")
    if macro['twd_chg'] > 0.2: score -= 5; det.append("⚠️匯率貶")
    if macro['sox'] > 1.5: score += 10; det.append("🚀費半攻")
    if safety > 10: score += 10; det.append("💰低估")
    if pe > 0 and pe < 15: score += 10; det.append("✅PE合理")
    elif pe > 40: score -= 10; det.append("🔥PE過熱")
    if rsi < 30: score += 15; det.append("📉超賣")
    if change < -2.5: score += 10; det.append("🩸大跌")
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    mac = get_tw_macro()
    sl = []
    bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        try:
            s = yf.Ticker(t)
            h = s.history(period="6mo")
            if h.empty or len(h)<10: continue
            
            cur = h['Close'].iloc[-1]
            chg = ((cur-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100
            
            delta = h['Close'].diff()
            gain = (delta.where(delta>0, 0)).rolling(14).mean()
            loss = (-delta.where(delta<0, 0)).rolling(14).mean().replace(0, 0.001)
            rsi = 100 - (100/(1 + (gain/loss))).iloc[-1]
            
            info = s.info
            margin = (info.get('grossMargins', 0) or 0) * 100
            pe = info.get('trailingPE', 0)
            roe = (info.get('returnOnEquity', 0) or 0) * 100
            g = calc_graham(info)
            safety = ((g-cur)/cur)*100 if g>0 else 0
            
            sc, re = score_industry_stock(rsi, pe, margin, roe, chg, safety, mac)
            sl.append({"代號":t.replace(".TW",""), "現價":f"{cur:.1f}", "毛利率":f"{margin:.1f}%", "分數":int(sc), "評分原因":re})
        except: pass
        bar.progress((i+1)/len(tickers))
    
    return pd.DataFrame(sl), mac

# --- UI ---
c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描台股'):
    ds, mac = get_data(target_tickers)
    c1.metric("USD/TWD", f"{mac['twd']:.2f}", f"{mac['twd_chg']:.2f}%", delta_color="inverse")
    c2.metric("費半指數", f"{mac['sox']:.2f}%")
    
    if api_key:
        with st.spinner("🤖 雙人格分析中..."):
            st.session_state.ai_response_tw_conservative = ask_ai(api_key, "conservative", mac, ds)
            st.session_state.ai_response_tw_growth = ask_ai(api_key, "growth", mac, ds)
            
    if st.session_state.ai_response_tw_conservative:
        st.write("### 🤖 觀點對決")
        t1, t2 = st.tabs(["🧐 外資 (保守)", "✨ 產業 (成長)"])
        with t1: st.info(st.session_state.ai_response_tw_conservative)
        with t2: st.success(st.session_state.ai_response_tw_growth)

    def hi(v): return 'background-color: #1b5e20; color: white; font-weight: bold;' if v>=80 else 'background-color: #c8e6c9; color: black;' if v>=60 else ''
    st.subheader("🏭 產業龍頭")
    if not ds.empty: st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(hi, subset=['分數']))
    else: st.warning("無數據")
