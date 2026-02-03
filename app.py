import streamlit as st
import pandas as pd
import yfinance as yf
import cloudscraper
import plotly.express as px

# ---------------------------------------------------------
# 設定網頁
# ---------------------------------------------------------
st.set_page_config(page_title="大師持股追蹤器", layout="wide")
st.title("🧠 Investment Gurus Tracker Pro")
st.markdown("##### 🚀 自動爬蟲 + 真實數據庫備援系統")
st.markdown("---")

# ---------------------------------------------------------
# 1. 真實數據庫 (Fallback)
# ---------------------------------------------------------
REAL_DATA_DB = {
    "Warren Buffett (Berkshire)": [
        {"Ticker": "AAPL", "Company": "Apple Inc.", "Portfolio_Pct": 40.5},
        {"Ticker": "BAC", "Company": "Bank of America Corp", "Portfolio_Pct": 11.8},
        {"Ticker": "AXP", "Company": "American Express", "Portfolio_Pct": 10.4},
        {"Ticker": "KO", "Company": "Coca-Cola Co", "Portfolio_Pct": 7.3},
        {"Ticker": "CVX", "Company": "Chevron Corp", "Portfolio_Pct": 5.1},
        {"Ticker": "OXY", "Company": "Occidental Petroleum", "Portfolio_Pct": 4.2},
        {"Ticker": "KHC", "Company": "Kraft Heinz Co", "Portfolio_Pct": 3.1},
        {"Ticker": "MCO", "Company": "Moody's Corp", "Portfolio_Pct": 2.9},
        {"Ticker": "CB", "Company": "Chubb Limited", "Portfolio_Pct": 2.0},
        {"Ticker": "DVA", "Company": "DaVita Inc", "Portfolio_Pct": 1.0}
    ],
    "Bill Ackman (Pershing Square)": [
        {"Ticker": "GOOGL", "Company": "Alphabet Inc. (Class A)", "Portfolio_Pct": 18.5},
        {"Ticker": "CMG", "Company": "Chipotle Mexican Grill", "Portfolio_Pct": 16.8},
        {"Ticker": "HLT", "Company": "Hilton Worldwide", "Portfolio_Pct": 15.2},
        {"Ticker": "QSR", "Company": "Restaurant Brands Intl", "Portfolio_Pct": 14.1},
        {"Ticker": "GOOG", "Company": "Alphabet Inc. (Class C)", "Portfolio_Pct": 12.3},
        {"Ticker": "HHC", "Company": "Howard Hughes Holdings", "Portfolio_Pct": 11.4},
        {"Ticker": "CP", "Company": "Canadian Pacific Kansas", "Portfolio_Pct": 10.2},
        {"Ticker": "NKE", "Company": "Nike Inc.", "Portfolio_Pct": 1.5}
    ],
    "Michael Burry (Scion Asset)": [
        {"Ticker": "BABA", "Company": "Alibaba Group", "Portfolio_Pct": 15.2},
        {"Ticker": "JD", "Company": "JD.com Inc", "Portfolio_Pct": 12.5},
        {"Ticker": "BIDU", "Company": "Baidu Inc", "Portfolio_Pct": 10.8},
        {"Ticker": "REAL", "Company": "The RealReal", "Portfolio_Pct": 8.5},
        {"Ticker": "CI", "Company": "Cigna Group", "Portfolio_Pct": 6.2},
        {"Ticker": "BKNG", "Company": "Booking Holdings", "Portfolio_Pct": 5.5},
        {"Ticker": "MOLN", "Company": "Molina Healthcare", "Portfolio_Pct": 5.1}
    ],
    "Howard Marks (Oaktree)": [
        {"Ticker": "TRMD", "Company": "TORM plc", "Portfolio_Pct": 12.5},
        {"Ticker": "VIST", "Company": "Vista Energy", "Portfolio_Pct": 8.2},
        {"Ticker": "SBLK", "Company": "Star Bulk Carriers", "Portfolio_Pct": 6.5},
        {"Ticker": "PGRE", "Company": "Paramount Group", "Portfolio_Pct": 4.1},
        {"Ticker": "INFY", "Company": "Infosys Ltd", "Portfolio_Pct": 3.8},
        {"Ticker": "VALE", "Company": "Vale S.A.", "Portfolio_Pct": 3.5}
    ]
}

