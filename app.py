import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px

# 設定網頁標題與排版
st.set_page_config(page_title="巴菲特持股追蹤器", layout="wide")

st.title("💰 Warren Buffett's Portfolio Tracker")
st.markdown("數據來源：SEC 13F Filings (via Dataroma) & Yahoo Finance")
st.markdown("---")

# ---------------------------------------------------------
# 1. 爬蟲函數：抓取波克夏最新持股
# ---------------------------------------------------------
@st.cache_data(ttl=24*3600)  # 設定快取，避免每次重新整理都去爬網站
def get_buffett_portfolio():
    url = "https://www.dataroma.com/m/holdings.php?m=BRK"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        # 利用 Pandas 直接讀取網頁中的表格
        dfs = pd.read_html(response.text)
        # Dataroma 的持股表格通常是列表中的第一個
        df = dfs[0]
        
        # 清理資料：只留我們需要的欄位
        # 欄位名稱可能會變，這裡針對 Dataroma 的結構做處理
        df = df[['Stock', 'Symbol', '% ofPortfolio', 'Share Count', 'ReportedPrice']]
        df.columns = ['Company', 'Ticker', 'Portfolio_Pct', 'Shares', 'Cost_Price']
        
        # 轉換數值格式 (去除 % 和 $ 符號)
        df['Portfolio_Pct'] = df['Portfolio_Pct'].astype(str).str.replace('%', '').astype(float)
        
        return df
    except Exception as e:
        st.error(f"抓取數據失敗: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 股價函數：取得即時價格與漲跌
# ---------------------------------------------------------
def get_live_prices(tickers):
    if not tickers:
        return {}
    
    # yfinance 一次抓多檔股票比較快
    data = yf.download(tickers, period="1d", group_by='ticker', threads=True)
    
    prices = {}
    for ticker in tickers:
        try:
            # 取得最新收盤價 (有些資料可能會有延遲)
            # 處理 yfinance 多層索引的問題
            if len(tickers) > 1:
                current_price = data[ticker]['Close'].iloc[-1]
                prev_close = data[ticker]['Open'].iloc[-1] # 簡易計算當日漲跌
            else:
                current_price = data['Close'].iloc[-1]
                prev_close = data['Open'].iloc[-1]
            
            change_pct = ((current_price - prev_close) / prev_close) * 100
            prices[ticker] = {'Price': current_price, 'Change_Pct': change_pct}
        except:
            prices[ticker] = {'Price': 0, 'Change_Pct': 0}
            
    return prices

# ---------------------------------------------------------
# 3. 主程式邏輯
# ---------------------------------------------------------
df = get_buffett_portfolio()

if not df.empty:
    # 側邊欄：篩選器
    st.sidebar.header("篩選設定")
    top_n = st.sidebar.slider("顯示前幾大持股?", 5, 50, 10)
    
    # 取出前 N 大持股
    df_top = df.head(top_n).copy()
    
    # 抓取即時股價
    ticker_list = df_top['Ticker'].tolist()
    
    with st.spinner('正在抓取最新美股報價...'):
        price_data = get_live_prices(ticker_list)
    
    # 將即時股價合併回 DataFrame
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0))
    
    # 格式化顯示
    df_display = df_top[['Ticker', 'Company', 'Portfolio_Pct', 'Current_Price', 'Day_Change_%']]
    
    # -----------------------------------------------------
    # 4. 視覺化儀表板
    # -----------------------------------------------------
    
    # 顯示指標卡片 (Top 3 持股的即時狀況)
    col1, col2, col3 = st.columns(3)
    top_3 = df_top.head(3)
    
    cols = [col1, col2, col3]
    for i, row in enumerate(top_3.itertuples()):
        cols[i].metric(
            label=f"#{i+1} {row.Ticker}",
            value=f"${row.Current_Price:.2f}",
            delta=f"{row._5:.2f}%" # _5 對應 Day_Change_%
        )

    # 圖表區
    col_chart, col_table = st.columns([1, 2])
    
    with col_chart:
        st.subheader("持股佔比 (Portfolio Weight)")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.subheader(f"前 {top_n} 大持股詳細清單")
        # 使用 Pandas Styler 加上顏色 (漲=綠, 跌=紅)
        def color_change(val):
            color = '#ff4b4b' if val < 0 else '#3bd671'
            return f'color: {color}'
            
        st.dataframe(
            df_display.style.map(color_change, subset=['Day_Change_%'])
            .format({"Current_Price": "${:.2f}", "Day_Change_%": "{:.2f}%", "Portfolio_Pct": "{:.2f}%"}),
            height=400
        )

    st.info("💡 註：13F 報告每季公佈一次，因此持股名單會有約 45 天的延遲。即時股價為市場現價。")

else:
    st.warning("無法抓取數據，請稍後再試或檢查來源網站是否改版。")