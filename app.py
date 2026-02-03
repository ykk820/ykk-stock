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
# ---------------------------------------------------------
# 1. 爬蟲函數：抓取波克夏最新持股 (修正版)
# ---------------------------------------------------------
@st.cache_data(ttl=24*3600)
def get_buffett_portfolio():
    url = "https://www.dataroma.com/m/holdings.php?m=BRK"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.get(url, headers=headers)
        dfs = pd.read_html(response.text)
        df = dfs[0]
        
        # --- 🔧 除錯專用：如果又報錯，這一行會顯示抓到了什麼欄位 ---
        # st.write("抓到的欄位名稱:", df.columns.tolist())
        
        # --- 修正點：改用 iloc (位置) 來選欄位，比較不會因為字串有空白而報錯 ---
        # 通常 Dataroma 的順序是：Stock(0), Symbol(1), % of Portfolio(2), Share Count(3), % Change(4), Reported Price(5)...
        # 我們只取我們需要的欄位
        
        # 建立一個新的乾淨 DataFrame
        clean_df = pd.DataFrame()
        clean_df['Company'] = df.iloc[:, 0]       # 第 1 欄：公司名稱
        clean_df['Ticker'] = df.iloc[:, 1]        # 第 2 欄：股票代號
        clean_df['Portfolio_Pct'] = df.iloc[:, 2] # 第 3 欄：佔比
        clean_df['Shares'] = df.iloc[:, 3]        # 第 4 欄：股數
        clean_df['Cost_Price'] = df.iloc[:, 5]    # 第 6 欄：原本的價格 (Reported Price)
        
        # 資料清理
        # 把佔比的 % 符號拿掉，轉成數字
        clean_df['Portfolio_Pct'] = clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False)
        clean_df['Portfolio_Pct'] = pd.to_numeric(clean_df['Portfolio_Pct'], errors='coerce')
        
        return clean_df

    except Exception as e:
        st.error(f"抓取數據失敗: {e}")
        # 如果失敗，回傳空的 DataFrame 防止程式崩潰
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
