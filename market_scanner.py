import streamlit as st
import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timedelta
import openai
import math

# --- 1. 設定與邏輯資料庫 ---
st.set_page_config(page_title="Moat Hunter v19 (Graham & Fed)", layout="wide")
st.title("🛡️ Moat Hunter v19 (全知價值版)")
st.markdown("### 策略：升降息機率 (ZQ=F) + 葛拉漢真實價值 + AI 策略官")

# 行事曆數據 (2026)
CALENDAR_DATA = {
    "FOMC_MEETINGS": [
        {"date": "2026-01-28", "type": "利率決策", "note": "已結束"},
        {"date": "2026-03-18", "type": "🔥 利率決策 + SEP", "note": "季度經濟預測"},
        {"date": "2026-04-29", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-06-17", "type": "🔥 利率決策 + SEP", "note": "重點會議"},
        {"date": "2026-07-29", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-09-16", "type": "🔥 利率決策 + SEP", "note": "重點會議"},
        {"date": "2026-10-28", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-12-09", "type": "🔥 利率決策 + SEP", "note": "年終會議"}
    ],
    "HOLIDAYS": [
        {"date": "2026-02-16", "name": "總統日"},
        {"date": "2026-04-03", "name": "耶穌受難日"},
        {"date": "2026-05-25", "name": "陣亡將士紀念日"},
        {"date": "2026-06-19", "name": "六月節"},
        {"date": "2026-09-07", "name": "勞動節"},
        {"date": "2026-11-26", "name": "感恩節"},
        {"date": "2026-12-25", "name": "聖誕節"}
    ]
}

TREND_THEMES = {
    "🔥 自選監控名單": [], 
    "📊 指數型 ETF": {"logic": "大盤/高股息/債券", "tickers": ['VOO', 'QQQ', 'SCHD', 'TLT', 'SMH']},
    "⚡️ AI 電力 (核能)": {"logic": "基載電力與公用事業", "tickers": ['CEG', 'VST', 'NEE', 'DUK', 'CCJ']},
    "📦 供應鏈重組": {"logic": "製造業回流自動化", "tickers": ['PLD', 'ROK', 'ZBRA', 'ETN', 'HON']},
    "🧠 AI 基礎建設": {"logic": "晶片/伺服器/軟體", "tickers": ['NVDA', 'TSM', 'AVGO', 'AMD', 'MSFT', 'PLTR']},
    "🛡️ 國防軍工": {"logic": "地緣政治風險", "tickers": ['LMT', 'RTX', 'NOC', 'GD']},
    "💰 金融護城河": {"logic": "抗通膨與支付", "tickers": ['V', 'MA', 'JPM', 'BLK', 'SPGI']},
    "🛒 抗衰退堡壘": {"logic": "必須消費品", "tickers": ['COST', 'KO', 'PG', 'PEP', 'MCD']}
}

KNOWN_ETFS = ['VOO', 'SPY', 'QQQ', 'IVV', 'VTI', 'VT', 'SCHD', 'TLT', 'SOXX', 'SMH', 'XLK', 'XLE', 'XLV', 'XLF', 'TQQQ', 'SOXL']

if 'watchlist' not in st.session_state: st.session_state.watchlist = ['VOO', 'AAPL'] 
if 'ai_response' not in st.session_state: st.session_state.ai_response = None

# --- 側邊欄 ---
st.sidebar.header("🤖 AI 策略官")
api_key = st.sidebar.text_input("輸入 OpenAI API Key:", type="password", placeholder="sk-...")

st.sidebar.header("🌍 選擇戰場")
selected_theme = st.sidebar.selectbox("趨勢板塊:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控名單":
    new_ticker = st.sidebar.text_input("➕ 新增代號:").upper()
    if st.sidebar.button("新增") and new_ticker: 
        if new_ticker not in st.session_state.watchlist: st.session_state.watchlist.append(new_ticker)
    if st.session_state.watchlist:
        rm_ticker = st.sidebar.selectbox("移除:", ["(選擇)"] + st.session_state.watchlist)
        if rm_ticker != "(選擇)" and st.sidebar.button("刪除"): 
            st.session_state.watchlist.remove(rm_ticker)
            st.rerun()
    target_tickers = st.session_state.watchlist
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]
    st.sidebar.info(f"💡 {TREND_THEMES[selected_theme]['logic']}")

# --- 核心數據函式 ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        # 1. 恐慌指數
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        
        # 2. 10年債 (鷹派指標)
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_change = ((tnx_curr - tnx['Close'].iloc[-2]) / tnx['Close'].iloc[-2]) * 100 

        # 3. 升降息預測 (聯邦基金期貨 ZQ=F)
        # 價格 = 100 - 隱含利率
        fed_futures = yf.Ticker("ZQ=F").history(period="5d")
        if not fed_futures.empty:
            last_price = fed_futures['Close'].iloc[-1]
            implied_rate = 100 - last_price
        else:
            implied_rate = 0.0 # 抓不到時的備案
            
        return {"vix": vix, "tnx_yield": tnx_curr, "tnx_change": tnx_change, "fed_implied_rate": implied_rate}
    except: return {"vix": 20, "tnx_yield": 4.0, "tnx_change": 0, "fed_implied_rate": 0}

def get_next_fomc():
    today = datetime.now().date()
    for meeting in CALENDAR_DATA["FOMC_MEETINGS"]:
        m_date = datetime.strptime(meeting["date"], "%Y-%m-%d").date()
        if m_date >= today:
            days_left = (m_date - today).days
            return meeting, days_left
    return None, 0

# --- 價值投資核心：葛拉漢估值 ---
def calculate_graham_value(info):
    try:
        # 葛拉漢公式：V = Sqrt(22.5 * EPS * BVPS)
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        
        if eps > 0 and bvps > 0:
            graham_value = math.sqrt(22.5 * eps * bvps)
            return graham_value
        else:
            return 0
    except:
        return 0

# --- AI 分析 ---
def ask_ai_strategist(api_key, macro, fomc_info, df_stock, df_etf):
    client = openai.OpenAI(api_key=api_key)
    
    # 準備摘要
    top_picks = []
    if not df_stock.empty:
        # 加入葛拉漢數據給 AI
        picks = df_stock.head(3)[['代號', '現價', '葛拉漢價', '評分原因']].to_dict('records')
        top_picks += picks
        
    prompt = f"""
    擔任華爾街價值投資策略師。用繁體中文簡報。
    
    【宏觀數據】
    - 市場隱含利率 (ZQ=F): {macro['fed_implied_rate']:.2f}% (這是市場押注的未來利率)
    - 10年美債: {macro['tnx_yield']:.2f}% (變化 {macro['tnx_change']:.2f}%)
    - VIX: {macro['vix']:.2f}
    - 下次 FOMC: {fomc_info[0]['date']} (剩 {fomc_info[1]} 天)
    
    【精選價值股 (Moat Hunter)】
    {top_picks}
    
    【任務】
    1. 利率解讀：市場隱含利率 vs 美債殖利率，暗示未來是升息還是降息？
    2. 價值分析：針對精選股的「現價」與「葛拉漢價」做比較，哪支有安全邊際？
    3. 給出明確操作建議 (買入/觀望/避險)。
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 思考失敗: {str(e)}"

# --- 評分系統 ---
def score_company(rsi, peg, pe, roe, de, fcf, change, safety_margin, macro):
    score = 50
    details = []
    
    # 宏觀
    if macro['vix'] > 30: score += 20; details.append("🩸恐慌VIX")
    
    # 價值 (New: 安全邊際)
    if safety_margin > 20: score += 20; details.append("🏰葛拉漢低估")
    elif safety_margin > 0: score += 10; details.append("💰低於價值")
    elif safety_margin < -50: score -= 20; details.append("💸溢價過高")

    # 品質
    if roe > 15: score += 10; details.append("✅ROE優")
    elif roe < 5: score -= 15; details.append("❌ROE低")
    if de > 2.5: score -= 20; details.append("💀高負債")
    if fcf <= 0: score -= 20; details.append("💸燒錢")
    
    # 技術
    if rsi < 30: score += 15; details.append("📉超賣")
    if change < -2.0: score += 10; details.append("🔥大跌")
    
    return max(0, min(100, score)), " ".join(details)

def score_etf(rsi, change, drawdown, price, ma200, macro):
    score = 50
    details = []
    if macro['vix'] > 30: score += 30; details.append("🩸極度恐慌")
    if drawdown < -20: score += 25; details.append("🐻熊市價")
    elif drawdown < -10: score += 15; details.append("📉修正價")
    if rsi < 30: score += 20; details.append("📉RSI超賣")
    if ma200 > 0 and price < ma200: score += 10; details.append("💎跌破年線")
    return max(0, min(100, score)), " ".join(details)

def get_market_data(tickers):
    macro = get_macro_environment()
    stock_list, etf_list = [], []
    progress = st.progress(0)
    
    for i, ticker in enumerate(tickers):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if len(hist) > 200:
                curr = hist['Close'].iloc[-1]
                change = ((curr - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
                
                # RSI
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1]

                info = stock.info
                is_etf = (ticker in KNOWN_ETFS) or (info.get('quoteType') == 'ETF')
                
                if is_etf:
                    high_52 = hist['Close'].max()
                    drawdown = ((curr - high_52) / high_52) * 100
                    ma200 = hist['Close'].rolling(200).mean().iloc[-1]
                    score, reason = score_etf(rsi_val, change, drawdown, curr, ma200, macro)
                    etf_list.append({"代號": ticker, "現價": f"${curr:.2f}", "分數": int(score), "回檔幅度": f"{drawdown:.1f}%", "評分原因": reason})
                else:
                    # 價值投資數據
                    peg = info.get('pegRatio', 0)
                    pe = info.get('trailingPE', 0)
                    roe = info.get('returnOnEquity', 0); roe = roe * 100 if roe else 0
                    de = info.get('debtToEquity', 0); de = de / 100 if de else 0
                    fcf = info.get('freeCashflow', 0)
                    
                    # 葛拉漢價值計算
                    graham_val = calculate_graham_value(info)
                    safety_margin = ((graham_val - curr) / curr) * 100 if graham_val > 0 else 0
                    
                    score, reason = score_company(rsi_val, peg, pe, roe, de, fcf, change, safety_margin, macro)
                    
                    stock_list.append({
                        "代號": ticker, 
                        "現價": f"${curr:.2f}", 
                        "葛拉漢價": f"${graham_val:.2f}" if graham_val > 0 else "-",
                        "安全邊際": f"{safety_margin:.1f}%",
                        "分數": int(score), 
                        "ROE": f"{roe:.1f}%", 
                        "評分原因": reason
                    })
            time.sleep(0.1)
        except: pass
        progress.progress((i + 1) / len(tickers))
    
    return pd.DataFrame(stock_list), pd.DataFrame(etf_list), macro

# --- 主介面 ---
next_meeting, days_left = get_next_fomc()

# 儀表板
col_mac1, col_mac2, col_mac3 = st.columns(3)

# 1. 升降息預測儀表
if st.button('🚀 掃描市場'):
    with st.spinner('正在分析價值與利率...'):
        df_stock, df_etf, macro = get_market_data(target_tickers)
        
        # 顯示利率預測
        implied_rate = macro['fed_implied_rate']
        rate_diff = implied_rate - 4.5 # 假設基準是 4.5% (可手動調整或抓取)
        rate_msg = "預期降息" if rate_diff < 0 else "預期升息"
        
        col_mac1.metric("市場隱含利率 (ZQ=F)", f"{implied_rate:.2f}%", f"{rate_msg}", delta_color="inverse")
        col_mac2.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", "越低越穩", delta_color="inverse")
        col_mac3.metric("下次 FOMC", f"{days_left} 天後", f"{next_meeting['date']}")

        st.markdown(f"**💡 利率解讀：** 聯邦基金期貨顯示市場押注的利率為 **{implied_rate:.2f}%**。若此數字低於當前利率，代表市場強烈預期**降息**。")

        # AI 報告
        if api_key:
            with st.spinner("🤖 AI 正在計算安全邊際..."):
                report = ask_ai_strategist(api_key, macro, (next_meeting, days_left), df_stock, df_etf)
                st.session_state.ai_response = report
        
        if st.session_state.ai_response:
            st.info(f"🤖 **AI 策略官報告：**\n\n{st.session_state.ai_response}")

        # 表格顯示
        def highlight(val):
            if val >= 80: return 'background-color: #28a745; color: white'
            if val >= 60: return 'background-color: #d4edda; color: black'
            return ''

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🏢 價值股 (葛拉漢估值)")
            if not df_stock.empty: 
                df_stock = df_stock.sort_values(by="分數", ascending=False)
                st.dataframe(df_stock.style.map(highlight, subset=['分數']))
            else: st.write("無數據")
        with c2:
            st.subheader("📊 ETF (回檔策略)")
            if not df_etf.empty: 
                df_etf = df_etf.sort_values(by="分數", ascending=False)
                st.dataframe(df_etf.style.map(highlight, subset=['分數']))
            else: st.write("無數據")
