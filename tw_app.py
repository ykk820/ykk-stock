import streamlit as st
import yfinance as yf
import pandas as pd
import time
import openai
import math

st.set_page_config(page_title="🇹🇼 Moat Hunter (TW)", layout="wide")
st.title("🇹🇼 Moat Hunter (台股特戰版)")
st.markdown("### 策略：殖利率 + 匯率外資 + 葛拉漢")

TREND_THEMES = {
    "🔥 自選監控": [], 
    "🏆 權值股": {"logic": "台積/聯發科/鴻海", "tickers": ['2330.TW', '2454.TW', '2317.TW']},
    "🤖 AI 伺服器": {"logic": "廣達/緯創/技嘉", "tickers": ['2382.TW', '3231.TW', '2376.TW']},
    "💰 高股息": {"logic": "存股族最愛", "tickers": ['0056.TW', '00878.TW', '00929.TW', '00919.TW']},
    "🏦 金融": {"logic": "抗跌領息", "tickers": ['2881.TW', '2882.TW', '2886.TW']}
}

if 'watchlist_tw' not in st.session_state: st.session_state.watchlist_tw = ['2330.TW', '0050.TW'] 
if 'ai_response_tw' not in st.session_state: st.session_state.ai_response_tw = None

st.sidebar.header("🇹🇼 設定")
api_key = st.sidebar.text_input("OpenAI API Key:", type="password")
selected_theme = st.sidebar.selectbox("板塊:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控":
    st.sidebar.caption("代號需加 .TW (上市) 或 .TWO (上櫃)")
    new = st.sidebar.text_input("➕ 代號:").upper()
    if st.sidebar.button("新增") and new: 
        if new not in st.session_state.watchlist_tw: st.session_state.watchlist_tw.append(new)
    if st.session_state.watchlist_tw:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_tw)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_tw.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_tw
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]

@st.cache_data(ttl=300)
def get_tw_macro():
    try:
        twd = yf.Ticker("TWD=X").history(period="5d")
        rate = twd['Close'].iloc[-1]
        chg = ((rate - twd['Close'].iloc[-2])/twd['Close'].iloc[-2])*100
        sox = yf.Ticker("^SOX").history(period="5d")
        sox_chg = ((sox['Close'].iloc[-1]-sox['Close'].iloc[-2])/sox['Close'].iloc[-2])*100
        return {"twd": rate, "twd_chg": chg, "sox": sox_chg}
    except: return {"twd": 32.0, "twd_chg": 0, "sox": 0}

def calc_graham(info):
    try:
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        return math.sqrt(22.5 * eps * bvps) if eps > 0 and bvps > 0 else 0
    except: return 0

def ask_ai(api_key, macro, df_s, df_e):
    client = openai.OpenAI(api_key=api_key)
    picks = []
    if not df_s.empty: picks += df_s.head(3)[['代號','現價','殖利率','評分原因']].to_dict('records')
    prompt = f"""
    擔任台股操盤手。繁體中文。
    宏觀: USD/TWD {macro['twd']:.2f} (變動{macro['twd_chg']:.2f}%), 費半 {macro['sox']:.2f}%。
    精選: {picks}
    任務: 1.外資動向(匯率) 2.操作建議(存股/波段) 3.風險。
    """
    try:
        res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
        return res.choices[0].message.content
    except: return "AI 休息中"

def score_tw_stock(rsi, pe, yld, roe, change, margin, macro):
    score = 50; det = []
    if yld>6: score+=20; det.append("💰高殖利率")
    elif yld>4: score+=10; det.append("✅配息穩")
    if macro['twd_chg']>0.2: score-=5; det.append("⚠️匯率貶")
    if macro['sox']>1.5: score+=10; det.append("🚀費半攻")
    if margin>10: score+=15; det.append("🏰低估")
    if roe>15: score+=10; det.append("👑ROE優")
    if pe>0 and pe<12: score+=10; det.append("💎低PE")
    if rsi<30: score+=15; det.append("📉超賣")
    if change<-2.5: score+=10; det.append("🩸大跌")
    return max(0,min(100,score)), " ".join(det)

def score_tw_etf(rsi, yld, price, ma60, macro):
    score = 50; det = []
    if yld>7: score+=25; det.append("💰超高息")
    elif yld>5: score+=15; det.append("✅高息")
    if ma60>0 and price<ma60: score+=10; det.append("💎破季線")
    if rsi<30: score+=20; det.append("📉超賣")
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    mac = get_tw_macro()
    sl, el = [], []
    bar = st.progress(0)
    for i, t in enumerate(tickers):
        try:
            s = yf.Ticker(t)
            h = s.history(period="6mo")
            if len(h)>60:
                cur = h['Close'].iloc[-1]
                chg = ((cur-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100
                rsi = 100 - (100/(1 + (h['Close'].diff().where(lambda x: x>0,0).rolling(14).mean()/(-h['Close'].diff().where(lambda x: x<0,0).rolling(14).mean())).iloc[-1]))
                info = s.info
                is_etf = t.startswith("00")
                yld = (info.get('trailingAnnualDividendRate',0)/cur)*100 if cur>0 else 0
                
                if is_etf:
                    ma60 = h['Close'].rolling(60).mean().iloc[-1]
                    sc, re = score_tw_etf(rsi, yld, cur, ma60, mac)
                    el.append({"代號":t.replace(".TW",""), "現價":f"{cur:.1f}", "殖利率":f"{yld:.1f}%", "分數":int(sc), "原因":re})
                else:
                    g = calc_graham(info)
                    m = ((g-cur)/cur)*100 if g>0 else 0
                    pe=info.get('trailingPE',0); roe=(info.get('returnOnEquity',0) or 0)*100
                    sc, re = score_tw_stock(rsi, pe, yld, roe, chg, m, mac)
                    sl.append({"代號":t.replace(".TW",""), "現價":f"{cur:.1f}", "葛拉漢":f"{g:.1f}" if g>0 else "-", "殖利率":f"{yld:.1f}%", "分數":int(sc), "原因":re})
        except: pass
        bar.progress((i+1)/len(tickers))
    return pd.DataFrame(sl), pd.DataFrame(el), mac

c1,c2,c3 = st.columns(3)
if st.button('🚀 掃描台股'):
    ds, de, mac = get_data(target_tickers)
    c1.metric("USD/TWD", f"{mac['twd']:.2f}", f"{mac['twd_chg']:.2f}%", delta_color="inverse")
    c2.metric("費半", f"{mac['sox']:.2f}%")
    
    if api_key:
        with st.spinner("AI 分析中..."): st.session_state.ai_response_tw = ask_ai(api_key, mac, ds, de)
    if st.session_state.ai_response_tw: st.info(st.session_state.ai_response_tw)
    
    def hi(v): return 'background-color: #28a745' if v>=80 else 'background-color: #d4edda' if v>=60 else ''
    cl, cr = st.columns(2)
    with cl:
        st.subheader("🏢 個股"); 
        if not ds.empty: st.dataframe(ds.sort_values("分數",0).style.map(hi, subset=['分數']))
    with cr:
        st.subheader("📊 ETF"); 
        if not de.empty: st.dataframe(de.sort_values("分數",0).style.map(hi, subset=['分數']))