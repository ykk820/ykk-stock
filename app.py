import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px

# ---------------------------------------------------------
# 設定網頁標題
# ---------------------------------------------------------
st.set_page_config(page_title="巴菲特持股追蹤器", layout="wide")
st.title("💰 Warren Buffett's Portfolio Tracker")
st.markdown("數據來源：SEC 13F (Dataroma) & Yahoo Finance | 自動修正代號格式")
st.markdown("---")

# ---------------------------------------------------------
# 1. 爬蟲函數
# ---------------------------------------------------------
@st.cache_data(ttl=24*3600)
def get_buffett_portfolio():
    url = "https://www.dataroma.com/m/holdings.php?m=BRK"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers)
        dfs = pd.read_html(response.text)
        df = dfs[0]
        
        clean_df = pd.DataFrame()
        clean_df['Company'] = df.iloc[:, 0]
        clean_df['Ticker'] = df.iloc[:, 1]
        clean_df['Portfolio_Pct'] = df.iloc[:, 2]
        
        # 轉數值
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), 
            errors='coerce'
        )
        
        # 【關鍵修正】把代號中的 "." 換成 "-" (解決 BRK.B 抓不到的問題)
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False)
        
        # 去除空白
        clean_df['Ticker'] = clean_df['Ticker'].str.strip()

        return clean_df

    except Exception as e:
        st.error(f"數據抓取錯誤: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 股價函數 (增強版)
# ---------------------------------------------------------
def get_live_prices(tickers):
    if not tickers:
        return {}
    
    # 強制轉成 list 避免格式錯誤
    tickers = [x for x in tickers if isinstance(x, str)]
    
    try:
        # 下載數據 (使用 auto_adjust 修正除權息影響)
        data = yf.download(tickers, period="1d", group_by='ticker', threads=True, auto_adjust=True)
    except Exception as e:
        st.error(f"Yahoo Finance 連線失敗: {e}")
        return {}
    
    prices = {}
    
    # 處理單檔股票 (yfinance 格式不同)
    if len(tickers) == 1:
        ticker = tickers[0]
        try:
            # 單檔股票沒有第二層 index
            current = data['Close'].iloc[-1]
            prev = data['Open'].iloc[-1]
            prices[ticker] = {
                'Price': current,
                'Change_Pct': ((current - prev) / prev) * 100
            }
        except:
            prices[ticker] = {'Price': 0.0, 'Change_Pct': 0.0}
            
    # 處理多檔股票
    else:
        for ticker in tickers:
            try:
                # 檢查該 ticker 是否有資料
                if ticker in data.columns.levels[0]: 
                    stock_data = data[ticker]
                    # 確保不是空值
                    if not stock_data.empty and not pd.isna(stock_data['Close'].iloc[-1]):
                        current = stock_data['Close'].iloc[-1]
                        prev = stock_data['Open'].iloc[-1]
                        
                        # 防止開盤價為 0 導致除以零
                        if prev == 0: prev = current 
                        
                        prices[ticker] = {
                            'Price': current,
                            'Change_Pct': ((current - prev) / prev) * 100
                        }
                    else:
                        prices[ticker] = {'Price': 0.0, 'Change_Pct': 0.0}
                else:
                    prices[ticker] = {'Price': 0.0, 'Change_Pct': 0.0}
            except Exception:
                prices[ticker] = {'Price': 0.0, 'Change_Pct': 0.0}
            
    return prices

# ---------------------------------------------------------
# 3. 主程式
# ---------------------------------------------------------
df = get_buffett_portfolio()

if not df.empty:
    with st.sidebar:
        st.header("⚙️ 設定")
        top_n = st.slider("顯示前幾大持股?", 3, 50, 10)

    # 取前 N 大
    df_top = df.head(top_n).copy()
    ticker_list = df_top['Ticker'].tolist()
    
    # 顯示進度條讓你知道它在跑
    with st.spinner(f'正在抓取 {len(ticker_list)} 檔股票報價...'):
        price_data = get_live_prices(ticker_list)
    
    # 填入數據
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0.0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0.0))
    
    # -----------------------------------------------------
    # 4. 顯示
    # -----------------------------------------------------
    
    # 指標卡片
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
        st.subheader("權重分佈")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.subheader("持股清單")
        def highlight_change(val):
            color = '#ff4b4b' if val < 0 else '#3bd671'
            return f'color: {color}'

        # 顯示表格
        st.dataframe(
            df_top[['Ticker', 'Company', 'Portfolio_Pct', 'Current_Price', 'Day_Change_%']]
            .style.map(highlight_change, subset=['Day_Change_%'])
            .format({
                "Current_Price": "${:.2f}", 
                "Day_Change_%": "{:.2f}%", 
                "Portfolio_Pct": "{:.2f}%"
            }),
            height=400,
            use_container_width=True
        )
else:
    st.error("無法抓取 13F 數據。")
