import streamlit as st
import yfinance as yf
import pandas as pd
import openai
from datetime import datetime

st.set_page_config(page_title="🕵️‍♂️ Fundamental Agent", layout="wide")
st.title("🕵️‍♂️ AI 公司基本面調查員")
st.markdown("### 任務：財報分析 + 供應鏈解密 + 合約新聞挖掘")

# --- 側邊欄設定 ---
st.sidebar.header("⚙️ 設定調查員")
api_key = st.sidebar.text_input("OpenAI Key (sk-...):", type="password")
ticker = st.sidebar.text_input("輸入美股代號 (如 PLTR, GOOGL):", value="PLTR").upper()

# --- 1. 抓取公司行事曆與基本面 ---
def get_fundamentals(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        # 抓取行事曆 (下一次財報)
        try:
            cal = stock.calendar
            if isinstance(cal, dict) and 'Earnings Date' in cal:
                next_earnings = cal['Earnings Date'][0].strftime('%Y-%m-%d')
            elif not cal.empty:
                next_earnings = cal.iloc[0, 0].strftime('%Y-%m-%d')
            else:
                next_earnings = "未知"
        except:
            next_earnings = "未知"

        # 整理核心數據 (統一使用簡短 Key，避免報錯)
        pe = info.get('trailingPE')
        peg = info.get('pegRatio')
        
        data = {
            "名稱": info.get('longName', symbol),
            "產業": info.get('industry', 'N/A'),
            "市值": f"{info.get('marketCap', 0) / 1e9:.2f} B",
            "本益比": f"{pe:.2f}" if pe else "N/A (虧損中)",
            "PEG": f"{peg:.2f}" if peg else "N/A",
            "毛利率": f"{info.get('grossMargins', 0)*100:.2f}%",
            "營收成長": f"{info.get('revenueGrowth', 0)*100:.2f}%",
            "現金流": f"{info.get('freeCashflow', 0) / 1e9:.2f} B",
            "下次財報": next_earnings,
            "描述": info.get('longBusinessSummary', 'N/A')[:500] + "..."
        }
        return data, stock
    except Exception as e:
        st.error(f"找不到代號 {symbol}: {e}")
        return None, None

# --- 2. 抓取並過濾新聞 ---
def get_key_news(stock):
    try:
        news_list = stock.news
        key_stories = []
        
        # 定義關鍵字 (合約、訴訟、財報)
        keywords = ["contract", "deal", "partnership", "award", "supply", "lawsuit", "report", "earnings", "growth", "revenue"]
        
        for n in news_list:
            title = n['title']
            if any(k in title.lower() for k in keywords):
                publish_time = datetime.fromtimestamp(n['providerPublishTime']).strftime('%Y-%m-%d')
                key_stories.append(f"- [{publish_time}] {title}")
        
        # 如果找不到關鍵新聞，回傳最近 5 則
        if not key_stories:
            for n in news_list[:5]:
                publish_time = datetime.fromtimestamp(n['providerPublishTime']).strftime('%Y-%m-%d')
                key_stories.append(f"- [{publish_time}] {n['title']}")
                
        return key_stories[:10]
    except:
        return ["無法取得新聞數據"]

# --- 3. AI 調查員大腦 ---
def ask_agent(api_key, data, news):
    try:
        client = openai.OpenAI(api_key=api_key)
        
        # 這裡的 Key 已經跟 get_fundamentals 對齊，不會再報錯
        prompt = f"""
        你是一位像《大賣空》主角一樣敏銳的「法證基本面分析師」。
        請根據以下資料，對 {data['名稱']} ({data['產業']}) 進行深度調查。

        【硬數據】
        - 市值: {data['市值']}
        - 估值: PE {data['本益比']}, PEG {data['PEG']}
        - 獲利能力: 毛利率 {data['毛利率']}, 營收成長 {data['營收成長']}
        - 現金流: {data['現金流']}
        - 下次財報日: {data['下次財報']}

        【最新情報線索 (新聞)】
        {chr(10).join(news)}

        【任務：請撰寫一份調查報告】
        1. **供應鏈解密 (重要)**：
           - 根據你的知識庫，列出它的**上游供應商**（它依賴誰？例如晶片買誰的？雲端用誰的？）
           - 列出它的**下游大客戶**（誰給它錢？政府？企業？）。
           - 判斷它在供應鏈中是否有「不可取代性」？

        2. **重大合約與催化劑**：
           - 從新聞中分析，最近是否有獲得大合約？(例如 PLTR 的政府單)
           - 接下來的財報日是否有爆雷或噴出的風險？

        3. **隱藏風險**：
           - 除了財務，有沒有法律、政治或名譽風險？

        4. **最終判決**：
           - 給出投資評級 (強力買進/買進/觀望/賣出)。
           - 用一句話總結它的「護城河狀態」。

        請用繁體中文回答，風格犀利、專業。
        """

        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user", "content": prompt}]
        )
        return res.choices[0].message.content
    except Exception as e:
        return f"AI 罷工: {str(e)}"

# --- UI 介面 ---
if st.sidebar.button("🔍 開始調查"):
    if not api_key:
        st.error("請先輸入 OpenAI Key！")
    else:
        with st.spinner(f"正在駭入 {ticker} 的資料庫..."):
            fund_data, stock_obj = get_fundamentals(ticker)
            
            if fund_data:
                news_data = get_key_news(stock_obj)
                
                # 顯示數據看板
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("毛利率 (護城河)", fund_data['毛利率'])
                c2.metric("營收成長 (動能)", fund_data['營收成長'])
                c3.metric("本益比 (PE)", fund_data['本益比'])
                c4.metric("PEG (成長估值)", fund_data['PEG'])
                
                # AI 分析
                report = ask_agent(api_key, fund_data, news_data)
                
                st.markdown("---")
                st.subheader(f"📄 {ticker} 深度調查報告")
                st.write(report)
                
                with st.expander("查看原始新聞線索"):
                    for n in news_data:
                        st.text(n)
