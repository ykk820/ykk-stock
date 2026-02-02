import streamlit as st
import yfinance as yf
import pandas as pd
import time

# --- 1. 設定與邏輯資料庫 (擴充版) ---
st.set_page_config(page_title="Moat Hunter v15 (Supply Chain)", layout="wide")
st.title("🛡️ Moat Hunter v15 (全方位趨勢版)")
st.markdown("### 策略：透過「產業邏輯」尋找低估的 S&P 500 龍頭")

# 定義你的「邏輯鏈」
TREND_THEMES = {
    "🔥 自選監控名單": [], 
    
    "📦 全球供應鏈重組 (物流/自動化)": {
        "logic": "製造業回流與去全球化，需要更強的物流中心與自動化設備。",
        "tickers": ['PLD', 'UPS', 'FDX', 'ROK', 'HON', 'ZBRA', 'ETN']
        # PLD(全球最大倉儲), ROK(工廠自動化), ZBRA(條碼追蹤), ETN(電力管理)
    },
    "⚡️ AI 的盡頭是電力 (核能/電網)": {
        "logic": "AI 資料中心需要 24 小時穩定基載電力，核能與電網是最大受惠者。",
        "tickers": ['CEG', 'VST', 'NEE', 'DUK', 'SO', 'ETR', 'CCJ'] 
    },
    "🏗️ 基礎建設超級週期 (機具/原物料)": {
        "logic": "修橋鋪路蓋工廠，實體經濟的基石。",
        "tickers": ['CAT', 'DE', 'VMC', 'MLM', 'URI', 'FCX']
        # CAT(開拓重工), VMC(砂石龍頭), FCX(銅礦-電網需要銅)
    },
    "🧠 AI 基礎建設 (晶片/伺服器)": {
        "logic": "AI 發展的第一階段，賣鏟子的硬體公司。",
        "tickers": ['NVDA', 'TSM', 'AVGO', 'AMD', 'MSFT', 'GOOG', 'META']
    },
    "🛡️ 世界動盪 (國防/航太)": {
        "logic": "地緣政治風險升高，各國增加國防預算。",
        "tickers": ['LMT', 'RTX', 'NOC', 'GD', 'BA']
    },
    "💰 金融護城河 (支付/抗通膨)": {
        "logic": "通膨越高，刷卡金額越高，手續費收越多 (抗通膨首選)。",
        "tickers": ['V', 'MA', 'AXP', 'JPM', 'BLK', 'SPGI']
        # V/MA(支付壟斷), SPGI(信評壟斷-標普)
    },
    "💊 減肥與高齡化 (生技/製藥)": {
        "logic": "GLP-1 減肥藥需求與人口老化趨勢。",
        "tickers": ['LLY', 'NVO', 'ISRG', 'UNH', 'JNJ', 'ABBV']
    },
     "🔒 數位保全 (資安)": {
        "logic": "AI 帶來的攻擊增加，企業必須採購資安服務。",
        "tickers": ['PANW', 'CRWD', 'NET', 'FTNT', 'PLTR']
    }
}

# --- 2. 初始化 Session State ---
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['VOO', 'AAPL'] 

# --- 3. 側邊欄控制 ---
st.sidebar.header("🌍 選擇投資趨勢")
selected_theme = st.sidebar.selectbox("你想押注哪個未來？", list(TREND_THEMES.keys()))

# 處理自選名單邏輯
target_tickers = []
theme_desc = ""

if selected_theme == "🔥 自選監控名單":
    st.sidebar.markdown("---")
    new_ticker = st.sidebar.text_input("➕ 新增代號 (如 AMZN):").upper()
    if st.sidebar.button("新增"):
        if new_ticker and new_ticker not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_ticker)
            
    if st.session_state.watchlist:
        remove_ticker = st.sidebar.selectbox("移除:", ["(選擇)"] + st.session_state.watchlist)
        if remove_ticker != "(選擇)" and st.sidebar.button("刪除"):
            st.session_state.watchlist.remove(remove_ticker)
            st.experimental_rerun()
            
    target_tickers = st.session_state.watchlist
    theme_desc = "你個人的觀察清單。"
else:
    # 載入預設趨勢股
    target_tickers = TREND_THEMES[selected_theme]["tickers"]
    theme_desc = TREND_THEMES[selected_theme]["logic"]
    st.sidebar.info(f"💡 **邏輯：**\n{theme_desc}")

