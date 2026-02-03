import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px

# ---------------------------------------------------------
# 設定網頁標題與排版
# ---------------------------------------------------------
st.set_page_config(page_title="巴菲特持股追蹤器", layout="wide")

st.title("💰 Warren Buffett's Portfolio Tracker")
st.markdown("數據來源：SEC 13F (Dataroma) & Yahoo Finance | 自動化即時追蹤")
st.markdown("---")

# ---------------------------------------------------------
# 1. 爬蟲函數：抓取波克夏最新持股 (使用 iloc 防止欄位名稱錯誤)
# ---------------------------------------------------------
@st.cache_data(ttl=24*3600)
def get_buffett_portfolio():
    url = "https://www.dataroma.com/m/holdings.php?m=BRK"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        # 利用 Pandas 讀取網頁中的表格
        dfs = pd.read_html(response.text)
        df = dfs[0]
        
        # 建立乾淨的 DataFrame (使用 iloc 根據位置抓取，避免名稱變動報錯)
        # Dataroma 表格結構通常為: [Stock, Symbol, % Port, Shares, % Change, Value, Price...]
        clean_df = pd.DataFrame()
        clean_df['Company'] = df.iloc[:, 0]       # 第 1 欄：公司名
        clean_df['Ticker'] = df.iloc[:, 1]        # 第 2 欄：股票代號
        clean_df['Portfolio_Pct'] = df.iloc[:, 2] # 第 3 欄：佔比
        
        # 清理數據：轉為數值
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), 
            errors='coerce'
        )
        
        return clean_df

    except Exception as e:
        st.error(f"數據抓取發生錯誤: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 股價函數：取得即時價格與漲跌
# ---------------------------------------------------------
def get_live_prices(tickers):
    if not tickers:
        return {}
    
    # 下載數據
    data = yf.download(tickers, period="1d", group_by='ticker', threads=True)
    
    prices = {}
    for ticker in tickers:
        try:
            # 判斷回傳格式 (單檔 vs 多檔結構不同)
            if len(tickers) > 1:
                stock_data = data[ticker]
            else:
                stock_data = data
            
            # 確保有數據
            if not stock_data.empty:
                current_price = stock_data['Close'].iloc[-1]
                prev_close = stock_data['Open'].iloc[-1] # 簡易用開盤當作比較基準
                change_pct = ((current_price - prev_close) / prev_close) * 100
                
                prices[ticker] = {
                    'Price': current_price, 
                    'Change_Pct': change_pct
                }
            else:
                prices[ticker] = {'Price': 0, 'Change_Pct': 0}
                
        except Exception:
            prices[ticker] = {'Price': 0, 'Change_Pct': 0}
            
    return prices

# ---------------------------------------------------------
# 3. 主程式邏輯
# ---------------------------------------------------------
df = get_buffett_portfolio()

if not df.empty:
    # 側邊欄控制
    with st.sidebar:
        st.header("⚙️ 設定")
        top_n = st.slider("顯示前幾大持股?", min_value=3, max_value=50, value=10)
        st.info("此程式為自動爬取 Dataroma 最新一季 13F 報告，並結合 Yahoo Finance 即時報價。")

    # 取前 N 大
    df_top = df.head(top_n).copy()
    
    # 抓取即時股價
    ticker_list = df_top['Ticker'].tolist()
    
    with st.spinner('正在連線美股市場取得最新報價...'):
        price_data = get_live_prices(ticker_list)
    
    # 合併數據
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0))
    
    # -----------------------------------------------------
    # 4. 儀表板顯示區
    # -----------------------------------------------------
    
    # 顯示前三大持股卡片
    st.subheader("🔥 核心持股即時狀況")
    col1, col2, col3 = st.columns(3)
    cols = [col1, col2, col3]
    
    for i in range(min(3, len(df_top))):
        row = df_top.iloc[i]
        cols[i].metric(
            label=f"#{i+1} {row['Ticker']}",
            value=f"${row['Current_Price']:.2f}",
            delta=f"{row['Day_Change_%']:.2f}%"
        )

    # 圖表與表格
    col_chart, col_table = st.columns([1, 1.5])
    
    with col_chart:
        st.subheader("持股權重分佈")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.subheader(f"前 {top_n} 大持股清單")
        
        # 樣式設定：漲跌幅上色
        def highlight_change(val):
            color = '#ff4b4b' if val < 0 else '#3bd671' # 紅跌綠漲 (美股慣例可反過來)
            return f'color: {color}'

        display_cols = ['Ticker', 'Company', 'Portfolio_Pct', 'Current_Price', 'Day_Change_%']
        
        st.dataframe(
            df_top[display_cols].style.map(highlight_change, subset=['Day_Change_%'])
            .format({
                "Current_Price": "${:.2f}", 
                "Day_Change_%": "{:.2f}%", 
                "Portfolio_Pct": "{:.2f}%"
            }),
            height=400,
            use_container_width=True
        )

else:
    st.warning("⚠️ 無法讀取數據，請檢查 Dataroma 網站狀態或稍後再試。")
