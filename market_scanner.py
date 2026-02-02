import streamlit as st
import yfinance as yf
import pandas as pd
from tradingview_ta import TA_Handler, Interval, Exchange
import streamlit.components.v1 as components
from GoogleNews import GoogleNews
from textblob import TextBlob
import statistics

# --- 1. 設定與清單 ---
TICKERS = ['VOO', 'GOOG', 'V', 'NET', 'PANW', 'MSFT', 'ISRG', 'CEG', 'AAPL', 'TSM']
st.set_page_config(page_title="Moat Hunter v6 (逆向投資)", layout="wide")
st.title("💎 Moat Hunter v6 (逆向價值獵手)")
st.markdown("### 策略核心：別人恐慌我貪婪 (Bad News is Good News)")

# --- 2. 核心分析邏輯 ---

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
        
        for item in results[:7]:
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
        
        # --- 3. 逆向邏輯 (The Switch) ---
        # 分數越低 (負面新聞) -> 對你是「買點」 (Opportunity)
        if avg_score < -0.05:
            return f"💎 恐慌買點 (原因: {reason})", avg_score
        # 分數越高 (正面新聞) -> 對你是「風險」 (Risk)
        elif avg_score > 0.05:
            return f"⚠️ 過熱風險 (原因: {reason})", avg_score
        else:
            return f"⚪ 觀望中 (原因: {reason})", avg_score

    except Exception as e:
        return "分析失敗", 0

def get_exchange(symbol):
    if symbol in ['VOO', 'V', 'NET', 'TSM']: return "NYSE"
    return "NASDAQ"

def get_market_data(tickers):
    data_list = []
    progress_bar = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        
        if len(hist) > 0:
            curr = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = ((curr - prev) / prev) * 100
            
            # 判斷是否大跌 (跌幅 > 1.5%)
            is_dip = change < -1.5
            
            # AI 逆向結論
            ai_text, ai_score = get_contrarian_ai(ticker)

            data_list.append({
                "Ticker": ticker,
                "Price": f"${curr:.2f}",
                "Change %": change,
                "Strategy Signal": ai_text, # 這是你的逆向指標
                "Is Dip?": "YES" if is_dip else "No"
            })
        progress_bar.progress((i + 1) / len(tickers))
            
    return pd.DataFrame(data_list)

# --- 3. 介面 ---
if st.button('🚀 掃描恐慌機會'):
    st.write("正在尋找市場上的「倒霉鬼」與「錯殺股」...")
    df = get_market_data(TICKERS)
    
    # 樣式設定：逆向操作
    def highlight_strategy(row):
        # 如果是「恐慌買點」 -> 標記綠色 (Green Light to Buy)
        if "恐慌買點" in row['Strategy Signal']:
            return ['background-color: #d4edda; color: black'] * len(row) # 淺綠底
        # 如果是「過熱風險」 -> 標記紅色 (Red Light to Stop)
        elif "過熱風險" in row['Strategy Signal']:
            return ['background-color: #f8d7da; color: black'] * len(row) # 淺紅底
        else:
            return [''] * len(row)

    st.dataframe(df.style.apply(highlight_strategy, axis=1))

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