# --- 4. 獲取宏觀數據 ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_change = ((tnx_curr - tnx['Close'].iloc[-2]) / tnx['Close'].iloc[-2]) * 100 
        sp500 = yf.Ticker("^GSPC").history(period="5d")
        sp_change = ((sp500['Close'].iloc[-1] - sp500['Close'].iloc[-2]) / sp500['Close'].iloc[-2]) * 100
        return {"vix": vix, "tnx_yield": tnx_curr, "tnx_change": tnx_change, "sp500_change": sp_change}
    except:
        return {"vix": 20, "tnx_yield": 4.0, "tnx_change": 0, "sp500_change": 0}

# --- 5. 核心評分邏輯 (含 PEG 過濾投機股) ---
def get_financials(stock):
    try:
        info = stock.info
        peg = info.get('pegRatio', 0)
        pe = info.get('trailingPE', 0)
        margin = info.get('grossMargins', 0) * 100
        return peg, pe, margin
    except:
        return 0, 0, 0

def calculate_trend_score(rsi, peg, pe, margin, change, macro):
    score = 50
    details = []

    # A. 宏觀 (全體加分)
    if macro['vix'] > 30: 
        score += 20; details.append("🩸恐慌VIX")
    if macro['tnx_change'] > 3.0: 
        score += 15; details.append("🦅升息預期")
    if macro['sp500_change'] < -1.5: 
        score += 20; details.append("📉大盤崩跌")

    # B. 價值過濾 (非投機)
    if peg > 0 and peg < 1.2:
        score += 15; details.append("💎PEG低估")
    elif peg > 3.5:
        score -= 10; details.append("⚠️PEG過高")
    
    if pe > 0 and pe < 20:
        score += 10; details.append("💰PE便宜")

    # C. 技術面
    if rsi < 35: score += 15; details.append("📉超賣")
    if change < -2.0: score += 10; details.append("🔥大跌")

    return max(0, min(100, score)), " ".join(details)

def get_market_data(tickers):
    macro = get_macro_environment()
    data_list = []
    progress = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            if len(hist) > 14:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((curr - prev) / prev) * 100
                
                # 計算 RSI
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1]

                peg, pe, margin = get_financials(stock)
                
                final_score, reasons = calculate_trend_score(rsi_val, peg, pe, margin, change, macro)

                data_list.append({
                    "代號": ticker,
                    "現價": f"${curr:.2f}",
                    "分數": int(final_score),
                    "漲跌幅": f"{change:.2f}%",
                    "PEG": f"{peg:.2f}" if peg else "-",
                    "P/E": f"{pe:.1f}" if pe else "-",
                    "評分原因": reasons
                })
            time.sleep(0.1)
        except: pass
        progress.progress((i + 1) / len(tickers))
    
    df = pd.DataFrame(data_list)
    if not df.empty: df = df.sort_values(by="分數", ascending=False)
    return df, macro

# --- 6. 介面 ---
st.subheader(f"📊 目前趨勢：{selected_theme.split('(')[0]}")
st.write(theme_desc)

if st.button('🚀 掃描此板塊'):
    with st.spinner(f'正在分析 {len(target_tickers)} 支龍頭股...'):
        df, macro = get_market_data(target_tickers)
        
        # 顯示宏觀
        c1, c2, c3 = st.columns(3)
        c1.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", delta="極度恐慌" if macro['vix']>30 else "正常", delta_color="inverse")
        c2.metric("10年債 (鷹派)", f"{macro['tnx_yield']:.2f}%", f"{macro['tnx_change']:.2f}%", delta_color="inverse")
        c3.metric("標普500", "變動", f"{macro['sp500_change']:.2f}%")

        if not df.empty:
            def highlight(val):
                if val >= 80: return 'background-color: #28a745; color: white'
                if val >= 60: return 'background-color: #d4edda; color: black'
                return ''
            st.dataframe(df.style.map(highlight, subset=['分數']))
            st.info("💡 **名詞解釋：**\n* **PEG**: 找成長股的神器。PEG < 1.2 才是真便宜。\n* **RSI < 35**: 短線超賣，通常會反彈。")
        else:
            st.warning("請先新增自選股或等待數據下載。")
