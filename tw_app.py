import streamlit as st
import yfinance as yf
import pandas as pd
import time
import math
import openai
import google.generativeai as genai

st.set_page_config(page_title="🇹🇼 Moat Hunter (Final Fix)", layout="wide")
st.title("🇹🇼 Moat Hunter (台股終極修復版)")
st.markdown("### 策略：OpenAI (保守) vs Gemini (成長) + 自動偵測模型")

# --- 1. 產業鏈清單 ---
TREND_THEMES = {
    "🔥 自選監控": [], 
    "👑 半導體護國群山": {"logic": "晶圓/封測/IC設計", "tickers": ['2330.TW', '2454.TW', '3711.TW', '2303.TW', '3034.TW']},
    "🤖 AI 硬體供應鏈": {"logic": "伺服器/散熱/電源", "tickers": ['2317.TW', '2382.TW', '2308.TW', '3231.TW', '3017.TW']},
    "💎 隱形冠軍": {"logic": "鏡頭/工業/關鍵零組件", "tickers": ['3008.TW', '2395.TW', '1590.TW', '2327.TW', '3661.TW']},
    "🌐 網通與高速傳輸": {"logic": "數據中心基建", "tickers": ['2345.TW', '2379.TW', '4966.TW', '6271.TW']}
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '2317.TW'] 
if 'ai_response_tw_openai' not in st.session_state: st.session_state.ai_response_tw_openai = None
if 'ai_response_tw_gemini' not in st.session_state: st.session_state.ai_response_tw_gemini = None

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

# --- 🧠 AI 大腦區 (OpenAI) ---
def ask_openai(api_key, macro, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
        prompt = f"""
        你是【保守派的外資分析師】。繁體中文。
        宏觀: USD/TWD {macro['twd']:.2f} (變動 {macro['twd_chg']:.2f}%), 費半 {macro['sox']:.2f}%。
        精選: {picks}
        任務: 請用「嚴格、避險」的角度分析。
        1. 匯率風險：台幣貶值是否影響資金撤離？
        2. 估值風險：這些股票是否過熱？毛利是否能支撐股價？
        """
        res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
        return res.choices[0].message.content
    except Exception as e: return f"OpenAI 罷工: {str(e)}"

# --- 🧠 AI 大腦區 (Gemini 暴力窮舉版) ---
def ask_gemini(api_key, macro, df_s):
    try:
        genai.configure(api_key=api_key)
        
        # 1. 定義白名單 (優先順序)
        candidate_models = [
            'gemini-1.5-flash',
            'gemini-1.5-flash-latest',
            'gemini-1.5-pro',
            'gemini-1.5-pro-latest',
            'gemini-1.0-pro',
            'gemini-pro'
        ]
        
        target_model_name = None
        
        # 2. 嘗試從 API 抓取可用清單
        try:
            available = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            # 比對白名單
            for candidate in candidate_models:
                if candidate in available:
                    target_model_name = candidate
                    break
        except:
            pass # 如果 list_models 失敗，就直接往下盲測
            
        # 3. 如果還是沒找到，就用最通用的 'gemini-pro' 當最後手段
        if not target_model_name:
            target_model_name = 'gemini-pro'

        # 4. 建立模型
        model = genai.GenerativeModel(target_model_name)
        
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
        
        prompt = f"""
        你是【積極派的產業研究員】。繁體中文。
        宏觀: USD/TWD {macro['twd']:.2f}, 費半 {macro['sox']:.2f}%。
        精選: {picks}
        任務: 請用「產業趨勢、技術護城河」的角度分析。
        1. 競爭優勢：毛利率是否顯示具備定價權？
        2. 未來展望：在 AI 或半導體供應鏈中是否不可或缺？
        鼓勵抓住長期成長機會。
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e: 
        return f"Gemini 罷工 ({target_model_name}): {str(e)}"

# --- 評分邏輯 ---
def score_industry_stock(rsi, pe, margin, roe, change, safety_margin, macro):
    score = 50; det = []
    if margin > 50: score += 20; det.append("🏰超強護城河")
    elif margin > 30: score += 15; det.append("💎高毛利")
    elif margin < 10: score -= 10; det.append("🔨毛利低")
    if roe > 20: score += 15; det.append("👑ROE頂級")
    elif roe > 15: score += 10; det.append("✅ROE優")
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
        status.text(f"掃描護城河: {t}")
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
    c1.metric("USD/TWD (外資)", f"{mac['twd']:.2f}", f"{mac['twd_chg']:.2f}%", delta_color="inverse")
    c2.metric("費半指數 (科技)", f"{mac['sox']:.2f}%")
    
    # 平行處理
    if openai_key or gemini_key:
        with st.spinner("🤖 雙 AI 正在辯論中 (模型掃描)..."):
            if openai_key: st.session_state.ai_response_tw_openai = ask_openai(openai_key, mac, ds)
            if gemini_key: st.session_state.ai_response_tw_gemini = ask_gemini(gemini_key, mac, ds)

    # 顯示辯論結果
    if st.session_state.ai_response_tw_openai or st.session_state.ai_response_tw_gemini:
        st.write("### 🤖 投資觀點對決")
        tab1, tab2 = st.tabs(["🧐 OpenAI (保守外資)", "✨ Gemini (產業成長)"])
        
        with tab1:
            if st.session_state.ai_response_tw_openai: st.info(st.session_state.ai_response_tw_openai)
            else: st.warning("未輸入 OpenAI Key")
        
        with tab2:
            if st.session_state.ai_response_tw_gemini: st.success(st.session_state.ai_response_tw_gemini)
            else: st.warning("未輸入 Gemini Key")

    def highlight_score(val):
        if val >= 80: return 'background-color: #1b5e20; color: white; font-weight: bold;'
        elif val >= 60: return 'background-color: #c8e6c9; color: black;'
        return ''
    
    st.subheader("🏭 產業龍頭 (毛利率為王)")
    if not ds.empty: 
        st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(highlight_score, subset=['分數']))
    else: st.warning("無數據")
