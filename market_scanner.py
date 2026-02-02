import streamlit as st
import yfinance as yf
import pandas as pd
from tradingview_ta import TA_Handler, Interval, Exchange
import time

# --- 1. 設定與清單 ---
TICKERS = ['VOO', 'GOOG', 'V', 'NET', 'PANW', 'MSFT', 'ISRG', 'CEG', 'AAPL', 'TSM']
st.set_page_config(page_title="Moat Hunter v12 (Pure Signal)", layout="wide")
st.title("🛡️ Moat Hunter v12 (純訊號戰鬥版)")
st.markdown("### 策略：宏觀環境 (Fed/VIX) + 企業體質 (P/E, Margin) + 恐慌進場")

# --- 2. 獲取宏觀數據 (Macro Data) ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        # A. 恐慌指數 (VIX)
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        
        # B. 10年期公債殖利率 (^TNX) - 鷹派指標
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_prev = tnx['Close'].iloc[-2]
        tnx_change = ((tnx_curr - tnx_prev) / tnx_prev) * 100 
        
        # C. S&P 500 大盤
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

# --- 3. 獲取個股數據 ---
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

# --- 4. 核心評分邏輯 ---
def calculate_sniper_score(rsi, margin, pe, change_pct, macro_data):
    score = 50 
    details = []
    
    # A. 宏觀加分 (Macro)
    if macro_data['tnx_change'] > 3.0:
        score += 15
        details.append("🦅鷹派恐慌(+15)")
    
    if macro_data['sp500_change'] < -1.5:
        score += 20
        details.append("📉大盤崩跌(+20)")
        
    if macro_data['vix'] > 30:
        score += 20
        details.append("🩸極度恐慌VIX(+20)")

    # B. 基本面 (Fundamental)
    if pe > 0 and pe < 25:
        score += 10
        details.append("💰便宜PE(+10)")
    elif pe > 50:
        score -= 15
        details.append("💸太貴PE(-15)")

    if margin > 50:
        score += 10
        details.append("🏰高毛利(+10)")

    # C. 技術面 (Technical)
    if rsi < 30:
        score += 15
        details.append("📉RSI超賣(+15)")
    
    if change_pct < -2.0:
        score += 10
        details.append("🔥單日大跌(+10)")

    return max(0, min(100, score)), " ".join(details)

@st.cache_data(ttl=600, show_spinner=False)
def get_market_data(tickers):
    macro = get_macro_environment()
    data_list = []
    
    for ticker in tickers:
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
            continue
            
    df = pd.DataFrame(data_list)
    if not df.empty:
        df = df.sort_values(by="Score", ascending=False)
    return df, macro

# --- 5. 介面呈現 (極簡版) ---

# 側邊欄：宏觀數據
st.sidebar.header("🌍 宏觀數據 (Macro)")
if st.button('🚀 掃描市場訊號'):
    with st.spinner('正在分析數據...'):
        df, macro = get_market_data(TICKERS)
        
        # 顯示重點宏觀指標
        st.sidebar.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", 
                          delta="極度恐慌" if macro['vix'] > 30 else "正常",
                          delta_color="inverse")
        
        tnx_color = "normal" if macro['tnx_change'] > 0 else "inverse"
        st.sidebar.metric("10年債 (鷹派指標)", f"{macro['tnx_yield']:.2f}%", 
                          f"{macro['tnx_change']:.2f}%", delta_color=tnx_color)
        
        st.sidebar.metric("S&P 500 大盤", f"變動", f"{macro['sp500_change']:.2f}%")

        # 顯示主表格
        if not df.empty:
            def highlight_score(val):
                if val >= 80: return 'background-color: #28a745; color: white' # 深綠
                if val >= 60: return 'background-color: #d4edda; color: black' # 淺綠
                return ''

            st.dataframe(df.style.map(highlight_score, subset=['Score']))
            
            # 簡單說明
            st.info("""
            **評分邏輯 (最高100分)：**
            * **>= 80分 (🟢 強力買進)**：宏觀恐慌 (VIX高/大盤跌) + 個股超跌/便宜。
            * **>= 60分 (🟢 觀察買點)**：基本面優秀且價格合理。
            * **其他**：太貴或時機未到。
            """)
        else:
            st.error("連線忙碌中。")
else:
    st.write("👈 請點擊按鈕開始掃描")
