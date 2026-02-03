import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px

# ---------------------------------------------------------
# 設定網頁
# ---------------------------------------------------------
st.set_page_config(page_title="巴菲特持股追蹤器", layout="wide")
st.title("💰 Warren Buffett's Portfolio Tracker")
st.markdown("數據來源：多重備援系統 (StockCircle / HedgeFollow / Fallback) | 自動切換")
st.markdown("---")

# ---------------------------------------------------------
# 1. 數據獲取模組 (多重來源)
# ---------------------------------------------------------

# 來源 A: StockCircle (通常對爬蟲較友善)
def scrape_stockcircle():
    url = "https://stockcircle.com/portfolio/warren-buffett"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        dfs = pd.read_html(response.text)
        
        # 尋找包含 'Symbol' 的表格
        df = None
        for table in dfs:
            if 'Symbol' in table.columns:
                df = table
                break
        
        if df is None: return None
        
        # 整理欄位
        clean_df = pd.DataFrame()
        clean_df['Ticker'] = df['Symbol']
        clean_df['Company'] = df['Name']
        clean_df['Portfolio_Pct'] = df['Portfolio %']
        
        # 格式清理
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), errors='coerce'
        )
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False)
        
        return clean_df
    except:
        return None

# 來源 B: HedgeFollow (備用)
def scrape_hedgefollow():
    url = "https://hedgefollow.com/funds/Berkshire+Hathaway"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        dfs = pd.read_html(response.text)
        
        df = None
        for table in dfs:
            cols = [c.lower() for c in table.columns]
            if 'ticker' in cols:
                df = table
                break
        
        if df is None: return None
        
        clean_df = pd.DataFrame()
        clean_df['Ticker'] = df['Ticker']
        clean_df['Company'] = df['Company Name']
        # 尋找 % 欄位
        pct_col = [c for c in df.columns if '%' in c][0]
        clean_df['Portfolio_Pct'] = df[pct_col]
        
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), errors='coerce'
        )
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False)
        return clean_df
    except:
        return None

# 來源 C: 寫死備份數據 (最後防線，確保網站一定能跑)
def get_fallback_data():
    st.toast("⚠️ 爬蟲被擋，已切換至備份數據模式", icon="🛡️")
    data = {
        'Ticker': ['AAPL', 'BAC', 'AXP', 'KO', 'CVX', 'OXY', 'KHC', 'MCO', 'CB', 'DVA'],
        'Company': ['Apple Inc.', 'Bank of America', 'American Express', 'Coca-Cola', 'Chevron', 'Occidental Petroleum', 'Kraft Heinz', "Moody's", 'Chubb Ltd', 'DaVita'],
        'Portfolio_Pct': [40.5, 11.8, 10.4, 7.3, 5.1, 4.2, 3.1, 2.9, 2.0, 1.0] # 估計值
    }
    return pd.DataFrame(data)

@st.cache_data(ttl=3600)
def get_buffett_portfolio():
    # 策略：嘗試 A -> 失敗試 B -> 失敗用 C
    df = scrape_stockcircle()
    if df is not None and not df.empty:
        return df
    
    df = scrape_hedgefollow()
    if df is not None and not df.empty:
        return df
    
    return get_fallback_data()

# ---------------------------------------------------------
# 2. 股價函數
# ---------------------------------------------------------
def get_live_prices(tickers):
    if not tickers: return {}
    tickers = [x for x in tickers if isinstance(x, str) and len(x)>0]
    
    try:
        data = yf.download(tickers, period="1d", group_by='ticker', threads=True, auto_adjust=True)
    except:
        return {}
    
    prices = {}
    if len(tickers) == 1:
        t = tickers[0]
        try:
            current = data['Close'].iloc[-1]
            prev = data['Open'].iloc[-1]
            prices[t] = {'Price': current, 'Change_Pct': ((current - prev)/prev)*100}
        except:
            prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
    else:
        for t in tickers:
            try:
                if t in data.columns.levels[0]:
                    current = data[t]['Close'].iloc[-1]
                    prev = data[t]['Open'].iloc[-1]
                    if pd.isna(current): current = 0.0
                    if pd.isna(prev) or prev == 0: prev = current if current!=0 else 1.0
                    prices[t] = {'Price': current, 'Change_Pct': ((current - prev)/prev)*100}
                else:
                    prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
            except:
                prices[t] = {'Price': 0.0, 'Change_Pct': 0.0}
    return prices

# ---------------------------------------------------------
# 3. 主程式
# ---------------------------------------------------------
with st.spinner('正在連線多重數據源...'):
    df = get_buffett_portfolio()

if not df.empty:
    with st.sidebar:
        st.header("⚙️ 設定")
        top_n = st.slider("顯示前幾大持股?", 3, len(df), 10)

    # 取前 N 大
    df_top = df.head(top_n).copy()
    ticker_list = df_top['Ticker'].tolist()
    
    with st.spinner('正在抓取即時股價...'):
        price_data = get_live_prices(ticker_list)
    
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0.0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0.0))
    
    # --- UI 顯示 ---
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
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.subheader("持股清單")
        def highlight_change(val):
            color = '#ff4b4b' if val < 0 else '#3bd671'
            return f'color: {color}'

        st.dataframe(
            df_top[['Ticker', 'Company', 'Portfolio_Pct', 'Current_Price', 'Day_Change_%']]
            .style.map(highlight_change, subset=['Day_Change_%'])
            .format({"Current_Price": "${:.2f}", "Day_Change_%": "{:.2f}%", "Portfolio_Pct": "{:.2f}%"}),
            height=400,
            use_container_width=True
        )
else:
    st.error("所有數據源皆失效，請檢查網路狀態。")
