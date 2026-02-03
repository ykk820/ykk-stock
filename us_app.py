import streamlit as st
import yfinance as yf
import pandas as pd
import time
from datetime import datetime
import openai
import math
import requests
import json

st.set_page_config(page_title="🇺🇸 Moat Hunter (Selector)", layout="wide")
st.title("🇺🇸 Moat Hunter (美股手動切換版)")
st.markdown("### 策略：巴菲特 (OpenAI) vs 伍德 (Gemini) + 模型自選")

# --- 1. 美股行事曆 ---
CALENDAR_DATA = {
    "FOMC": [
        {"date": "2026-03-18", "note": "🔥 利率決策 + SEP"},
        {"date": "2026-04-29", "note": "常規會議"},
        {"date": "2026-06-17", "note": "🔥 重點會議"}
    ]
}

TREND_THEMES = {
    "🔥 自選監控": [], 
    "📊 指數 ETF": {"logic": "大盤/債券", "tickers": ['VOO', 'QQQ', 'TLT', 'SMH']},
    "⚡️ AI 電力": {"logic": "基載電力", "tickers": ['CEG', 'VST', 'NEE', 'CCJ']},
    "🧠 AI 基建": {"logic": "晶片/軟體", "tickers": ['NVDA', 'TSM', 'AVGO', 'MSFT', 'PLTR']},
    "🛒 抗衰退": {"logic": "必須消費", "tickers": ['COST', 'KO', 'PEP', 'MCD']}
}
KNOWN_ETFS = ['VOO', 'QQQ', 'SPY', 'TLT', 'SMH', 'SOXX', 'XLK', 'SCHD']

if 'watchlist_us' not in st.session_state: st.session_state.watchlist_us = ['VOO', 'NVDA'] 
if 'ai_response_us_openai' not in st.session_state: st.session_state.ai_response_us_openai = None
if 'ai_response_us_gemini' not in st.session_state: st.session_state.ai_response_us_gemini = None

# --- 側邊欄設定 ---
st.sidebar.header("🚀 雙引擎設定")
openai_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
gemini_key = st.sidebar.text_input("Gemini Key (AIza...):", type="password")

# 🌟 新增：模型選擇器 (讓使用者自己選能用的)
st.sidebar.markdown("---")
st.sidebar.caption("🔧 Gemini 模型微調")
gemini_model = st.sidebar.selectbox(
    "選擇模型:", 
    ["gemini-pro", "gemini-1.5-flash", "gemini-1.5-pro"],
    index=0  # 預設選第一個 (gemini-pro 最穩)
)

st.sidebar.markdown("---")
selected_theme = st.sidebar.selectbox("板塊:", list(TREND_THEMES.keys()))

target_tickers = []
if selected_theme == "🔥 自選監控":
    new = st.sidebar.text_input("➕ 代號:").upper().strip()
    if st.sidebar.button("新增") and new: 
        if new not in st.session_state.watchlist_us: st.session_state.watchlist_us.append(new)
    if st.session_state.watchlist_us:
        rm = st.sidebar.selectbox("移除:", ["(選)"]+st.session_state.watchlist_us)
        if rm != "(選)" and st.sidebar.button("刪除"): st.session_state.watchlist_us.remove(rm); st.rerun()
    target_tickers = st.session_state.watchlist_us
else:
    target_tickers = TREND_THEMES[selected_theme]["tickers"]

# --- 數據函式 ---
@st.cache_data(ttl=300)
def get_us_macro():
    try:
        vix = yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1]
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_curr = tnx['Close'].iloc[-1]
        tnx_change = ((tnx_curr - tnx['Close'].iloc[-2]) / tnx['Close'].iloc[-2]) * 100 
        fed = yf.Ticker("ZQ=F").history(period="5d")
        implied = 100 - fed['Close'].iloc[-1] if not fed.empty else 0
        return {"vix": vix, "tnx": tnx_curr, "tnx_chg": tnx_change, "rate": implied}
    except: return {"vix": 20, "tnx": 4.0, "tnx_chg": 0, "rate": 0}

