import streamlit as st
import yfinance as yf
import pandas as pd
from tradingview_ta import TA_Handler, Interval, Exchange
import streamlit.components.v1 as components
from GoogleNews import GoogleNews
from textblob import TextBlob
import statistics
import time

# --- 1. 設定與清單 ---
TICKERS = ['VOO', 'GOOG', 'V', 'NET', 'PANW', 'MSFT', 'ISRG', 'CEG', 'AAPL', 'TSM']
st.set_page_config(page_title="Moat Hunter v7 (Anti-Block)", layout="wide")
st.title("💎 Moat Hunter v7 (防封鎖穩定版)")
st.markdown("### 策略核心：別人恐慌我貪婪 (快取優化模式)")

# --- 2. 核心分析邏輯 (加上快取) ---

# 設定 ttl=3600，代表這段 AI 分析會被記住 1 小時 (3600秒)
# 這樣就不用每次都去 Google 搜尋，大幅降低被擋機率
@st.cache_data(ttl=3600, show_spinner=False)
def get_contrarian_ai(ticker):
    try:
        # 1. 抓新聞
        googlenews = GoogleNews(lang='en', region='US')
        googlenews.set_period('3d') 
        googlenews.search(f"{ticker} stock")
        results = googlenews.results()
        
        if not results:
            return "無重大消息", 0

        # 2. 情感計算
        scores = []
        keywords = []
        
        for item in results[:5]: # 減少數量加快速度
            title = item['title']
            blob = TextBlob(title)
            scores.append(blob.sentiment.polarity)
            
            t_lower = title.lower()
            if "earnings" in t_lower: keywords.append("財報")
            if "plunge" in t_lower or "drop" in t_lower: keywords.append("暴跌")
            if "fed" in t_lower: keywords.append("升息/通膨")
            if "lawsuit" in t_lower: keywords.append("訴訟")
            if "hike" in t_lower: keywords.append("漲價")

        avg_score = statistics.mean(scores) if scores else 0
        reason = "、".join(list(set(keywords))) if keywords else "市場波動"
        
        if avg_score < -0.05:
            return f"💎 恐慌買點 (原因: {reason})", avg_score
        elif avg_score > 0.05:
            return f"⚠️ 過熱風險 (原因: {reason})", avg_score
        else:
            return f"⚪ 觀望中 (原因: {reason})", avg_score

    except Exception:
        return "暫無分析", 0

def get_exchange(symbol):
    if symbol in ['VOO', 'V', 'NET', 'TSM']: return "NYSE"
    return "NASDAQ"

# 設定 ttl=600，代表股價每 10 分鐘才更新一次
# 這對價值投資者來說綽綽有餘，且能完美避開 Yahoo 封鎖
@st.cache_data(ttl=600, show_spinner=False)
def get_market_data(tickers):
    data_list = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            # 加上錯誤處理，如果抓不到就跳過，不會讓整個網站掛掉
            hist = stock.history(period="6mo")
            
            if len(hist) > 0:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((curr - prev) / prev) * 100
                is_dip = change < -1.5
                
                # AI 分析 (現在會讀取快取)
                ai_text, ai_score = get_contrarian_ai(ticker)

                data_list.append({
                    "Ticker": ticker,
                    "Price": f"${curr:.2f}",
                    "Change %": change,
                    "Strategy Signal": ai_text,
                    "Is Dip?": "YES" if is_dip else "No"
                })
            time.sleep(0.1) # 稍微休息一下，對 API 溫柔一點
            
        except Exception as e:
            # 如果這支股票抓不到，就先跳過，不要報錯
            continue
            
    return pd.DataFrame(data_list)

# --- 3. 介面 ---
if st.button('🚀 掃描恐慌機會 (快取啟動)'):
    with st.spinner('正在從快取或雲端讀取數據...'):
        df = get_market_data(TICKERS)
        
        if not df.empty:
            def highlight_strategy(row):
                if "恐慌買點" in row['Strategy Signal']:
                    return ['background-color: #d4edda; color: black'] * len(row)
                elif "過熱風險" in row['Strategy Signal']:
                    return ['background-color: #f8d7da; color: black'] * len(row)
                else:
                    return [''] * len(row)

            st.dataframe(df.style.apply(highlight_strategy, axis=1))
        else:
            st.error("⚠️ Yahoo 目前暫時阻擋了連線，請過 10 分鐘後再試。")

# --- 4. 詳細圖表 ---
st.markdown("---")
selected = st.selectbox("查看詳細圖表:", TICKERS)
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
