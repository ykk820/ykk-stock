import streamlit as st
import yfinance as yf
import pandas as pd
import time

# --- 1. 設定頁面 ---
st.set_page_config(page_title="Moat Hunter v13 (Dynamic)", layout="wide")
st.title("🛡️ Moat Hunter v13 (動態輸入版)")
st.markdown("### 策略：宏觀環境 + 企業體質 + 自訂監控")

# --- 2. 初始化 Session State (記憶體) ---
# 這是讓網頁「記住」你新增了哪些股票的關鍵
if 'tickers' not in st.session_state:
    st.session_state.tickers = ['VOO', 'GOOG', 'V', 'NET', 'PANW', 'MSFT', 'ISRG', 'CEG', 'AAPL', 'TSM']

# --- 3. 側邊欄：新增/移除股票 ---
st.sidebar.header("📝 管理監控名單")

# 新增股票
new_ticker = st.sidebar.text_input("輸入美股代號 (例如 NVDA):").upper()
if st.sidebar.button("➕ 新增到清單"):
    if new_ticker and new_ticker not in st.session_state.tickers:
        st.session_state.tickers.append(new_ticker)
        st.sidebar.success(f"已新增 {new_ticker}！")
    elif new_ticker in st.session_state.tickers:
        st.sidebar.warning("這支股票已經在清單裡了。")

# 顯示目前清單 (可選移除)
st.sidebar.markdown("---")
st.sidebar.write(f"目前監控中 ({len(st.session_state.tickers)}):")
ticker_to_remove = st.sidebar.selectbox("移除股票:", ["(選擇以移除)"] + st.session_state.tickers)
if ticker_to_remove != "(選擇以移除)":
    if st.sidebar.button("🗑️ 移除"):
        st.session_state.tickers.remove(ticker_to_remove)
        st.experimental_rerun() # 重新整理頁面

# --- 4. 獲取宏觀數據 ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_prev = tnx['Close'].iloc[-2]
        tnx_change = ((tnx_curr - tnx_prev) / tnx_prev) * 100 
        
        sp500 = yf.Ticker("^GSPC").history(period="5d")
        sp_curr = sp500['Close'].iloc[-1]
        sp_prev = sp500['Close'].iloc[-2]
        sp_change = ((sp_curr - sp_prev) / sp_prev) * 100
        
        return {
            "vix": vix,
            "tnx_yield": tnx_curr,
            "tnx_change": tnx_change,
            "sp500_change": sp_change
        }
    except:
        return {"vix": 20, "tnx_yield": 4.0, "tnx_change": 0, "sp500_change": 0}

# --- 5. 獲取個股數據 ---
def get_financial_health(stock):
    try:
        info = stock.info
        gross_margin = info.get('grossMargins', 0) * 100
        pe_ratio = info.get('trailingPE', 0)
        return gross_margin, pe_ratio
    except:
        return 0, 0

def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# --- 6. 核心評分邏輯 ---
def calculate_sniper_score(rsi, margin, pe, change_pct, macro_data):
    score = 50 
    details = []
    
    # 宏觀 (Macro)
    if macro_data['tnx_change'] > 3.0:
        score += 15
        details.append("🦅鷹派恐慌")
    if macro_data['sp500_change'] < -1.5:
        score += 20
        details.append("📉大盤崩跌")
    if macro_data['vix'] > 30:
        score += 20
        details.append("🩸極度恐慌VIX")

    # 基本面 (Fundamental)
    if pe > 0 and pe < 25:
        score += 10
        details.append("💰便宜PE")
    elif pe > 50:
        score -= 15
        details.append("💸太貴PE")

    if margin > 50:
        score += 10
        details.append("🏰高毛利")

    # 技術面 (Technical)
    if rsi < 30:
        score += 15
        details.append("📉RSI超賣")
    if change_pct < -2.0:
        score += 10
        details.append("🔥單日大跌")

    return max(0, min(100, score)), " ".join(details)

def get_market_data(tickers):
    macro = get_macro_environment()
    data_list = []
    
    # 建立進度條
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="6mo")
            
            if len(hist) > 14:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((curr - prev) / prev) * 100
                rsi = calculate_rsi(hist)
                
                if ticker == 'VOO':
                    margin, pe = 0, 0
                else:
                    margin, pe = get_financial_health(stock)

                final_score, reasons = calculate_sniper_score(rsi, margin, pe, change, macro)

                data_list.append({
                    "Ticker": ticker,
                    "Price": f"${curr:.2f}",
                    "Score": int(final_score),
                    "Change": f"{change:.2f}%",
                    "P/E": f"{pe:.1f}" if pe > 0 else "-",
                    "Reason": reasons
                })
            time.sleep(0.1)
        except Exception:
            pass # 抓不到就跳過
        
        # 更新進度條
        progress_bar.progress((i + 1) / len(tickers))
            
    df = pd.DataFrame(data_list)
    if not df.empty:
        df = df.sort_values(by="Score", ascending=False)
    return df, macro

# --- 7. 主介面 ---

if st.button('🚀 開始掃描清單'):
    with st.spinner(f'正在分析 {len(st.session_state.tickers)} 支股票...'):
        # 使用 session_state 裡的清單
        df, macro = get_market_data(st.session_state.tickers)
        
        # 顯示宏觀指標
        col1, col2, col3 = st.columns(3)
        col1.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", delta="極度恐慌" if macro['vix'] > 30 else "正常", delta_color="inverse")
        col2.metric("10年債 (鷹派)", f"{macro['tnx_yield']:.2f}%", f"{macro['tnx_change']:.2f}%", delta_color="inverse")
        col3.metric("S&P 500", "變動", f"{macro['sp500_change']:.2f}%")

        if not df.empty:
            def highlight_score(val):
                if val >= 80: return 'background-color: #28a745; color: white'
                if val >= 60: return 'background-color: #d4edda; color: black'
                return ''

            st.dataframe(df.style.map(highlight_score, subset=['Score']))
        else:
            st.warning("沒有數據，請確認你的清單有股票。")
else:
    st.info(f"目前清單內有 {len(st.session_state.tickers)} 支股票，點擊按鈕開始掃描。")
