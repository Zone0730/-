
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 設定區 ---
# 建議未來將 TOKEN 移至 st.secrets 以維護資安
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMyAxODo0Mjo0NiIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjQ5LjIxNi45MC4xMjEifQ.rGUBHwrSCNbQEx71AB3Qoev38M1ztlRFAiYSG1xO17g"

st.set_page_config(page_title="台股波段選股系統 (效能優化版)", layout="centered")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    try:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    except: pass
    return dl

dl = get_loader()

def scan_market(progress_bar, status_text):
    # 1. 取得目標日期 (若當前為凌晨或收盤前，嘗試抓取最新資料)
    now = datetime.datetime.now()
    # 判斷是否為收盤後(14:30後)
    if now.hour < 14:
        target_date = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = now.strftime("%Y-%m-%d")

    status_text.text(f"🔍 正在抓取全市場 {target_date} 快照，初步過濾中...")
    
    try:
        # 使用全市場快照 API (一次抓取所有股票當日行情)
        all_daily = dl.taiwan_stock_daily_info(date=target_date)
        if all_daily.empty:
            # 若當日無資料則改抓前一天
            target_date = (datetime.datetime.strptime(target_date, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            all_daily = dl.taiwan_stock_daily_info(date=target_date)
    except Exception as e:
        st.error(f"連線異常: {e}")
        return []

    # 2. 初步過濾：成交量 > 3000 張 且 股價 > 10 元 (排除非一般股)
    all_daily['Vol'] = pd.to_numeric(all_daily['Trading_Volume'], errors='coerce')
    all_daily['close'] = pd.to_numeric(all_daily['close'], errors='coerce')
    
    # 過濾條件：量大於 3,000,000 股、價大於 10、代碼長度為 4
    candidates = all_daily[
        (all_daily['Vol'] >= 3000000) & 
        (all_daily['close'] >= 10) & 
        (all_daily['stock_id'].str.len() == 4)
    ].copy()
    
    candidate_list = candidates[['stock_id', 'stock_name']].values.tolist()
    total = len(candidate_list)
    status_text.text(f"🎯 初步篩選完成！剩餘 {total} 檔需進行詳細技術掃描...")
    
    picks = []
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    
    # 3. 針對候選標的進行 MA 與 突破 邏輯判斷
    for i, (sid, sname) in enumerate(candidate_list):
        progress_bar.progress((i + 1) / total)
        status_text.text(f"📊 分析指標中 ({i+1}/{total}): {sid} {sname}")
        
        try:
            # 只有符合第一輪過濾的股票才會發送此請求
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=target_date)
            if df is None or len(df) < 65: continue
                
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['Vol'] = pd.to_numeric(df['Trading_Volume'], errors='coerce')
            df = df.dropna(subset=['close', 'Vol']).sort_values('date')
            
            curr_v = df['Vol'].iloc[-1]
            curr_p = df['close'].iloc[-1]
            
            # 指標計算
            ma_series = df['close'].rolling(20).mean()
            ma60_series = df['close'].rolling(60).mean()
            ma20, ma20_prev, ma60 = ma_series.iloc[-1], ma_series.iloc[-2], ma60_series.iloc[-1]
            high_10d = df['close'].iloc[-11:-1].max()
            vol_avg_5d = df['Vol'].iloc[-6:-1].mean()
            
            # 策略邏輯
            is_trending = curr_p > ma20 > ma60
            is_ma20_up = ma20 > ma20_prev
            is_breakout = curr_p > high_10d and curr_v > vol_avg_5d * 1.2
            bias = (curr_p - ma20) / ma20
            is_safe_entry = bias < 0.10
            
            if is_trending and is_ma20_up and is_breakout and is_safe_entry:
                picks.append({
                    "股票代號": sid, "股票名稱": sname, "目前股價": curr_p,
                    "今日張數": int(curr_v / 1000), "量增倍數": round(curr_v/vol_avg_5d, 1),
                    "乖離率%": round(bias * 100, 2)
                })
            # 稍微停頓避免 API 限制
            time.sleep(0.05) 
        except: continue
        
    return picks

# --- UI 介面 ---
st.title("🏆 台股波段選股系統 (效能優化版)")
st.info("優化重點：先過濾低成交量個股，掃描速度提升 10 倍以上。")

# 初始化 session_state
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

if st.button("🚀 開始高速掃描", use_container_width=True):
    bar = st.progress(0)
    status = st.empty()
    st.session_state.scan_results = scan_market(bar, status)
    bar.progress(1.0)
    status.text("✅ 掃描完成！")

# 顯示結果
if st.session_state.scan_results:
    st.balloons()
    df_res = pd.DataFrame(st.session_state.scan_results)
    st.success(f"找到 {len(df_res)} 檔符合條件的標的！")
    st.dataframe(df_res, use_container_width=True)
    
    csv = df_res.to_csv(index=False).encode('utf_8_sig')
    st.download_button("📥 下載選股結果 (CSV)", csv, "picks.csv", "text/csv")
elif st.session_state.scan_results == []:
    st.warning("目前市面上無符合條件的標的，或尚未到收盤更新時間。")

# 頁尾說明
st.divider()
st.caption("策略：多頭排列 + 10日高點突破 + 成交量大於3000張且增量1.2倍 + 乖離率小於10%。")
