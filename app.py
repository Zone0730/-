
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 初始化與設定 ---
# 這是你原本提供的 Token
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMyAxODo0Mjo0NiIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjQ5LjIxNi45MC4xMjEifQ.rGUBHwrSCNbQEx71AB3Qoev38M1ztlRFAiYSG1xO17g"

st.set_page_config(page_title="台股波段選股系統 (穩定修復版)", layout="centered")

@st.cache_resource
def get_loader():
    """初始化並登入 API"""
    dl = DataLoader()
    try:
        # 強制進行登入驗證
        success = dl.login_by_token(api_token=FINMIND_TOKEN)
        if not success:
            st.error("❌ FinMind Token 登入失敗，請確認 Token 是否有效。")
    except Exception as e:
        st.error(f"❌ 登入過程發生異常: {e}")
    return dl

dl = get_loader()

def fetch_valid_data():
    """關鍵修復：解決截圖中『抓不到資料』的問題"""
    # 考量到 Streamlit 伺服器時區，獲取台灣時間
    now_tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    
    # 從昨天開始往回找 15 天 (避開當日更新延遲與例假日)
    for i in range(1, 16):
        test_date = (now_tw - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            # 抓取該日全市場快照
            df = dl.taiwan_stock_daily_all(date=test_date)
            
            if df is not None and not df.empty:
                # 【重要】統一將欄位轉為小寫，解決大小寫不一導致的崩潰
                df.columns = [c.lower() for c in df.columns]
                
                # 確認成交量欄位名稱 (有些版本叫 trading_volume)
                if 'trading_volume' not in df.columns and 'volume' in df.columns:
                    df = df.rename(columns={'volume': 'trading_volume'})
                
                return df, test_date
        except:
            continue
    return pd.DataFrame(), None

def scan_market(progress_bar, status_text):
    """執行核心選股邏輯"""
    # 1. 抓取資料
    all_market, actual_date = fetch_valid_data()
    
    if all_market.empty:
        st.error("❌ 抓不到市場資料。可能是 API 次數達上限或伺服器維護中。")
        return []

    status_text.text(f"📅 偵測到最近有效交易日：{actual_date}，篩選中...")
    
    # 2. 初步過濾：成交量 > 1000 張 + 價格 > 10 + 僅限個股 (4碼)
    try:
        mask = (all_market['trading_volume'] >= 1000000) & (all_market['close'] >= 10)
        filtered_df = all_market[mask].copy()
        filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4]
    except KeyError as e:
        st.error(f"❌ 資料欄位異常，找不到：{e}")
        return []
    
    picks = []
    total = len(filtered_df)
    # 歷史資料抓取起始日 (回溯 120 天以確保 MA60 準確)
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

    # 3. 個股技術指標深度分析
    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        sname = row.get('stock_name', sid)
        
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 深度分析 ({i+1}/{total}): {sid} {sname}")
        
        try:
            time.sleep(0.08) # 稍微緩衝，防止被封 IP
            df_hist = dl.taiwan_stock_daily(stock_id=sid, start_date=start_dt)
            
            if df_hist is None or len(df_hist) < 60:
                continue
            
            df_hist = df_hist.sort_values('date')
            prices = pd.to_numeric(df_hist['close'])
            curr_p = prices.iloc[-1]
            
            # 技術指標計算
            ma10 = prices.rolling(10).mean().iloc[-1]
            ma20 = prices.rolling(20).mean().iloc[-1]
            ma60 = prices.rolling(60).mean().iloc[-1]
            
            # --- 選股策略：均線多頭排列 + 靠近月線 ---
            if curr_p > ma10 > ma20 > ma60:
                bias = (curr_p - ma20) / ma20
                # 乖離率在 0% ~ 8% 之間 (代表剛起漲，沒離月線太遠)
                if 0 < bias < 0.08:
                    picks.append({
                        "代號": sid,
                        "名稱": sname,
                        "股價": curr_p,
                        "張數": int(row['trading_volume'] / 1000),
                        "月線": round(ma20, 2),
                        "乖離率%": round(bias * 100, 2)
                    })
        except:
            continue
            
    return picks

# --- 2. UI 介面 ---
st.title("🏆 台股波段選股系統")
st.markdown("---")
st.caption("🔍 **策略目標**：找尋「均線多頭」且「剛回檔或剛起漲」的標的（月線乖離 < 8%）。")

if st.button("🚀 開始全市場掃描", use_container_width=True):
    bar = st.progress(0)
    msg = st.empty()
    
    start_time = time.time()
    results = scan_market(bar, msg)
    duration = int(time.time() - start_time)
    
    bar.progress(1.0)
    
    if results:
        st.balloons()
        st.success(f"✅ 掃描完成！耗時 {duration} 秒，找到 {len(results)} 檔符合標的。")
        
        # 整理結果表格
        res_df = pd.DataFrame(results)
        st.dataframe(
            res_df, 
            use_container_width=True,
            column_config={
                "乖離率%": st.column_config.NumberColumn("月線乖離%", format="%.2f%%"),
                "股價": st.column_config.NumberColumn("收盤價", format="%.1f")
            }
        )
    else:
        st.warning("🧐 掃描完成。今日市場暫無符合「多頭且低乖離」的股票。建議晚間或隔日再試。")

st.markdown("---")
st.caption("提示：若持續出現抓不到資料，請檢查網頁右上角是否正在 Running，或嘗試重新整理。")
