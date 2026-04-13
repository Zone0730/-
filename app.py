
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 初始化 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股波段選股系統 (終極修復版)", layout="centered")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    try: dl.login_by_token(api_token=FINMIND_TOKEN)
    except: pass
    return dl

dl = get_loader()

def fetch_valid_data():
    """關鍵修復：自動往回找有資料的日期，直到抓到為止"""
    # 從今天開始往回找 10 天 (避開長假)
    for i in range(10):
        test_date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            df = dl.taiwan_stock_daily_all(date=test_date)
            if df is not None and not df.empty:
                return df, test_date
        except:
            continue
    return pd.DataFrame(), None

def scan_market(progress_bar, status_text):
    # 1. 抓取最近一個交易日的快照
    all_market, actual_date = fetch_valid_data()
    
    if all_market.empty:
        st.error("❌ 抓不到市場資料。可能是 API Token 失效或 FinMind 伺服器維護中。")
        return []

    status_text.text(f"📅 檢測到最近交易日：{actual_date}，篩選中...")
    
    # 2. 初步過濾：成交量 > 1000 張 (1,000,000股) + 價格 > 10
    # 修正：部分資料庫欄位名稱可能是 'Trading_Volume' 或 'volume'
    vol_col = 'Trading_Volume' if 'Trading_Volume' in all_market.columns else 'volume'
    
    filtered_df = all_market[(all_market[vol_col] >= 1000000) & (all_market['close'] >= 10)]
    filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4] # 只留個股
    
    picks = []
    total = len(filtered_df)
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        sname = row.get('stock_name', sid)
        
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 深度分析 ({i+1}/{total}): {sid} {sname}")
        
        try:
            time.sleep(0.1) # 防止被 API 封鎖
            df_hist = dl.taiwan_stock_daily(stock_id=sid, start_date=start_dt)
            
            if df_hist is None or len(df_hist) < 60: continue
            
            df_hist = df_hist.sort_values('date')
            prices = pd.to_numeric(df_hist['close'])
            curr_p = prices.iloc[-1]
            
            # 技術指標
            ma20 = prices.rolling(20).mean().iloc[-1]
            ma60 = prices.rolling(60).mean().iloc[-1]
            ma10 = prices.rolling(10).mean().iloc[-1]
            
            # 選股邏輯：多頭排列 + 站上10日線 + 乖離小於 10%
            if curr_p > ma20 > ma60 and curr_p > ma10:
                bias = (curr_p - ma20) / ma20
                if bias < 0.10:
                    picks.append({
                        "代號": sid,
                        "股價": curr_p,
                        "張數": int(row[vol_col] / 1000),
                        "月線": round(ma20, 2),
                        "乖離%": round(bias * 100, 2)
                    })
        except:
            continue
    return picks

# --- UI 介面 ---
st.title("🏆 台股波段選股系統")
st.caption("自動追蹤最近交易日數據 | 均線多頭戰法")

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
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.warning("🧐 掃描完成，但沒有符合「強勢多頭且低乖離」的股票。建議盤後 17:00 再試一次。")
