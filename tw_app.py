import streamlit as st
import yfinance as yf
import pandas as pd
import time
import math
import openai
import google.generativeai as genai

st.set_page_config(page_title="🇹🇼 Moat Hunter (Dual AI)", layout="wide")
st.title("🇹🇼 Moat Hunter (雙 AI 辯論版)")
st.markdown("### 策略：OpenAI vs Gemini 交叉比對 + 產業護城河")

# --- 1. 產業鏈清單 ---
TREND_THEMES = {
    "🔥 自選監控": [], 
    "👑 半導體護國群山": {"logic": "晶圓/封測/IC設計", "tickers": ['2330.TW', '2454.TW', '3711.TW', '2303.TW', '3034.TW']},
    "🤖 AI 硬體供應鏈": {"logic": "伺服器/散熱/電源", "tickers": ['2317.TW', '2382.TW', '2308.TW', '3231.TW', '3017.TW']},
    "💎 隱形冠軍": {"logic": "鏡頭/工業/關鍵零組件", "tickers": ['3008.TW', '2395.TW', '1590.TW', '2327.TW', '3661.TW']},
    "🌐 網通與高速傳輸": {"logic": "數據中心基建", "tickers": ['2345.TW', '2379.TW', '4966.TW', '6271.TW']}
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '2317.TW'] 
if 'ai_response_openai' not in st.session_state: st.session_state.ai_response_openai = None
if 'ai_response_gemini' not in st.session_state: st.session_state.ai_response_gemini = None

# --- 側邊欄：雙引擎設定 ---
st.sidebar.header("🚀 雙引擎設定")
openai_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
gemini_key = st.sidebar.text_input("Gemini Key (AIza...):", type="password")

st.sidebar.markdown("---")
selected_theme = st.sidebar.selectbox("產業鏈:", list(TREND_THEMES.keys()))

# --- 智慧代號處理 ---
target_tickers = []
if selected_theme == "🔥 自選監控":
    new = st.sidebar.text_input("➕ 新增代號:").upper().strip()
    if st.sidebar.button("新增") and new:
        if new.isdigit(): new = f"{new}.TW"; st.sidebar.success(f"已修正: {new}")
        if new not in st.session_state.watchlist_tw: st.session_state.watchlist_tw.append(new)
    if st.session_state.watchlist_tw:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_tw)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_tw.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_tw
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]

# --- 數據函式 ---
@st.cache_data(ttl=300)
def get_tw_macro():
    try:
        twd = yf.Ticker("TWD=X").history(period="5d")
        if twd.empty: return {"twd": 32.0, "twd_chg": 0, "sox": 0}
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

# --- 🧠 AI 大腦區 ---

def ask_openai(api_key, macro, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
        prompt = f"""
        你是【保守穩健派】的華爾街分析師（類似巴菲特）。繁體中文。
        宏觀: USD/TWD {macro['twd']:.2f}, 費半 {macro['sox']:.2f}%。
        精選: {picks}
        任務: 請用「嚴格、懷疑」的角度分析這些股票。重點放在風險、估值是否過高？如果沒問題才建議買進。
        """
        res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
        return res.choices[0].message.content
    except Exception as e: return f"OpenAI 罷工: {str(e)}"

def ask_gemini(api_key, macro, df_s):
    try:
        # 設定 API
        genai.configure(api_key=api_key)
        
        # ⚠️ 這裡修改了：改用 'gemini-pro'，這是最穩定的版本，舊版套件也能跑
        model = genai.GenerativeModel('gemini-pro')
        
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
        
        prompt = f"""
        你是【積極成長派】的矽谷投資人（類似凱薩琳伍德）。繁體中文。
        宏觀: USD/TWD {macro['twd']:.2f}, 費半 {macro['sox']:.2f}%。
        精選: {picks}
        任務: 請用「趨勢、未來」的角度分析這些股票。重點放在產業護城河、未來成長爆發力。鼓勵抓住機會。
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e: return f"Gemini 罷工: {str(e)}"

# --- 評分邏輯 ---
def score_industry_stock(rsi, pe, margin, roe, change, safety_margin, macro):
    score = 50; det = []
    if margin > 50: score += 20; det.append("🏰超強護城河")
    elif margin > 30: score += 15; det.append("💎高毛利")
    elif margin < 10: score -= 10; det.append("🔨毛利低")
    if roe > 20: score += 15; det.append("👑ROE頂級")
    if macro['twd_chg'] > 0.2: score -= 5; det.append("⚠️匯率貶")
    if macro['sox'] > 1.5: score += 10; det.append("🚀費半攻")
    if safety_margin > 10: score += 10; det.append("💰低估")
    if pe > 0 and pe < 15: score += 10; det.append("✅PE合理")
    elif pe > 40: score -= 10; det.append("🔥PE過熱")
    if rsi < 30: score += 15; det.append("📉超賣")
    if change < -2.5: score += 10; det.append("🩸大跌")
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    mac = get_tw_macro()
    sl = []
    bar = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        status.text(f"分析中: {t}")
        try:
            s = yf.Ticker(t)
            h = s.history(period="6mo")
            if h.empty:
                st.toast(f"找不到 {t}", icon="⚠️")
                continue
            if len(h)>10:
                cur = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2] if h['Close'].iloc[-2]!=0 else cur
                chg = ((cur-prev)/prev)*100
                delta = h['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, 0.001)
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
    
    status.empty()
    return pd.DataFrame(sl), mac

# --- UI ---
c1,c2,c3 = st.columns(3)
if st.button('🚀 雙引擎啟動'):
    ds, mac = get_data(target_tickers)
    c1.metric("USD/TWD", f"{mac['twd']:.2f}", f"{mac['twd_chg']:.2f}%", delta_color="inverse")
    c2.metric("費半指數", f"{mac['sox']:.2f}%")
    
    # 平行處理
    if openai_key or gemini_key:
        with st.spinner("🤖 雙 AI 正在辯論中..."):
            if openai_key: st.session_state.ai_response_openai = ask_openai(openai_key, mac, ds)
            if gemini_key: st.session_state.ai_response_gemini = ask_gemini(gemini_key, mac, ds)

    # 顯示辯論結果
    if st.session_state.ai_response_openai or st.session_state.ai_response_gemini:
        st.write("### 🤖 投資觀點對決")
        tab1, tab2 = st.tabs(["🧐 OpenAI (保守派)", "✨ Gemini (成長派)"])
        
        with tab1:
            if st.session_state.ai_response_openai: st.info(st.session_state.ai_response_openai)
            else: st.warning("未輸入 OpenAI Key")
        
        with tab2:
            if st.session_state.ai_response_gemini: st.success(st.session_state.ai_response_gemini)
            else: st.warning("未輸入 Gemini Key")

    def highlight_score(val):
        if val >= 80: return 'background-color: #1b5e20; color: white; font-weight: bold;'
        elif val >= 60: return 'background-color: #c8e6c9; color: black;'
        return ''
    
    st.subheader("🏭 產業龍頭數據")
    if not ds.empty: 
        st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(highlight_score, subset=['分數']))
    else: st.warning("無數據")
    