def get_fomc():
    today = datetime.now().date()
    for m in CALENDAR_DATA["FOMC"]:
        d = datetime.strptime(m["date"], "%Y-%m-%d").date()
        if d >= today: return m, (d - today).days
    return None, 0

def calc_graham(info):
    try:
        eps = info.get('trailingEps', 0)
        bvps = info.get('bookValue', 0)
        return math.sqrt(22.5 * eps * bvps) if eps > 0 and bvps > 0 else 0
    except: return 0

# --- AI 大腦區 ---
def ask_openai(api_key, macro, fomc, df_s):
    try:
        client = openai.OpenAI(api_key=api_key)
        picks = []
        if not df_s.empty: picks += df_s.head(3)[['代號','現價','葛拉漢價','評分原因']].to_dict('records')
        prompt = f"""
        你是【巴菲特風格】的價值投資者。繁體中文。
        宏觀: 隱含利率 {macro['rate']:.2f}%, 10年債 {macro['tnx']:.2f}%, VIX {macro['vix']:.2f}, FOMC剩 {fomc[1]} 天。
        精選: {picks}
        任務: 請用「保守、安全邊際」的角度分析。如果葛拉漢價低於現價，請嚴厲警告風險。重點放在不想虧錢。
        """
        res = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role":"user","content":prompt}])
        return res.choices[0].message.content
    except Exception as e: return f"OpenAI 罷工: {str(e)}"

def ask_gemini(api_key, model_name, macro, fomc, df_s):
    # 使用 HTTP 直連，並代入使用者選擇的模型名稱
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    picks = []
    if not df_s.empty: picks += df_s.head(3)[['代號','現價','葛拉漢價','評分原因']].to_dict('records')
    
    prompt_text = f"""
    你是【凱薩琳伍德風格】的成長型投資者。繁體中文。
    宏觀: 隱含利率 {macro['rate']:.2f}%, 10年債 {macro['tnx']:.2f}%, VIX {macro['vix']:.2f}。
    精選: {picks}
    任務: 請用「創新、顛覆性趨勢」的角度分析。不要太在意現在的估值，重點是未來的成長潛力。
    """
    
    payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
    
    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            result = response.json()
            return f"✨ (使用模型: {model_name})\n\n{result['candidates'][0]['content']['parts'][0]['text']}"
        else:
            return f"Gemini 連線失敗 (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return f"Gemini 網路錯誤: {str(e)}"

# --- 評分 ---
def score_us_stock(rsi, peg, pe, roe, de, fcf, change, margin, macro):
    score = 50; det = []
    if macro['vix']>30: score+=20; det.append("🩸恐慌VIX")
    if margin>20: score+=20; det.append("🏰葛拉漢低估")
    elif margin>0: score+=10; det.append("💰低於價值")
    if roe>15: score+=10; det.append("✅ROE優")
    if de>2.5: score-=20; det.append("💀高負債")
    if fcf<=0: score-=20; det.append("💸燒錢")
    if peg>0 and peg<1.2: score+=15; det.append("💎PEG低估")
    if rsi<30: score+=15; det.append("📉超賣")
    if change<-2: score+=10; det.append("🔥大跌")
    return max(0,min(100,score)), " ".join(det)

def score_us_etf(rsi, dd, macro):
    score = 50; det = []
    if macro['vix']>30: score+=30; det.append("🩸極恐慌")
    if dd<-20: score+=25; det.append("🐻熊市價")
    elif dd<-10: score+=15; det.append("📉修正價")
    if rsi<30: score+=20; det.append("📉超賣")
    return max(0,min(100,score)), " ".join(det)

