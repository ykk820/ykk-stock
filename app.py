import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px

# ---------------------------------------------------------
# 設定網頁
# ---------------------------------------------------------
st.set_page_config(page_title="大師持股追蹤器", layout="wide")
st.title("🧠 Investment Gurus Tracker")
st.markdown("追蹤對象：巴菲特 (穩健) | Ackman (集中/Google) | Burry (反骨) | Marks (週期哲學)")
st.markdown("---")

# ---------------------------------------------------------
# 0. 設定大師名單與資料來源
# ---------------------------------------------------------
GURUS = {
    "Warren Buffett (Berkshire)": {
        "stockcircle": "https://stockcircle.com/portfolio/warren-buffett",
        "hedgefollow": "https://hedgefollow.com/funds/Berkshire+Hathaway",
        "fallback_tickers": ['AAPL', 'BAC', 'AXP', 'KO', 'CVX']
    },
    "Bill Ackman (Pershing Square)": {
        "stockcircle": "https://stockcircle.com/portfolio/bill-ackman",
        "hedgefollow": "https://hedgefollow.com/funds/Pershing+Square+Capital+Management",
        "fallback_tickers": ['GOOGL', 'CMG', 'HLT', 'QSR', 'HHC'] # Ackman 喜歡 Google & 餐飲
    },
    "Michael Burry (Scion Asset)": {
        "stockcircle": "https://stockcircle.com/portfolio/michael-burry",
        "hedgefollow": "https://hedgefollow.com/funds/Scion+Asset+Management",
        "fallback_tickers": ['JD', 'BABA', 'REAL', 'CI', 'BKNG'] # Burry 常換股，這是常見名單
    },
    "Howard Marks (Oaktree)": {
        "stockcircle": "https://stockcircle.com/portfolio/howard-marks",
        "hedgefollow": "https://hedgefollow.com/funds/Oaktree+Capital+Management+Lp",
        "fallback_tickers": ['TRMD', 'VIST', 'SBLK', 'PGRE', 'INFY']
    }
}

# ---------------------------------------------------------
# 1. 爬蟲模組 (參數化)
# ---------------------------------------------------------

def scrape_stockcircle(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        dfs = pd.read_html(response.text)
        
        df = None
        for table in dfs:
            if 'Symbol' in table.columns:
                df = table
                break
        
        if df is None: return None
        
        clean_df = pd.DataFrame()
        clean_df['Ticker'] = df['Symbol']
        clean_df['Company'] = df['Name']
        clean_df['Portfolio_Pct'] = df['Portfolio %']
        
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), errors='coerce'
        )
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False)
        
        return clean_df
    except:
        return None

def scrape_hedgefollow(url):
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
        
        pct_col = [c for c in df.columns if '%' in c][0]
        clean_df['Portfolio_Pct'] = df[pct_col]
        
        clean_df['Portfolio_Pct'] = pd.to_numeric(
            clean_df['Portfolio_Pct'].astype(str).str.replace('%', '', regex=False), errors='coerce'
        )
        clean_df['Ticker'] = clean_df['Ticker'].astype(str).str.replace('.', '-', regex=False)
        return clean_df
    except:
        return None

# 產生各個大師的備用數據 (當爬蟲都失敗時)
def get_fallback_data(guru_name):
    st.toast(f"⚠️ {guru_name} 爬蟲受阻，啟用備份數據", icon="🛡️")
    tickers = GURUS[guru_name]['fallback_tickers']
    # 這裡只簡單生成清單，權重隨意分配
    data = {
        'Ticker': tickers,
        'Company': [f"{t} (Fallback Data)" for t in tickers],
        'Portfolio_Pct': [20.0] * len(tickers) 
    }
    return pd.DataFrame(data)

@st.cache_data(ttl=3600)
def get_guru_portfolio(guru_key):
    urls = GURUS[guru_key]
    
    # 策略 1: StockCircle
    df = scrape_stockcircle(urls['stockcircle'])
    if df is not None and not df.empty:
        return df
    
    # 策略 2: HedgeFollow
    df = scrape_hedgefollow(urls['hedgefollow'])
    if df is not None and not df.empty:
        return df
    
    # 策略 3: Fallback
    return get_fallback_data(guru_key)

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
# 3. 主程式 UI 邏輯
# ---------------------------------------------------------

# 側邊欄：選擇大師
with st.sidebar:
    st.header("🔍 選擇投資大師")
    selected_guru = st.selectbox("請選擇你要追蹤的對象：", list(GURUS.keys()))
    
    st.info(f"正在分析 {selected_guru.split('(')[0]} 的最新持股...")

# 執行資料獲取
with st.spinner(f'正在連線數據源獲取 {selected_guru} 持股...'):
    df = get_guru_portfolio(selected_guru)

if not df.empty:
    with st.sidebar:
        st.divider()
        top_n = st.slider("顯示前幾大持股?", 3, len(df), 10)

    # 取前 N 大
    df_top = df.head(top_n).copy()
    ticker_list = df_top['Ticker'].tolist()
    
    with st.spinner('正在抓取即時股價...'):
        price_data = get_live_prices(ticker_list)
    
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0.0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0.0))
    
    # --- 顯示區 ---
    
    # 標題區塊
    st.subheader(f"📊 {selected_guru}")
    
    # 指標卡片 (Top 3)
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
        st.markdown("#### 資金權重分佈")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
        
    with col_table:
        st.markdown(f"#### 前 {top_n} 大持股清單")
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
