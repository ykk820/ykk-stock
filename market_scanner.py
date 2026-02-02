import streamlit as st
import yfinance as yf
import pandas as pd
import time

# --- 1. 設定與全方位邏輯庫 ---
st.set_page_config(page_title="Moat Hunter v16 (Strict)", layout="wide")
st.title("🛡️ Moat Hunter v16 (嚴格檢驗版)")
st.markdown("### 策略：9 大板塊趨勢 + 巴菲特三道濾網 (ROE/負債/現金流)")

# 定義 9 大邏輯板塊
TREND_THEMES = {
    "🔥 自選監控名單": [], 
    
    "📦 全球供應鏈重組 (物流/自動化)": {
        "logic": "製造業回流與去全球化，需要更強的物流中心與自動化設備。",
        "tickers": ['PLD', 'UPS', 'FDX', 'ROK', 'HON', 'ZBRA', 'ETN']
    },
    "⚡️ AI 的盡頭是電力 (核能/電網)": {
        "logic": "AI 資料中心需要 24 小時穩定基載電力，核能與電網是最大受惠者。",
        "tickers": ['CEG', 'VST', 'NEE', 'DUK', 'SO', 'ETR', 'CCJ'] 
    },
    "🏗️ 基礎建設超級週期 (機具/原物料)": {
        "logic": "修橋鋪路蓋工廠，實體經濟的基石。",
        "tickers": ['CAT', 'DE', 'VMC', 'MLM', 'URI', 'FCX']
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
    },
    "🛒 抗衰退堡壘 (必須消費)": {
        "logic": "不管經濟多差，人都要喝可樂、用牙膏、去賣場。資金避風港。",
        "tickers": ['COST', 'KO', 'PG', 'PEP', 'WMT', 'MCD']
        # COST(好市多), KO(可口可樂), PG(寶僑), MCD(麥當勞)
    },
    "🛢️ 舊能源避險 (石油/天然氣)": {
        "logic": "當AI需要電力，且地緣戰爭爆發時，石油與天然氣是最佳對沖。",
        "tickers": ['XOM', 'CVX', 'OXY', 'COP', 'EOG']
        # XOM(埃克森美孚), OXY(巴菲特愛股-西方石油)
    },
    "💊 減肥與高齡化 (生技/製藥)": {
        "logic": "GLP-1 減肥藥需求與人口老化趨勢。",
        "tickers": ['LLY', 'NVO', 'ISRG', 'UNH', 'JNJ', 'ABBV']
    }
}

# --- 2. 初始化 ---
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = ['VOO', 'AAPL'] 

# --- 3. 側邊欄 ---
st.sidebar.header("🌍 選擇投資戰場")
selected_theme = st.sidebar.selectbox("趨勢板塊:", list(TREND_THEMES.keys()))

# 處理名單
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

# --- 5. 嚴格的基本面獲取 (The Hardcore Fetch) ---
def get_strict_financials(stock):
    try:
        info = stock.info
        
        # 1. 估值指標
        peg = info.get('pegRatio', 0)
        pe = info.get('trailingPE', 0)
        
        # 2. 品質指標 (Quality)
        roe = info.get('returnOnEquity', 0) # 股東權益報酬率 (越高越好)
        debt_to_equity = info.get('debtToEquity', 0) # 負債比 (越低越好)
        margin = info.get('grossMargins', 0)
        
        # 3. 現金流 (Truth)
        fcf = info.get('freeCashflow', 0) # 自由現金流
        
        # 數據清理 (有些公司沒資料會回傳 None)
        roe = roe * 100 if roe else 0
        margin = margin * 100 if margin else 0
        debt_to_equity = debt_to_equity / 100 if debt_to_equity else 0 # 通常 API 回傳是 150 代表 1.5
        
        return peg, pe, roe, debt_to_equity, margin, fcf
    except:
        return 0, 0, 0, 999, 0, 0 # 預設爛數據以免誤判

def calculate_strict_score(rsi, peg, pe, roe, de, margin, fcf, change, macro):
    score = 50
    details = []

    # --- A. 宏觀加分 (Macro) ---
    if macro['vix'] > 30: score += 20; details.append("🩸恐慌VIX")
    if macro['tnx_change'] > 3.0: score += 15; details.append("🦅升息預期")
    if macro['sp500_change'] < -1.5: score += 20; details.append("📉大盤崩跌")

    # --- B. 品質濾網 (Strict Quality) ---
    # 1. ROE (巴菲特最愛): > 15% 是好公司，> 30% 是頂級
    if roe > 30: score += 15; details.append("👑ROE頂級")
    elif roe > 15: score += 10; details.append("✅ROE優秀")
    elif roe < 5: score -= 15; details.append("❌ROE太低")

    # 2. 負債比 (避開倒閉風險): > 2.0 (200%) 危險
    if de > 2.5: score -= 20; details.append("💀高負債")
    elif de < 0.5: score += 10; details.append("🛡️低負債")

    # 3. 現金流 (照妖鏡): 必須是正的
    if fcf is None or fcf <= 0: score -= 20; details.append("💸燒錢中")

    # --- C. 估值濾網 (Valuation) ---
    if peg > 0 and peg < 1.2: score += 15; details.append("💎PEG低估")
    elif peg > 4.0: score -= 10; details.append("⚠️PEG過高")
    
    if pe > 0 and pe < 20: score += 10; details.append("💰PE便宜")

    # --- D. 技術面 (Timing) ---
    if rsi < 30: score += 15; details.append("📉RSI超賣")
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
                
                # RSI
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1]

                # 獲取嚴格數據
                peg, pe, roe, de, margin, fcf = get_strict_financials(stock)
                
                final_score, reasons = calculate_strict_score(rsi_val, peg, pe, roe, de, margin, fcf, change, macro)

                data_list.append({
                    "代號": ticker,
                    "現價": f"${curr:.2f}",
                    "分數": int(final_score),
                    "ROE": f"{roe:.1f}%",
                    "負債比": f"{de:.1f}",
                    "PEG": f"{peg:.2f}" if peg else "-",
                    "評分原因": reasons
                })
            time.sleep(0.1)
        except: pass
        progress.progress((i + 1) / len(tickers))
    
    df = pd.DataFrame(data_list)
    if not df.empty: df = df.sort_values(by="分數", ascending=False)
    return df, macro

# --- 6. 介面 ---
st.subheader(f"📊 目前戰場：{selected_theme.split('(')[0]}")
st.write(theme_desc)

if st.button('🚀 執行嚴格掃描'):
    with st.spinner(f'正在進行 ROE 與 負債壓力測試...'):
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
            st.info("""
            **🛡️ 嚴格篩選標準：**
            * **👑 ROE (股東權益報酬率)**：> 15% 才及格。代表公司很會賺錢。
            * **💀 負債比**：> 2.5 會被扣分。防止買到快倒閉的公司。
            * **💸 自由現金流**：如果是負的 (燒錢)，會大幅扣分。
            """)
        else:
            st.warning("請先新增自選股或等待數據下載。")