def get_data(tickers):
    macro = get_us_macro()
    sl, el = [], []
    bar = st.progress(0)
    status = st.empty()
    
    for i, t in enumerate(tickers):
        status.text(f"分析中: {t}")
        try:
            s = yf.Ticker(t)
            h = s.history(period="1y")
            if h.empty: continue
            if len(h)>200:
                cur = h['Close'].iloc[-1]
                chg = ((cur-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100
                delta = h['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean().replace(0, 0.001)
                rsi = 100 - (100/(1 + (gain/loss))).iloc[-1]
                info = s.info
                is_etf = (t in KNOWN_ETFS) or (info.get('quoteType')=='ETF')
                if is_etf:
                    dd = ((cur-h['Close'].max())/h['Close'].max())*100
                    sc, re = score_us_etf(rsi, dd, macro)
                    el.append({"代號":t, "現價":f"{cur:.2f}", "分數":int(sc), "回檔":f"{dd:.1f}%", "評分原因":re})
                else:
                    g = calc_graham(info)
                    m = ((g-cur)/cur)*100 if g>0 else 0
                    peg=info.get('pegRatio',0); roe=info.get('returnOnEquity',0); de=info.get('debtToEquity',0); fcf=info.get('freeCashflow',0)
                    sc, re = score_us_stock(rsi, peg, info.get('trailingPE',0), (roe or 0)*100, (de or 0)/100, fcf or 0, chg, m, macro)
                    sl.append({"代號":t, "現價":f"{cur:.2f}", "葛拉漢價":f"{g:.2f}" if g>0 else "-", "邊際":f"{m:.1f}%", "分數":int(sc), "評分原因":re})
        except: pass
        bar.progress((i+1)/len(tickers))
    return pd.DataFrame(sl), pd.DataFrame(el), macro

# --- UI ---
fomc, days = get_fomc()
c1,c2,c3 = st.columns(3)
if st.button('🚀 雙引擎掃描美股'):
    ds, de, mac = get_data(target_tickers)
    c1.metric("隱含利率", f"{mac['rate']:.2f}%")
    c2.metric("VIX", f"{mac['vix']:.2f}")
    c3.metric("FOMC", f"剩 {days} 天")
    
    if openai_key or gemini_key:
        with st.spinner(f"🤖 雙 AI 正在辯論中 ({gemini_model})..."):
            if openai_key: st.session_state.ai_response_us_openai = ask_openai(openai_key, mac, (fomc, days), ds)
            # 傳入使用者選擇的模型
            if gemini_key: st.session_state.ai_response_us_gemini = ask_gemini(gemini_key, gemini_model, mac, (fomc, days), ds)

    if st.session_state.ai_response_us_openai or st.session_state.ai_response_us_gemini:
        st.write("### 🤖 投資觀點對決")
        tab1, tab2 = st.tabs(["🧐 OpenAI (巴菲特)", "✨ Gemini (伍德)"])
        with tab1:
            if st.session_state.ai_response_us_openai: st.info(st.session_state.ai_response_us_openai)
            else: st.warning("未輸入 OpenAI Key")
        with tab2:
            if st.session_state.ai_response_us_gemini: st.success(st.session_state.ai_response_us_gemini)
            else: st.warning("未輸入 Gemini Key")
    
    def highlight_score(val):
        if val >= 80: return 'background-color: #1b5e20; color: white; font-weight: bold;'
        elif val >= 60: return 'background-color: #c8e6c9; color: black;'
        return ''
    
    cl, cr = st.columns(2)
    with cl:
        st.subheader("🏢 價值股")
        if not ds.empty: st.dataframe(ds.sort_values(by="分數", ascending=False).style.map(highlight_score, subset=['分數']))
        else: st.warning("無個股數據")
    with cr:
        st.subheader("📊 ETF")
        if not de.empty: st.dataframe(de.sort_values(by="分數", ascending=False).style.map(highlight_score, subset=['分數']))
        else: st.warning("無ETF數據")
