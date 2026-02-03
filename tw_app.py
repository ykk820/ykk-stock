import streamlit as st
import yfinance as yf
import pandas as pd
import openai
import math

st.set_page_config(page_title="🇹🇼 Moat Hunter (Pure)", layout="wide")
st.title("🇹🇼 Moat Hunter (台股結構版)")
st.markdown("### 策略：供應鏈地位 + 護城河 (毛利率) + 雙人格分析")

# --- 設定與清單 (專注供應鏈與龍頭) ---
TREND_THEMES = {
    "🔥 自選監控": [], 
    
    "👑 半導體護國群山 (核心)": {
        "logic": "全球晶片製造的核心，先進製程與封測壟斷。",
        "tickers": ['2330.TW', '2454.TW', '3711.TW', '2303.TW', '3034.TW']
        # 台積電, 聯發科, 日月光, 聯電, 聯詠
    },
    
    "🤖 AI 硬體供應鏈 (軍火商)": {
        "logic": "AI 伺服器、散熱、電源，訂單最明確的族群。",
        "tickers": ['2317.TW', '2382.TW', '2308.TW', '3231.TW', '3017.TW', '2356.TW']
        # 鴻海, 廣達, 台達電, 緯創, 奇鋐, 英業達
    },
    
    "💎 隱形冠軍 (高毛利護城河)": {
        "logic": "在利基市場擁有定價權，毛利率通常極高。",
        "tickers": ['3008.TW', '2395.TW', '1590.TW', '2327.TW', '3661.TW', '3529.TW']
        # 大立光, 研華, 亞德客, 國巨, 世芯, 力旺
    },
    
    "🌐 網通與高速傳輸 (基建)": {
        "logic": "數據傳輸速度升級，光通訊與交換器。",
        "tickers": ['2345.TW', '2379.TW', '4966.TW', '6271.TW']
        # 智邦, 瑞昱, 譜瑞, 同欣電
    }
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '2317.TW'] 
if 'ai_response_tw_conservative' not in st.session_state: st.session_state.ai_response_tw_conservative = None
if 'ai_response_tw_growth' not in st.session_state: st.session_state.ai_response_tw_growth = None

# --- 側邊欄 ---
st.sidebar.header("🚀 設定")
api_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
selected_theme = st.sidebar.selectbox("供應鏈板塊:", list(TREND_THEMES.keys()))

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
    st.sidebar.info(f"💡 {TREND_THEMES[selected_theme]['logic']}")

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

def ask_ai(api_key, persona, macro, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        # 🟢 修正點：確保只抓取存在的欄位，避免 KeyError
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','毛利率','ROE','評分原因']].to_dict('records')
        
        if persona == "conservative":
            sys_msg = "你是保守派的外資分析師。嚴格控管風險，看重基本面數據。"
            user_msg = f"宏觀: 美金兌台幣{macro['twd']:.2f} (變動{macro['twd_chg']:.2f}%), 費半{macro['sox']:.2f}%。分析: {picks}。請分析：1.匯率變動對外資買賣超的影響？ 2.股價是否已反映利多(過熱)？"
        else:
            sys_msg = "你是積極派的產業研究員。看重技術獨佔性與未來訂單。"
            user_msg = f"宏觀: 費半{macro['sox']:.2f}%。分析: {picks}。請分析：1.這些公司的毛利率是否顯示具備「護城河」？ 2.在 AI 供應鏈中是否具有「不可取代性」？"

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system", "content": sys_msg}, {"role":"user", "content": user_msg}]
        )
        return res.choices[0].message.content
    except Exception as e: return f"AI 分析失敗: {str(e)}"

def score_industry_stock(rsi, pe, margin, roe, change, macro):
    score = 50; det = []
    
    # 1. 護城河 (毛利率)
    if margin > 50: score += 20; det.append("🏰超強護城河")
    elif margin > 30: score += 15; det.append("💎高毛利")
    elif margin < 10: score -= 10; det.append("🔨毛利低")
    
    # 2. 經營效率 (ROE)
    if roe > 20: score += 15; det.append("👑ROE頂級")
    elif roe > 15: score += 10; det.append("✅ROE優")
    
    # 3. 宏觀與技術
    if macro['twd_chg'] > 0.2: score -= 5; det.append("⚠️匯率貶(外資逃)")
    if macro['sox'] > 1.5: score += 10; det.append("🚀費半攻")
    
    # 4. 估值與位階
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
            # 抓取關鍵數據 (若無數據則給 0)
            margin = (info.get('grossMargins', 0) or 0) * 100
            pe = info.get('trailingPE', 0)
            roe = (info.get('returnOnEquity', 0) or 0) * 100
            
            sc, re = score_industry_stock(rsi, pe, margin, roe, chg, mac)
            sl.append({
                "代號":t.replace(".TW",""), 
                "現價":f"{cur:.1f}", 
                "毛利率":f"{margin:.1f}%", # 護城河指標
                "ROE":f"{roe:.1f}%",      # 效率指標
                "分數":int(sc), 
                "評分原因":re
            })
        except: pass
        bar.progress((i+1)/len(tickers))
    
    return pd.DataFrame(sl), mac

# --- UI ---
c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描供應鏈'):
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
    st.subheader("🏭 產業龍頭 (毛利/ROE)")
    if not ds.empty: st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(hi, subset=['分數']))
    else: st.warning("無數據")