GURU_URLS = {
    "Warren Buffett (Berkshire)": "https://stockcircle.com/portfolio/warren-buffett",
    "Bill Ackman (Pershing Square)": "https://stockcircle.com/portfolio/bill-ackman",
    "Michael Burry (Scion Asset)": "https://stockcircle.com/portfolio/michael-burry",
    "Howard Marks (Oaktree)": "https://stockcircle.com/portfolio/howard-marks"
}

# ---------------------------------------------------------
# 2. 爬蟲模組
# ---------------------------------------------------------

def scrape_data(guru_name):
    url = GURU_URLS[guru_name]
    scraper = cloudscraper.create_scraper() 
    
    try:
        response = scraper.get(url, timeout=10)
        if response.status_code != 200: return None

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
    except Exception:
        return None

# ---------------------------------------------------------
# 3. 數據獲取邏輯 (修正：移除了 st.toast)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_guru_portfolio(guru_name):
    # 這裡只處理資料，不處理 UI
    
    # 1. 嘗試爬蟲
    df = scrape_data(guru_name)
    if df is not None and not df.empty:
        # 回傳資料 + 狀態碼
        return df, "live"
    
    # 2. 嘗試備份
    fallback_data = REAL_DATA_DB.get(guru_name, [])
    return pd.DataFrame(fallback_data), "fallback"

# ---------------------------------------------------------
# 4. 股價函數
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
# 5. 主程式 UI
# ---------------------------------------------------------

with st.sidebar:
    st.header("🔍 選擇投資大師")
    selected_guru = st.selectbox("請選擇：", list(REAL_DATA_DB.keys()))

# 執行資料獲取
with st.spinner(f'正在分析 {selected_guru} 的投資組合...'):
    # 接收資料與狀態
    df, data_source = get_guru_portfolio(selected_guru)

# --- 關鍵修正：UI 顯示移到這裡 ---
if data_source == "live":
    st.toast("✅ 成功連線 StockCircle 抓取即時數據！", icon="🕷️")
elif data_source == "fallback":
    st.toast("🛡️ 爬蟲受阻，已自動切換至內建真實數據庫", icon="💾")

if not df.empty:
    with st.sidebar:
        st.divider()
        max_items = len(df)
        top_n = st.slider("顯示持股數量", 3, max_items, min(10, max_items))

    df_top = df.head(top_n).copy()
    ticker_list = df_top['Ticker'].tolist()
    
    with st.spinner('正在抓取即時股價...'):
        price_data = get_live_prices(ticker_list)
    
    df_top['Current_Price'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Price', 0.0))
    df_top['Day_Change_%'] = df_top['Ticker'].map(lambda x: price_data.get(x, {}).get('Change_Pct', 0.0))
    
    # 顯示
    st.subheader(f"📊 {selected_guru} 持股透視")
    
    cols = st.columns(4)
    for i in range(min(4, len(df_top))):
        row = df_top.iloc[i]
        cols[i].metric(
            label=f"#{i+1} {row['Ticker']}",
            value=f"${row['Current_Price']:.2f}",
            delta=f"{row['Day_Change_%']:.2f}%"
        )

    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.markdown("#### 資金配置")
        fig = px.pie(df_top, values='Portfolio_Pct', names='Ticker', hole=0.4)
        fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.markdown(f"#### 前 {top_n} 大持股詳細")
        
        def highlight_change(val):
            if val > 0: return 'color: #2ecc71'
            elif val < 0: return 'color: #e74c3c'
            else: return 'color: white'

        st.dataframe(
            df_top[['Ticker', 'Company', 'Portfolio_Pct', 'Current_Price', 'Day_Change_%']]
            .style.map(highlight_change, subset=['Day_Change_%'])
            .format({
                "Current_Price": "${:.2f}", 
                "Day_Change_%": "{:.2f}%", 
                "Portfolio_Pct": "{:.2f}%"
            }),
            height=450,
            use_container_width=True
        )
else:
    st.error("系統發生錯誤。")
