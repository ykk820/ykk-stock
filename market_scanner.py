import streamlit as st
import yfinance as yf
import pandas as pd
from tradingview_ta import TA_Handler, Interval, Exchange
import streamlit.components.v1 as components
import time

# --- 1. 設定與清單 ---
TICKERS = ['VOO', 'GOOG', 'V', 'NET', 'PANW', 'MSFT', 'ISRG', 'CEG', 'AAPL', 'TSM']
st.set_page_config(page_title="Moat Hunter v11 (Macro)", layout="wide")
st.title("🛡️ Moat Hunter v11 (宏觀狙擊版)")
st.markdown("### 策略：監控 Fed 態度 (殖利率)、大盤災難與恐慌指數")

# --- 2. 獲取宏觀數據 (Macro Data) ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        # A. 恐慌指數 (VIX)
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        
        # B. 10年期公債殖利率 (^TNX) - 鷹派/鴿派 風向球
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_prev = tnx['Close'].iloc[-2]
        tnx_change = ((tnx_curr - tnx_prev) / tnx_prev) * 100 # 殖利率變動百分比
        
        # C. 美股大盤 (S&P 500)
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

def get_exchange(symbol):
    if symbol in ['VOO', 'V', 'NET', 'TSM']: return "NYSE"
    return "NASDAQ"

# --- 4. 核心評分邏輯 (加入宏觀權重) ---
def calculate_sniper_score(rsi, margin, pe, change_pct, macro_data):
    score = 50 
    details = []
    
    # --- A. 宏觀加分 (Macro Boost) ---
    # 1. 鷹派衝擊 (Rates Shock): 殖利率單日大漲 > 3% -> 科技股殺盤 -> 機會
    if macro_data['tnx_change'] > 3.0:
        score += 15
        details.append("🦅鷹派升息恐慌(+15)")
    
    # 2. 大盤崩跌 (Market Crash): S&P 500 大跌 > 1.5% -> 系統性買點
    if macro_data['sp500_change'] < -1.5:
        score += 20
        details.append("📉大盤崩跌(+20)")
        
    # 3. 恐慌指數 (VIX)
    if macro_data['vix'] > 30:
        score += 20
        details.append("🩸極度恐慌VIX(+20)")

    # --- B. 個股素質 ---
    # 估值 (P/E)
    if pe > 0 and pe < 25:
        score += 10
        details.append("💰便宜(+10)")
    elif pe > 50:
        score -= 15
        details.append("💸太貴(-15)")

    # 護城河 (毛利)
    if margin > 50:
        score += 10
        details.append("🏰高毛利(+10)")

    # --- C. 技術面 ---
    if rsi < 30:
        score += 15
        details.append("📉RSI超賣(+15)")
    
    if change_pct < -2.0:
        score += 10
        details.append("🔥單日大跌(+10)")

    return max(0, min(100, score)), " ".join(details)

@st.cache_data(ttl=600, show_spinner=False)
def get_market_data(tickers):
    # 1. 先抓宏觀環境
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

                # 2. 將宏觀數據傳入評分系統
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

# --- 5. 介面呈現 ---

# 側邊欄：宏觀儀表板
st.sidebar.header("🌍 宏觀儀表板 (Macro)")
if st.button('🚀 執行全域掃描'):
    with st.spinner('正在分析 Fed 態度與大盤走勢...'):
        df, macro = get_market_data(TICKERS)
        
        # 顯示宏觀狀態
        # A. VIX
        st.sidebar.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", 
                          delta="極度恐慌" if macro['vix'] > 30 else "正常",
                          delta_color="inverse") # 越高越紅
        
        # B. 10年債 (鷹派指標)
        tnx_delta_color = "normal" if macro['tnx_change'] > 0 else "inverse" # 漲=紅(鷹派), 跌=綠(鴿派)
        st.sidebar.metric("10年債殖利率 (鷹派指標)", f"{macro['tnx_yield']:.2f}%", 
                          f"{macro['tnx_change']:.2f}%",
                          delta_color=tnx_delta_color)
        if macro['tnx_change'] > 2.0:
            st.sidebar.error("🦅 殖利率飆升！鷹派衝擊！")

        # C. S&P 500
        st.sidebar.metric("S&P 500 大盤", f"變動", f"{macro['sp500_change']:.2f}%")
        if macro['sp500_change'] < -1.5:
            st.sidebar.success("📉 大盤崩跌中！全場特價！")

        # 主畫面表格
        if not df.empty:
            def highlight_score(val):
                if val >= 80: return 'background-color: #28a745; color: white'
                if val >= 60: return 'background-color: #d4edda; color: black' 
                return ''

            st.dataframe(df.style.map(highlight_score, subset=['Score']))
            st.markdown("""
            ### 🦅 鷹派與崩跌訊號說明：
            * **鷹派升息恐慌 (+15分)**：當 10 年債殖利率單日大漲，代表資金逃離債市，通常科技股會大跌。
            * **大盤崩跌 (+20分)**：當 S&P 500 單日跌幅超過 1.5%，代表系統性風險，是撿好股的最佳時機。
            """)
        else:
            st.error("無法取得數據，請稍後再試。")
else:
    st.info("請點擊左側按鈕開始掃描。")

# --- 6. TradingView ---
st.markdown("---")
selected = st.selectbox("查看圖表:", TICKERS)
tv_symbol = f"{get_exchange(selected)}:{selected}"
components.html(f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget(
  {{ "width": "100%", "height": 450, "symbol": "{tv_symbol}", "interval": "D", "theme": "dark" }}
  );
  </script>
</div>
""", height=450)
