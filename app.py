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
st.markdown("數據來源：HedgeFollow (13F Filings) & Yahoo Finance | 自動繞過 IP 封鎖")
st.markdown("---")

# ---------------------------------------------------------
# 1. 爬蟲函數：使用 HedgeFollow (抗封鎖版)
# ---------------------------------------------------------
@st.cache_data(ttl=24*3600)
def get_buffett_portfolio():
    # 改用 HedgeFollow，這個網站對雲端主機的爬蟲比較友善
    url = "https://hedgefollow.com/funds/Berkshire+Hathaway"
    
    # 偽裝成一般的瀏覽器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        # 檢查是否被擋
        if response.status_code != 200:
            st.error(f"網站拒絕連線 (Code: {response.status_code})，可能需要更換來源。")
            return pd.DataFrame()

        # 嘗試讀取所有表格
        dfs = pd.read_html(response.text)
        
        # 智慧尋找：找出包含 'Ticker' 欄位的那個表格
        df = None
        for table in dfs:
            # 轉成小寫比對比較保險
            cols = [c.lower() for c in table.columns]
            if 'ticker' in cols:
                df = table
                break
        
        if df is None:
            st.warning("抓到了網頁但找不到持股表格，網站結構可能改變。")
            return pd.DataFrame()

        # --- 整理欄位 ---
        clean_df = pd.DataFrame()
        
        # HedgeFollow 的欄位名稱通常是 'Ticker', 'Company Name', 'Portfolio %'
        # 我們用名稱來對應比較安全
        clean_df['Ticker'] = df['Ticker']
        clean_df['Company'] = df['Company Name']
        
        # 處理百分比 (名稱可能是 'Portfolio %' 或 '% Portfolio')
        pct_col = [c for c in df.columns if '%' in c]
        if pct_col:
            clean_df['Portfolio_Pct'] = df[pct_col[0]]
        else:
            clean_df['Portfolio_Pct'] = 0

        # --- 數據清理 ---
        # 1. 轉數值
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), 
            errors='coerce'
        )
        
        # 2. 修正代號 (BRK.B -> BRK-B)
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False).str.strip()

        return clean_df

    except Exception as e:
        st.error(f"爬蟲發生錯誤: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 2. 股價函數 (穩定版)
# ---------------------------------------------------------
def get_live_prices(tickers):
    if not tickers:
        return {}
    
    # 過濾掉怪異的代號
    tickers = [x for x in tickers if isinstance(x, str) and len(x) > 0]
    
    try:
        # 下載數據
        data = yf.download(tickers, period="1d", group_by='ticker', threads=True, auto_adjust=True)
    except Exception as e:
        st.error(f"Yahoo Finance 連線失敗: {e}")
        return {}
    
    prices = {}
    
    # 處理單檔
    if len(tickers) == 1:
        t = tickers[0]
        try:
            current = data['Close'].iloc[-1]
            prev = data['Open'].iloc[-1]
            prices[t] = {'Price': current, 'Change_Pct': ((current - prev)/prev)*100}
        except:
            prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
    
    # 處理多檔
    else:
        for t in tickers:
            try:
                # 檢查是否有該股票的數據
                if t in data.columns.levels[0]:
                    stock = data[t]
                    if not stock.empty:
                        # 處理 NaN
                        current = stock['Close'].iloc[-1]
                        prev = stock['Open'].iloc[-1]
                        
                        if pd.isna(current): current = 0.0
                        if pd.isna(prev) or prev == 0: prev = current if current != 0 else 1.0
                        
                        prices[t] = {
                            'Price': current,
                            'Change_Pct': ((current - prev) / prev) * 100
                        }
                    else:
                        prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
                else:
                    prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
            except:
                prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
            
    return prices

# ---------------------------------------------------------
# 3. 主程式邏輯
# ---------------------------------------------------------
with st.spinner('正在連線 HedgeFollow 取得最新持股名單...'):
    df = get_buffett_portfolio()

if not df.empty:
    with st.sidebar:
        st.header("⚙️ 設定")
        top_n = st.slider("顯示前幾大持股?", 3, 50, 10)
        st.info("已切換至 HedgeFollow 數據源以確保連線穩定。")

    # 取前 N 大
    df_top = df.head(top_n).copy()
    ticker_list = df_top['Ticker'].tolist()
    
    # 抓取股價
    with st.spinner(f'正在抓取 {len(ticker_list)} 檔股票的即時報價...'):
        price_data = get_live_prices(ticker_list)
    
    # 合併
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0.0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0.0))
    
    # -----------------------------------------------------
    # 4. 顯示儀表板
    # -----------------------------------------------------
    
    # 顯示前三名
    col1, col2, col3 = st.columns(3)
    cols = [col1, col2, col3]
    for i in range(min(3, len(df_top))):
        row = df_top.iloc[i]
        cols[i].metric(
            label=f"#{i+1} {row['Ticker']}",
            value=f"${row['Current_Price']:.2f}",
            delta=f"{row['Day_Change_%']:.2f}%"
        )

    col_chart, col_table = st.columns([1, 1.5])
    
    with col_chart:
        st.subheader("權重分佈")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.subheader("持股詳細清單")
        def highlight_change(val):
            color = '#ff4b4b' if val < 0 else '#3bd671'
            return f'color: {color}'

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
    st.error("⚠️ 無法取得數據。可能是網站結構改變或暫時性連線問題。")
