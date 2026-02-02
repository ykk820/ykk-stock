import streamlit as st
import yfinance as yf
import pandas as pd
import time

# --- 1. 設定與邏輯資料庫 ---
st.set_page_config(page_title="Moat Hunter v17 (Dual)", layout="wide")
st.title("🛡️ Moat Hunter v17 (雙軌評分版)")
st.markdown("### 策略：個股看「體質 (ROE/現金流)」，ETF 看「回檔 (Drawdown/VIX)」")

# 定義已知 ETF 清單 (用來快速分類)
KNOWN_ETFS = ['VOO', 'SPY', 'QQQ', 'IVV', 'VTI', 'VT', 'SCHD', 'TLT', 'SOXX', 'SMH', 'XLK', 'XLE', 'XLV', 'XLF', 'TQQQ', 'SOXL']

# 趨勢板塊 (混合了 ETF 與個股)
TREND_THEMES = {
    "🔥 自選監控名單": [], 
    "📊 指數型 ETF (大盤/高股息)": {
        "logic": "跟隨大盤長期成長，適合跌深加碼。",
        "tickers": ['VOO', 'QQQ', 'SCHD', 'VT', 'TLT', 'SMH']
    },
    "⚡️ AI 的盡頭是電力 (核能/電網)": {
        "logic": "AI 資料中心需要 24 小時穩定基載電力。",
        "tickers": ['CEG', 'VST', 'NEE', 'DUK', 'SO', 'CCJ'] 
    },
    "📦 全球供應鏈重組": {
        "logic": "製造業回流與自動化需求。",
        "tickers": ['PLD', 'ROK', 'ZBRA', 'ETN', 'HON']
    },
    "🧠 AI 基礎建設": {
        "logic": "賣鏟子的硬體公司。",
        "tickers": ['NVDA', 'TSM', 'AVGO', 'AMD', 'MSFT', 'GOOG']
    },
    "🛡️ 世界動盪 (國防)": {
        "logic": "地緣政治風險升高。",
        "tickers": ['LMT', 'RTX', 'NOC', 'GD']
    },
    "💰 金融護城河": {
        "logic": "抗通膨與手續費經濟。",
        "tickers": ['V', 'MA', 'JPM', 'BLK', 'SPGI']
    },
    "🛒 抗衰退堡壘": {
        "logic": "資金避風港。",
        "tickers": ['COST', 'KO', 'PG', 'PEP', 'MCD']
    }
}

# --- 2. 初始化 ---
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['VOO', 'AAPL'] 

# --- 3. 側邊欄 ---
st.sidebar.header("🌍 選擇投資戰場")
selected_theme = st.sidebar.selectbox("趨勢板塊:", list(TREND_THEMES.keys()))

target_tickers = []
theme_desc = ""

if selected_theme == "🔥 自選監控名單":
    new_ticker = st.sidebar.text_input("➕ 新增代號:").upper()
    if st.sidebar.button("新增"):
        if new_ticker and new_ticker not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_ticker)
    
    if st.session_state.watchlist:
        remove_ticker = st.sidebar.selectbox("移除:", ["(選擇)"] + st.session_state.watchlist)
        if remove_ticker != "(選擇)" and st.sidebar.button("刪除"):
            st.session_state.watchlist.remove(remove_ticker)
            st.experimental_rerun()
    target_tickers = st.session_state.watchlist
    theme_desc = "你的私人觀察名單。"
else:
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

# --- 5. 評分邏輯核心 (雙軌制) ---

# A. 個股評分標準 (財報嚴格版)
def score_company(rsi, peg, pe, roe, de, fcf, change, macro):
    score = 50
    details = []

    # 宏觀影響
    if macro['vix'] > 30: score += 20; details.append("🩸恐慌VIX")
    if macro['tnx_change'] > 3.0: score += 15; details.append("🦅升息預期")
    if macro['sp500_change'] < -1.5: score += 20; details.append("📉大盤崩跌")

    # 品質 (Quality)
    if roe > 15: score += 10; details.append("✅ROE優")
    elif roe < 5: score -= 15; details.append("❌ROE低")
    
    if de > 2.5: score -= 20; details.append("💀高負債")
    if fcf <= 0: score -= 20; details.append("💸燒錢")

    # 估值 (Value)
    if peg > 0 and peg < 1.2: score += 15; details.append("💎PEG低估")
    if pe > 0 and pe < 20: score += 10; details.append("💰PE便宜")

    # 技術 (Timing)
    if rsi < 30: score += 15; details.append("📉超賣")
    if change < -2.0: score += 10; details.append("🔥大跌")

    return max(0, min(100, score)), " ".join(details)

