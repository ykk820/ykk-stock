import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from openai import OpenAI
import json
import math # 引入數學模組來處理 NaN

# ---------------------------------------------------------
# 1. 系統設定
# ---------------------------------------------------------
st.set_page_config(page_title="AI 超級成長股分析師", layout="wide")
st.title("🤖 AI Super Growth Stock Analyzer")
st.markdown("### 結合 GPT-4 的「質化分析」與財報數據的「量化篩選」")
st.markdown("---")

# 側邊欄：設定
with st.sidebar:
    st.header("🔑 設定")
    api_key = st.text_input("請輸入 OpenAI API Key", type="password")
    st.caption("你的 Key 不會被儲存，僅用於本次執行。")
    
    st.divider()
    
    # 選股清單
    default_tickers = "PLTR, NU, GOOGL, MSFT, NVDA, RKLB, TSM, HIMS, SE, CRWD"
    user_tickers = st.text_area("輸入股票代號 (用逗號分隔)", value=default_tickers)
    tickers_list = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

# ---------------------------------------------------------
# 2. 核心：AI 分析師
# ---------------------------------------------------------
def analyze_stock_with_gpt(client, ticker, financial_data, business_summary):
    system_prompt = """
    You are a world-class Hedge Fund Manager specializing in "High Growth + Wide Moat" stocks. 
    Analyze the financial data and determine the moat strength and growth potential.
    Output strictly in JSON format:
    {
        "score": <int>,
        "moat_rating": "<Wide/Narrow/None>",
        "reason": "<string>"
    }
    """
    
    user_content = f"""
    Ticker: {ticker}
    Sector: {financial_data.get('sector', 'N/A')}
    Business Summary: {business_summary}
    
    Key Metrics:
    - Revenue Growth: {financial_data.get('revenueGrowth', 0) * 100:.2f}%
    - Gross Margins: {financial_data.get('grossMargins', 0) * 100:.2f}%
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"score": 0, "moat_rating": "Error", "reason": "AI Analysis Failed"}

# ---------------------------------------------------------
# 3. 數據抓取
# ---------------------------------------------------------
def fetch_data_and_analyze(tickers, client):
    results = []
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, ticker in enumerate(tickers):
        status.text(f"正在分析 {ticker} ...")
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 數據防呆處理
            rev_growth = info.get('revenueGrowth', 0)
            if rev_growth is None: rev_growth = 0
            
            gross_margin = info.get('grossMargins', 0)
            if gross_margin is None: gross_margin = 0
            
            current_price = info.get('currentPrice', 0)
            if current_price is None: current_price = 0
            
            fin_data = {
                'revenueGrowth': rev_growth,
                'grossMargins': gross_margin,
                'sector': info.get('sector', 'Tech'),
                'currentPrice': current_price
            }
            summary = info.get('longBusinessSummary', 'No summary available.')
            
            ai_result = analyze_stock_with_gpt(client, ticker, fin_data, summary[:800])
            
            results.append({
                "Ticker": ticker,
                "Price": fin_data['currentPrice'],
                "AI_Score": ai_result.get('score', 0),
                "Moat": ai_result.get('moat_rating', 'None'),
                "Reason": ai_result.get('reason', 'No reason provided'),
                "Revenue_Growth": fin_data['revenueGrowth'] * 100,
                "Gross_Margin": fin_data['grossMargins'] * 100
            })
            
        except Exception as e:
            st.warning(f"跳過 {ticker}: {e}")
            
        progress_bar.progress((i + 1) / len(tickers))
        
    status.empty()
    return pd.DataFrame(results)

# ---------------------------------------------------------
# 4. 主程式 UI
# ---------------------------------------------------------

if st.button("🚀 啟動 AI 分析引擎"):
    if not api_key:
        st.error("請先輸入 OpenAI API Key")
    else:
        try:
            client = OpenAI(api_key=api_key)
            with st.spinner("AI 正在分析市場數據..."):
                df = fetch_data_and_analyze(tickers_list, client)
            
            if not df.empty:
                df = df.sort_values(by="AI_Score", ascending=False)
                
                st.subheader("🏆 AI 精選高潛力股")
                try:
                    st.dataframe(
                        df.style.background_gradient(subset=['AI_Score'], cmap='RdYlGn')
                        .format({"Price": "${:.2f}", "Revenue_Growth": "{:.2f}%", "Gross_Margin": "{:.2f}%", "AI_Score": "{:.0f}"}),
                        use_container_width=True
                    )
                except:
                    st.dataframe(df, use_container_width=True)
                
                # --- 視覺化分析 (包含終極防呆邏輯) ---
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("矩陣分析")
                    
                    # 【終極數據清洗函數】
                    def clean_bubble_size(val):
                        try:
                            v = float(val)
                            # 如果是 NaN (空值) 或者小於等於 0，一律設為 1 (最小可顯示單位)
                            if math.isnan(v) or v <= 0:
                                return 1.0
                            return v
                        except:
                            return 1.0

                    # 應用清洗函數
                    df['Bubble_Size'] = df['Revenue_Growth'].apply(clean_bubble_size)
                    
                    fig = px.scatter(
                        df, 
                        x="Gross_Margin", 
                        y="AI_Score", 
                        size="Bubble_Size", # 這裡現在保證都是正數了
                        color="Moat",
                        hover_name="Ticker",
                        text="Ticker",
                        hover_data={"Bubble_Size": False, "Revenue_Growth": True},
                        title="泡泡大小 = 成長動能",
                        labels={"Gross_Margin": "毛利率 (%)", "AI_Score": "AI 評分", "Revenue_Growth": "成長率"}
                    )
                    fig.update_traces(textposition='top center')
                    st.plotly_chart(fig, use_container_width=True)
                    
                with col2:
                    st.subheader("建議配置")
                    total_score = df['AI_Score'].sum()
                    if total_score > 0:
                        df['Weight'] = df['AI_Score'] / total_score
                    else:
                        df['Weight'] = 0
                    
                    fig_pie = px.pie(df, values='Weight', names='Ticker', title='資金比例')
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                st.markdown("### 📝 詳細報告")
                for index, row in df.iterrows():
                    with st.expander(f"{row['Ticker']} - {row['AI_Score']} 分"):
                        st.write(row['Reason'])

        except Exception as e:
            st.error(f"發生錯誤: {e}")
