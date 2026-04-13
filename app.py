
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 初始化與設定 ---
# 建議將 Token 放在 secrets 中，此處維持你的變數方便直接運行
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股波段選股系統 (終極優化版)", layout="centered")

@st.cache_resource
def get_loader():
    """初始化 DataLoader 並登入"""
    dl = DataLoader()
    try:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    except Exception as e:
        st.error(f"登入失敗，請檢查 Token：{e}")
    return dl

dl = get_loader()

def fetch_valid_data():
    """修正版：解決抓不到資料的問題，並統一欄位名稱"""
    # 從今天往回找 15 天，確保避開長假與維護期
    for i in range(15):
        test_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            # 抓取全市場日成交快照
            df = dl.taiwan_stock_daily_all(date=test_date)
            if df is not None and not df.empty:
                # 【關鍵修復】將所有欄位轉為小寫，解決 'Trading_Volume' vs 'trading_volume' 問題
                df.columns = [c.lower() for c in df.columns]
                return df, test_date
        except:
            continue
    return pd.DataFrame(), None

def scan_market(progress_bar, status_text):
    """執行市場掃描邏輯"""
    # 1. 抓取最近交易日資料
    all_market, actual_date = fetch_valid_data()
    
    if all_market.empty:
        st.error("❌ 抓不到市場資料。請確認 FinMind API 狀態或 Token 是否正確。")
        return []

    status_text.text(f"📅 檢測到最近交易日：{actual_date}，初步篩選中...")
    
    # 2. 初步過濾：
    # 成交量 > 1000 張 (1,000,000股) 且 股價 > 10
    # 欄位已在 fetch_valid_data 統一為小寫
    mask = (all_market['trading_volume'] >= 1000000) & (all_market['close'] >= 10)
    filtered_df = all_market[mask].copy()
    
    # 只留 4 碼個股 (排除權證、ETF)
    filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4]
    
    picks = []
    total = len(filtered_df)
    
    # 歷史資料抓取起始日 (抓 120 天確保 MA60 準確)
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        sname = row.get('stock_name', sid)
        
        # 更新進度條
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 分析中 ({i+1}/{total}): {sid} {sname}")
        
        try:
            # 防止 API 頻率過快被鎖 (針對免費/一般 Token)
            time.sleep(0.05) 
            
            df_hist = dl.taiwan_stock_daily(stock_id=sid, start_date=start_dt)
            
            if df_hist is None or len(df_hist) < 60:
                continue
            
            # 排序並計算均線
            df_hist = df_hist.sort_values('date')
            prices = pd.to_numeric(df_hist['close'])
            curr_p = prices.iloc[-1]
            
            ma10 = prices.rolling(10).mean().iloc[-1]
            ma20 = prices.rolling(20).mean().iloc[-1]
            ma60 = prices.rolling(60).mean().iloc[-1]
            
            # --- 選股策略邏輯 ---
            # 1. 均線多頭排列：股價 > MA10 > MA20 > MA60
            # 2. 站穩 10 日線：股價 > MA10
            # 3. 低乖離：與月線距離在 8% 以內 (避免追高)
            if curr_p > ma10 > ma20 > ma60:
                bias = (curr_p - ma20) / ma20
                if 0 < bias < 0.08:
                    picks.append({
                        "股票代號": sid,
                        "收盤價": curr_p,
                        "成交張數": int(row['trading_volume'] / 1000),
                        "月線 (MA20)": round(ma20, 2),
                        "乖離率 (%)": f"{round(bias * 100, 2)}%",
                        "狀態": "強勢多頭"
                    })
        except Exception:
            continue
            
    return picks

# --- 3. UI 介面 ---
st.title("🏆 台股波段選股系統")
st.markdown("---")
st.caption("🚀 **戰法說明**：篩選成交量大、均線多頭排列且剛從月線起漲（低乖離）的潛力個股。")

# 側邊欄資訊
with st.sidebar:
    st.header("系統狀態")
    st.info(f"API Token: 已載入")
    st.write("建議執行時間：盤後 15:00 以後")

# 主按鈕
if st.button("🚀 開始全市場掃描", use_container_width=True):
    bar = st.progress(0)
    msg = st.empty()
    
    start_time = time.time()
    results = scan_market(bar, msg)
    duration = int(time.time() - start_time)
    
    bar.progress(1.0)
    
    if results:
        st.balloons()
        st.success(f"✅ 掃描完成！耗時 {duration} 秒，找到 {len(results)} 檔標的。")
        
        # 轉換為 DataFrame 顯示
        res_df = pd.DataFrame(results)
        st.dataframe(
            res_df, 
            use_container_width=True,
            column_config={
                "股票代號": st.column_config.TextColumn("代號"),
                "收盤價": st.column_config.NumberColumn("價格", format="%.2f"),
                "乖離率 (%)": st.column_config.TextColumn("月線乖離")
            }
        )
    else:
        st.warning("🧐 掃描完成，今日市場中暫無符合「強勢多頭且低乖離」的標的。")

st.markdown("---")
st.caption("免責聲明：本系統僅供技術研究，不構成任何投資建議，投資請審慎評估風險。")