# B. ETF 評分標準 (回檔撿便宜版)
def score_etf(rsi, change, drawdown, price, ma200, macro):
    score = 50
    details = []

    # ETF 最重要的就是：要在恐慌時買，在跌深時買
    # 1. 恐慌指數 (VIX) - 權重加倍
    if macro['vix'] > 30: 
        score += 30; details.append("🩸極度恐慌(+30)")
    elif macro['vix'] > 20: 
        score += 15; details.append("😰市場緊張(+15)")

    # 2. 回檔幅度 (Drawdown) - 離 52 週高點越遠越好
    if drawdown < -20:
        score += 25; details.append("🐻熊市價(+25)")
    elif drawdown < -10:
        score += 15; details.append("📉修正價(+15)")
    elif drawdown > -2:
        score -= 10; details.append("🏔️高點勿追(-10)")

    # 3. 技術面 (RSI)
    if rsi < 30: score += 20; details.append("📉RSI超賣(+20)")
    elif rsi > 70: score -= 15; details.append("🔥RSI過熱(-15)")

    # 4. 年線乖離 (均線回歸)
    if ma200 > 0:
        if price < ma200:
            score += 10; details.append("💎跌破年線(+10)")
        elif price > ma200 * 1.2:
            score -= 10; details.append("⚠️乖離過大(-10)")

    return max(0, min(100, score)), " ".join(details)

def get_market_data(tickers):
    macro = get_macro_environment()
    stock_list = []
    etf_list = []
    progress = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y") # ETF 需要一年數據算 Drawdown
            if len(hist) > 200:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((curr - prev) / prev) * 100
                
                # RSI
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1]

                # 判斷是否為 ETF (簡單邏輯：在已知清單 或 沒有 PEG/ROE 資料)
                info = stock.info
                is_etf = (ticker in KNOWN_ETFS) or (info.get('quoteType') == 'ETF')
                
                if is_etf:
                    # --- ETF 邏輯 ---
                    high_52 = hist['Close'].max()
                    drawdown = ((curr - high_52) / high_52) * 100
                    ma200 = hist['Close'].rolling(200).mean().iloc[-1]
                    
                    score, reason = score_etf(rsi_val, change, drawdown, curr, ma200, macro)
                    
                    etf_list.append({
                        "代號": ticker,
                        "現價": f"${curr:.2f}",
                        "分數": int(score),
                        "回檔幅度": f"{drawdown:.1f}%", # ETF 重點
                        "離年線": "低於" if curr < ma200 else "高於",
                        "評分原因": reason
                    })
                else:
                    # --- 個股邏輯 ---
                    peg = info.get('pegRatio', 0)
                    pe = info.get('trailingPE', 0)
                    roe = info.get('returnOnEquity', 0)
                    if roe: roe *= 100
                    else: roe = 0
                    
                    de = info.get('debtToEquity', 0)
                    if de: de /= 100
                    else: de = 0
                    
                    fcf = info.get('freeCashflow', 0)
                    
                    score, reason = score_company(rsi_val, peg, pe, roe, de, fcf, change, macro)
                    
                    stock_list.append({
                        "代號": ticker,
                        "現價": f"${curr:.2f}",
                        "分數": int(score),
                        "ROE": f"{roe:.1f}%",
                        "負債比": f"{de:.1f}",
                        "PEG": f"{peg:.2f}" if peg else "-",
                        "評分原因": reason
                    })

            time.sleep(0.1)
        except: pass
        progress.progress((i + 1) / len(tickers))
    
    df_stock = pd.DataFrame(stock_list)
    if not df_stock.empty: df_stock = df_stock.sort_values(by="分數", ascending=False)
    
    df_etf = pd.DataFrame(etf_list)
    if not df_etf.empty: df_etf = df_etf.sort_values(by="分數", ascending=False)
    
    return df_stock, df_etf, macro

# --- 6. 介面 ---
st.subheader(f"📊 目前戰場：{selected_theme.split('(')[0]}")
st.write(theme_desc)

if st.button('🚀 執行雙軌掃描'):
    with st.spinner(f'正在分類並分析 {len(target_tickers)} 支標的...'):
        df_stock, df_etf, macro = get_market_data(target_tickers)
        
        # 宏觀儀表板
        c1, c2, c3 = st.columns(3)
        c1.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", delta="適合買ETF" if macro['vix']>30 else "平穩", delta_color="inverse")
        c2.metric("10年債 (鷹派)", f"{macro['tnx_yield']:.2f}%", f"{macro['tnx_change']:.2f}%", delta_color="inverse")
        c3.metric("標普500", "變動", f"{macro['sp500_change']:.2f}%")

        def highlight(val):
            if val >= 80: return 'background-color: #28a745; color: white'
            if val >= 60: return 'background-color: #d4edda; color: black'
            return ''

        # 分開顯示
        if not df_etf.empty:
            st.markdown("### 📊 指數/ETF (評估標準：回檔與恐慌)")
            st.dataframe(df_etf.style.map(highlight, subset=['分數']))
            st.info("💡 **ETF 策略：** 不看財報，只看「有沒有跌深」。若回檔幅度超過 -10% 且分數高，通常是長期買點。")

        if not df_stock.empty:
            st.markdown("### 🏢 企業個股 (評估標準：財報與品質)")
            st.dataframe(df_stock.style.map(highlight, subset=['分數']))
            st.info("💡 **個股 策略：** 嚴格檢視 ROE 與 現金流。分數低通常代表太貴或基本面有問題。")
            
        if df_stock.empty and df_etf.empty:
            st.warning("無數據。")
