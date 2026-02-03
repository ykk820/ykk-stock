import streamlit as st
import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timedelta
import openai

# --- 1. 設定與邏輯資料庫 ---
st.set_page_config(page_title="Moat Hunter v18 (AI Strategist)", layout="wide")
st.title("🛡️ Moat Hunter v18 (AI 首席策略官)")
st.markdown("### 策略：OpenAI 智能解讀 + 2026 升降息行事曆")

# --- 2. 內建 2026 財經行事曆 (Hardcoded Data) ---
CALENDAR_DATA = {
    "FOMC_MEETINGS": [ # 利率決策會議 (星號代表有經濟預測 SEP)
        {"date": "2026-01-28", "type": "利率決策", "note": "已結束"},
        {"date": "2026-03-18", "type": "🔥 利率決策 + SEP", "note": "季度經濟預測 (重點)"},
        {"date": "2026-04-29", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-06-17", "type": "🔥 利率決策 + SEP", "note": "季度經濟預測 (重點)"},
        {"date": "2026-07-29", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-09-16", "type": "🔥 利率決策 + SEP", "note": "季度經濟預測 (重點)"},
        {"date": "2026-10-28", "type": "利率決策", "note": "常規會議"},
        {"date": "2026-12-09", "type": "🔥 利率決策 + SEP", "note": "年終會議"}
    ],
    "HOLIDAYS": [ # 美股休市日
        {"date": "2026-01-01", "name": "元旦"},
        {"date": "2026-01-19", "name": "馬丁路德金紀念日"},
        {"date": "2026-02-16", "name": "總統日"},
        {"date": "2026-04-03", "name": "耶穌受難日"},
        {"date": "2026-05-25", "name": "陣亡將士紀念日"},
        {"date": "2026-06-19", "name": "六月節"},
        {"date": "2026-07-03", "name": "獨立紀念日(補假)"},
        {"date": "2026-09-07", "name": "勞動節"},
        {"date": "2026-11-26", "name": "感恩節"},
        {"date": "2026-12-25", "name": "聖誕節"}
    ]
}

# 趨勢板塊邏輯
TREND_THEMES = {
    "🔥 自選監控名單": [], 
    "📊 指數型 ETF": {"logic": "大盤與高股息", "tickers": ['VOO', 'QQQ', 'SCHD', 'TLT', 'SMH']},
    "⚡️ AI 電力 (核能)": {"logic": "AI 資料中心基載電力", "tickers": ['CEG', 'VST', 'NEE', 'DUK', 'CCJ']},
    "📦 供應鏈重組": {"logic": "製造業回流自動化", "tickers": ['PLD', 'ROK', 'ZBRA', 'ETN', 'HON']},
    "🧠 AI 基礎建設": {"logic": "晶片與硬體", "tickers": ['NVDA', 'TSM', 'AVGO', 'AMD', 'MSFT']},
    "🛡️ 國防軍工": {"logic": "地緣政治風險", "tickers": ['LMT', 'RTX', 'NOC', 'GD']},
    "💰 金融護城河": {"logic": "抗通膨與支付", "tickers": ['V', 'MA', 'JPM', 'BLK', 'SPGI']},
    "🛒 抗衰退堡壘": {"logic": "必須消費", "tickers": ['COST', 'KO', 'PG', 'PEP', 'MCD']}
}

KNOWN_ETFS = ['VOO', 'SPY', 'QQQ', 'IVV', 'VTI', 'VT', 'SCHD', 'TLT', 'SOXX', 'SMH', 'XLK', 'XLE', 'XLV', 'XLF', 'TQQQ', 'SOXL']

# --- 3. 初始化 Session ---
if 'watchlist' not in st.session_state: st.session_state.watchlist = ['VOO', 'AAPL'] 
if 'ai_response' not in st.session_state: st.session_state.ai_response = None # 儲存 AI 回答避免重刷消失

# --- 4. 側邊欄：設定與 API ---
st.sidebar.header("🤖 AI 策略官設定")
api_key = st.sidebar.text_input("輸入 OpenAI API Key:", type="password", placeholder="sk-...")

st.sidebar.header("🌍 選擇戰場")
selected_theme = st.sidebar.selectbox("趨勢板塊:", list(TREND_THEMES.keys()))

# 處理名單邏輯 (略縮減以節省篇幅，功能不變)
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

# --- 5. 數據獲取函式 ---
@st.cache_data(ttl=300)
def get_macro_environment():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_change = ((tnx_curr - tnx['Close'].iloc[-2]) / tnx['Close'].iloc[-2]) * 100 
        return {"vix": vix, "tnx_yield": tnx_curr, "tnx_change": tnx_change}
    except: return {"vix": 20, "tnx_yield": 4.0, "tnx_change": 0}

def get_next_fomc():
    today = datetime.now().date()
    for meeting in CALENDAR_DATA["FOMC_MEETINGS"]:
        m_date = datetime.strptime(meeting["date"], "%Y-%m-%d").date()
        if m_date >= today:
            days_left = (m_date - today).days
            return meeting, days_left
    return None, 0

# --- 6. AI 分析函式 (核心新功能) ---
def ask_ai_strategist(api_key, macro, fomc_info, df_stock, df_etf):
    client = openai.OpenAI(api_key=api_key)
    
    # 準備餵給 AI 的資料摘要
    top_picks = []
    if not df_stock.empty:
        top_picks += df_stock.head(3)[['代號', '分數', '評分原因']].to_dict('records')
    if not df_etf.empty:
        top_picks += df_etf.head(2)[['代號', '分數', '評分原因']].to_dict('records')
        
    prompt = f"""
    你現在是一位華爾街頂級避險基金的首席策略官。請根據以下數據，用繁體中文為我撰寫一份簡短有力的「盤前戰略簡報」。
    
    【宏觀環境】
    - 恐慌指數 (VIX): {macro['vix']:.2f} (若>20為緊張, >30為恐慌)
    - 10年美債殖利率: {macro['tnx_yield']:.2f}% (單日變化 {macro['tnx_change']:.2f}%)
    - 下次 FOMC 會議: {fomc_info[0]['date']} ({fomc_info[0]['type']})，距離現在還有 {fomc_info[1]} 天。
    
    【系統篩選出的高分標的 (Moat Hunter)】
    {top_picks}
    
    【你的任務】
    1.解讀宏觀情緒：現在市場是貪婪還是恐慌？升息預期如何？
    2.操作建議：針對上述高分標的，結合宏觀環境，給出具體建議（例如：VIX過高建議分批買入ETF，或殖利率暴衝建議避開科技股）。
    3.語氣：專業、冷靜、果斷，像巴菲特或霍華馬克斯的風格。不要講廢話。
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # 或 gpt-4o
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 思考失敗: {str(e)}"

# --- 7. 評分邏輯 (保留 v17 雙軌制) ---
def score_company(rsi, peg, pe, roe, de, fcf, change, macro):
    score = 50
    details = []
    if macro['vix'] > 30: score += 20; details.append("🩸恐慌VIX")
    if macro['tnx_change'] > 3.0: score += 15; details.append("🦅升息預期")
    if roe > 15: score += 10; details.append("✅ROE優")
    elif roe < 5: score -= 15; details.append("❌ROE低")
    if de > 2.5: score -= 20; details.append("💀高負債")
    if fcf <= 0: score -= 20; details.append("💸燒錢")
    if peg > 0 and peg < 1.2: score += 15; details.append("💎PEG低估")
    if pe > 0 and pe < 20: score += 10; details.append("💰PE便宜")
    if rsi < 30: score += 15; details.append("📉超賣")
    if change < -2.0: score += 10; details.append("🔥大跌")
    return max(0, min(100, score)), " ".join(details)

def score_etf(rsi, change, drawdown, price, ma200, macro):
    score = 50
    details = []
    if macro['vix'] > 30: score += 30; details.append("🩸極度恐慌")
    elif macro['vix'] > 20: score += 15; details.append("😰市場緊張")
    if drawdown < -20: score += 25; details.append("🐻熊市價")
    elif drawdown < -10: score += 15; details.append("📉修正價")
    elif drawdown > -2: score -= 10; details.append("🏔️高點勿追")
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
                    peg = info.get('pegRatio', 0)
                    pe = info.get('trailingPE', 0)
                    roe = info.get('returnOnEquity', 0)
                    if roe: roe *= 100
                    de = info.get('debtToEquity', 0)
                    if de: de /= 100
                    fcf = info.get('freeCashflow', 0)
                    score, reason = score_company(rsi_val, peg, pe, roe or 0, de or 0, fcf or 0, change, macro)
                    stock_list.append({"代號": ticker, "現價": f"${curr:.2f}", "分數": int(score), "ROE": f"{roe:.1f}%" if roe else "-", "評分原因": reason})
            time.sleep(0.1)
        except: pass
        progress.progress((i + 1) / len(tickers))
    
    df_s = pd.DataFrame(stock_list)
    if not df_s.empty: df_s = df_s.sort_values(by="分數", ascending=False)
    df_e = pd.DataFrame(etf_list)
    if not df_e.empty: df_e = df_e.sort_values(by="分數", ascending=False)
    return df_s, df_e, macro

# --- 8. 主介面 ---
# A. 行事曆區塊
next_meeting, days_left = get_next_fomc()
col_cal1, col_cal2 = st.columns([2, 1])
with col_cal1:
    if next_meeting:
        st.info(f"📅 **距離下次利率決策 ({next_meeting['date']}) 還有 {days_left} 天**\n\n備註：{next_meeting['note']}")
    else:
        st.success("2026 年利率會議已全部結束。")
with col_cal2:
    with st.expander("查看 2026 完整行事曆"):
        st.write("**FOMC 會議時間**")
        st.table(pd.DataFrame(CALENDAR_DATA["FOMC_MEETINGS"]).set_index("date"))
        st.write("**美股休市日**")
        st.table(pd.DataFrame(CALENDAR_DATA["HOLIDAYS"]).set_index("date"))

# B. 掃描與分析
if st.button('🚀 執行全域掃描'):
    with st.spinner(f'正在分析 {len(target_tickers)} 支標的...'):
        df_stock, df_etf, macro = get_market_data(target_tickers)
        
        # 1. 宏觀數據
        c1, c2 = st.columns(2)
        c1.metric("VIX 恐慌指數", f"{macro['vix']:.2f}", delta="適合買ETF" if macro['vix']>30 else "平穩", delta_color="inverse")
        c2.metric("10年債 (鷹派指標)", f"{macro['tnx_yield']:.2f}%", f"{macro['tnx_change']:.2f}%", delta_color="inverse")

        # 2. AI 策略官報告
        if api_key:
            with st.spinner("🤖 AI 正在撰寫策略報告..."):
                strategy_report = ask_ai_strategist(api_key, macro, (next_meeting, days_left), df_stock, df_etf)
                st.session_state.ai_response = strategy_report
        
        if st.session_state.ai_response:
            st.markdown("---")
            st.markdown(f"### 🤖 AI 首席策略官觀點\n{st.session_state.ai_response}")
            st.markdown("---")
        elif not api_key:
            st.warning("⚠️ 想要 AI 幫你寫總結？請在左側輸入 OpenAI API Key。")

        # 3. 顯示表格
        def highlight(val):
            if val >= 80: return 'background-color: #28a745; color: white'
            if val >= 60: return 'background-color: #d4edda; color: black'
            return ''

        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("🏢 企業個股 (看財報)")
            if not df_stock.empty: st.dataframe(df_stock.style.map(highlight, subset=['分數']))
            else: st.write("無個股數據")
        with col_right:
            st.subheader("📊 指數/ETF (看回檔)")
            if not df_etf.empty: st.dataframe(df_etf.style.map(highlight, subset=['分數']))
            else: st.write("無 ETF 數據")
