import streamlit as st
import yfinance as yf
import pandas as pd
import time
import openai
import math

st.set_page_config(page_title="🇹🇼 Moat Hunter (Industry)", layout="wide")
st.title("🇹🇼 Moat Hunter (產業龍頭版)")
st.markdown("### 策略：產業地位 + 高毛利護城河 + 外資動向")

# --- 1. 產業鏈清單 (由上而下) ---
TREND_THEMES = {
    "🔥 自選監控": [], 
    
    "👑 半導體護國群山 (晶圓/封測/IC)": {
        "logic": "台灣最強核心，擁有絕對技術護城河。",
        "tickers": ['2330.TW', '2454.TW', '3711.TW', '2303.TW', '3034.TW']
        # 台積電(晶圓), 聯發科(IC設計), 日月光(封測), 聯電, 聯詠
    },
    "🤖 AI 硬體供應鏈 (伺服器/電源/散熱)": {
        "logic": "全球 AI 軍備競賽的實際製造者。",
        "tickers": ['2317.TW', '2382.TW', '2308.TW', '3231.TW', '3017.TW'] 
        # 鴻海, 廣達, 台達電(電源龍頭), 緯創, 奇鋐(散熱)
    },
    "💎 隱形冠軍 (關鍵零組件/工業)": {
        "logic": "在利基市場市佔率極高，擁有定價權。",
        "tickers": ['3008.TW', '2395.TW', '1590.TW', '2327.TW', '3661.TW']
        # 大立光(鏡頭), 研華(工業電腦), 亞德客(氣動), 國巨(被動元件), 世芯(ASIC)
    },
    "🌐 網通與高速傳輸": {
        "logic": "數據中心與 5G 基建必備。",
        "tickers": ['2345.TW', '2379.TW', '4966.TW', '6271.TW']
        # 智邦(交換器), 瑞昱(網通IC), 譜瑞(高速傳輸), 同欣電
    }
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '2317.TW'] 
if 'ai_response_tw' not in st.session_state: st.session_state.ai_response_tw = None

st.sidebar.header("🇹🇼 設定")
api_key = st.sidebar.text_input("OpenAI API Key:", type="password")
selected_theme = st.sidebar.selectbox("產業鏈:", list(TREND_THEMES.keys()))

# --- 智慧代號處理 ---
target_tickers = []
if selected_theme == "🔥 自選監控":
    st.sidebar.caption("💡 輸入純數字也可以 (例如 2330)，系統會自動加 .TW")
    new = st.sidebar.text_input("➕ 新增代號:").upper().strip()
    
    if st.sidebar.button("新增") and new:
        if new.isdigit():
            new = f"{new}.TW"
            st.sidebar.success(f"已自動修正為: {new}")
        if new not in st.session_state.watchlist_tw: 
            st.session_state.watchlist_tw.append(new)
            
    if st.session_state.watchlist_tw:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_tw)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_tw.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_tw
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]
    st.sidebar.info(f"💡 **產業邏輯：** {TREND_THEMES[selected_theme]['logic']}")

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

def ask_ai(api_key, macro, df_s):
    client = openai.OpenAI(api_key=api_key)
    # 給 AI 看毛利率和產業地位
    picks = []
    if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','評分原因']].to_dict('records')
    
    prompt = f"""
    擔任台股產業分析師。繁體中文。
    宏觀: USD/TWD {macro['twd']:.2f} (變動{macro['twd_chg']:.2f}%), 費半 {macro['sox']:.2f}%。
    精選龍頭股: {picks}
    任務: 
    1. 產業分析：這些公司的供應鏈地位穩固嗎？
    2. 護城河評估：毛利率是否顯示具備定價權？
    3. 操作建議。
    """
    try:
        res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
        return res.choices[0].message.content
    except Exception as e: return f"AI 分析失敗: {str(e)}"

# --- 核心評分邏輯 (Moat Focus) ---
def score_industry_stock(rsi, pe, margin, roe, change, safety_margin, macro):
    score = 50; det = []

    # 1. 護城河 (毛利率 Gross Margin) - 最重要
    # 毛利高代表有技術優勢或品牌溢價
    if margin > 50: score += 20; det.append("🏰超強護城河")
    elif margin > 30: score += 15; det.append("💎高毛利")
    elif margin < 10: score -= 10; det.append("🔨毛利低(代工)")

    # 2. 產業地位與品質 (ROE)
    if roe > 20: score += 15; det.append("👑ROE頂級")
    elif roe > 15: score += 10; det.append("✅ROE優")
    
    # 3. 宏觀與外資
    if macro['twd_chg'] > 0.2: score -= 5; det.append("⚠️匯率貶")
    if macro['sox'] > 1.5: score += 10; det.append("🚀費半攻")
    
    # 4. 估值 (本益比 & 葛拉漢)
    if safety_margin > 10: score += 10; det.append("💰低估")
    if pe > 0 and pe < 15: score += 10; det.append("✅PE合理")
    elif pe > 40: score -= 10; det.append("🔥PE過熱")

    # 5. 技術面
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
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                loss = loss.replace(0, 0.001)
                rs = gain / loss
                rsi = 100 - (100/(1 + rs)).iloc[-1]
                
                info = s.info
                
                # 抓取關鍵數據
                margin = (info.get('grossMargins', 0) or 0) * 100 # 毛利率
                pe = info.get('trailingPE', 0)
                roe = (info.get('returnOnEquity', 0) or 0) * 100
                
                g = calc_graham(info)
                safety = ((g-cur)/cur)*100 if g>0 else 0
                
                sc, re = score_industry_stock(rsi, pe, margin, roe, chg, safety, mac)
                
                sl.append({
                    "代號": t.replace(".TW",""), 
                    "現價": f"{cur:.1f}", 
                    "毛利率": f"{margin:.1f}%", # 重點指標
                    "ROE": f"{roe:.1f}%",
                    "分數": int(sc), 
                    "評分原因": re
                })
        except: pass
        bar.progress((i+1)/len(tickers))
    
    status.empty()
    return pd.DataFrame(sl), mac

# --- UI ---
c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描產業供應鏈'):
    ds, mac = get_data(target_tickers)
    c1.metric("USD/TWD", f"{mac['twd']:.2f}", f"{mac['twd_chg']:.2f}%", delta_color="inverse")
    c2.metric("費半指數", f"{mac['sox']:.2f}%")
    
    if api_key:
        with st.spinner("AI 分析護城河中..."): st.session_state.ai_response_tw = ask_ai(api_key, mac, ds)
    if st.session_state.ai_response_tw: st.info(st.session_state.ai_response_tw)
    
    def highlight_score(val):
        if val >= 80: return 'background-color: #1b5e20; color: white; font-weight: bold;'
        elif val >= 60: return 'background-color: #c8e6c9; color: black;'
        return ''
    
    st.subheader("🏭 產業龍頭 (毛利率為王)")
    if not ds.empty: 
        st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(highlight_score, subset=['分數']))
    else: st.warning("無數據")
