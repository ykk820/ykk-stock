import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
from openai import OpenAI
import json

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
# 2. 核心：AI 分析師 (The Brain)
# ---------------------------------------------------------
def analyze_stock_with_gpt(client, ticker, financial_data, business_summary):
    """
    將數據丟給 GPT 進行分析
    """
    
    # System Prompt: 定義 AI 的角色
    system_prompt = """
    You are a world-class Hedge Fund Manager specializing in "High Growth + Wide Moat" stocks. 
    Your investment philosophy combines Warren Buffett's focus on competitive advantage (Moat) 
    with Cathie Wood's focus on disruptive innovation.
    
    Your Task:
    1. Analyze the provided financial data and business summary.
    2. Determine the strength of the company's "Economic Moat" (Network effect, Switching costs, Brand, Tech).
    3. Evaluate its "Growth Potential" (Is it sustainable?).
    4. Provide a score from 0 to 100 (where 80+ is a strong buy).
    5. Provide a one-sentence investment thesis.
    
    Output strictly in JSON format:
    {
        "score": <int>,
        "moat_rating": "<Wide/Narrow/None>",
        "reason": "<string>"
    }
    """
    
    # User Prompt: 提供真實數據
    user_content = f"""
    Ticker: {ticker}
    Sector: {financial_data.get('sector', 'N/A')}
    Business Summary: {business_summary}
    
    Key Metrics:
    - Revenue Growth: {financial_data.get('revenueGrowth', 0) * 100:.2f}%
    - Gross Margins: {financial_data.get('grossMargins', 0) * 100:.2f}%
    - Profit Margins: {financial_data.get('profitMargins', 0) * 100:.2f}%
    - Free Cash Flow: {financial_data.get('freeCashflow', 'N/A')}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview", # 若沒額度可用 gpt-3.5-turbo
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"}, # 強制回傳 JSON
            temperature=0.7
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        st.error(f"AI 分析失敗: {e}")
        return {"score": 0, "moat_rating": "Error", "reason": "AI Analysis Failed"}

# ---------------------------------------------------------
# 3. 數據抓取與整合
# ---------------------------------------------------------
def fetch_data_and_analyze(tickers, client):
    results = []
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, ticker in enumerate(tickers):
        status.text(f"正在分析 {ticker} (這需要一點時間讓 AI 思考)...")
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 1. 準備數據
            # 注意：若 yfinance 抓不到數據，預設補 0
            rev_growth = info.get('revenueGrowth', 0)
            if rev_growth is None: rev_growth = 0
            
            gross_margin = info.get('grossMargins', 0)
            if gross_margin is None: gross_margin = 0
            
            fin_data = {
                'revenueGrowth': rev_growth,
                'grossMargins': gross_margin,
                'profitMargins': info.get('profitMargins', 0),
                'freeCashflow': info.get('freeCashflow', 0),
                'sector': info.get('sector', 'Tech'),
                'currentPrice': info.get('currentPrice', 0)
            }
            summary = info.get('longBusinessSummary', 'No summary available.')
            
            # 2. 呼叫 AI
            ai_result = analyze_stock_with_gpt(client, ticker, fin_data, summary[:1000])
            
            # 3. 整合結果
            results.append({
                "Ticker": ticker,
                "Price": fin_data['currentPrice'],
                "AI_Score": ai_result['score'],
                "Moat": ai_result['moat_rating'],
                "Reason": ai_result['reason'],
                "Revenue_Growth": fin_data['revenueGrowth'] * 100, # 轉 %
                "Gross_Margin": fin_data['grossMargins'] * 100     # 轉 %
            })
            
        except Exception as e:
            st.warning(f"跳過 {ticker}: {e}")
            
        progress_bar.progress((i + 1) / len(tickers))
        
    status.empty()
    return pd.DataFrame(results)

# ---------------------------------------------------------
# 4. 主程式 UI 邏輯
# ---------------------------------------------------------

if st.button("🚀 啟動 AI 分析引擎"):
    if not api_key:
        st.error("請先在左側輸入 OpenAI API Key！")
    else:
        # 初始化 OpenAI Client
        try:
            client = OpenAI(api_key=api_key)
            
            with st.spinner("AI 正在閱讀財報並進行評分..."):
                df = fetch_data_and_analyze(tickers_list, client)
            
            if not df.empty:
                # 排序：分數高的在上面
                df = df.sort_values(by="AI_Score", ascending=False)
                
                # --- 顯示區塊 1: 冠軍榜單 ---
                st.subheader("🏆 AI 精選高潛力股")
                
                # 格式化 DataFrame 顯示 (需要 matplotlib 支援漸層)
                try:
                    st.dataframe(
                        df.style.background_gradient(subset=['AI_Score'], cmap='RdYlGn')
                        .format({
                            "Price": "${:.2f}",
                            "Revenue_Growth": "{:.2f}%",
                            "Gross_Margin": "{:.2f}%",
                            "AI_Score": "{:.0f}"
                        }),
                        column_config={
                            "Reason": st.column_config.TextColumn("AI 投資觀點", width="medium"),
                            "Moat": st.column_config.TextColumn("護城河評級", width="small")
                        },
                        use_container_width=True
                    )
                except ImportError:
                    st.warning("請安裝 matplotlib 以顯示顏色漸層。")
                    st.dataframe(df, use_container_width=True)
                
                # --- 顯示區塊 2: 視覺化分析 ---
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("矩陣分析：護城河 vs AI 評分")
                    
                    # 【關鍵修正】防止負成長率導致 Plotly 報錯
                    # 邏輯：建立一個 Bubble_Size 欄位，最小數值為 1 (確保泡泡不會消失或報錯)
                    df['Bubble_Size'] = df['Revenue_Growth'].apply(lambda x: max(float(x), 1.0))
                    
                    # X軸: 毛利(硬護城河), Y軸: AI分數(軟實力), 顏色: 護城河評級
                    fig = px.scatter(
                        df, 
                        x="Gross_Margin", 
                        y="AI_Score", 
                        size="Bubble_Size", # 使用處理過的大小
                        color="Moat",
                        hover_name="Ticker",
                        text="Ticker",
                        # 在 hover 中顯示真實數據
                        hover_data={"Bubble_Size": False, "Revenue_Growth": True},
                        title="泡泡越大代表成長越快 (負成長顯示為最小點)",
                        labels={"Gross_Margin": "毛利率 (獲利能力)", "AI_Score": "AI 綜合評分", "Revenue_Growth": "營收成長率 (%)"}
                    )
                    fig.update_traces(textposition='top center')
                    st.plotly_chart(fig, use_container_width=True)
                    
                with col2:
                    st.subheader("💰 AI 建議投資組合")
                    # 簡單的權重分配：分數越高，買越多
                    total_score = df['AI_Score'].sum()
                    if total_score > 0:
                        df['Weight'] = df['AI_Score'] / total_score
                    else:
                        df['Weight'] = 0
                    
                    fig_pie = px.pie(df, values='Weight', names='Ticker', title='建議資金配置')
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                # --- 顯示區塊 3: AI 的詳細碎碎念 ---
                st.markdown("### 📝 AI 分析師詳細報告")
                for index, row in df.iterrows():
                    with st.expander(f"{row['Ticker']} - 分數: {row['AI_Score']} ({row['Moat']})"):
                        st.write(f"**投資理由：** {row['Reason']}")
                        st.write(f"**核心數據：** 營收成長 {row['Revenue_Growth']:.1f}% | 毛利率 {row['Gross_Margin']:.1f}%")
        
        except Exception as e:
            st.error(f"執行錯誤: {e}")
