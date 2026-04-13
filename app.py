import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 設定區 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股波段選股系統 (平衡版)", layout="centered")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    try:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    except: pass
    return dl

dl = get_loader()

@st.cache_data(ttl=3600)
def get_all_ids():
    try:
        df = dl.taiwan_stock_info()
        df = df[df['type'].isin(['twse', 'tpex'])]
        df = df[df['stock_id'].str.len() == 4]
        exclude_list = ['ETF', '受益證券', '存託憑證', '權證']
        pattern = '|'.join(exclude_list)
        df = df[~df['category'].str.contains(pattern, na=False)]
        df = df[~df['stock_id'].str.startswith('00')]
        return df[['stock_id', 'stock_name']].values.tolist()
    except: return []

def scan_market(progress_bar, status_text):
    all_stocks = get_all_ids()
    total = len(all_stocks)
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    picks = []
    
    for i, (sid, sname) in enumerate(all_stocks):
        if i % 10 == 0:
            pct = i / total
            progress_bar.progress(pct)
            status_text.text(f"📊 掃描中: {i}/{total} - 目前標的: {sid} {sname}")
        
        try:
            time.sleep(0.1) # 略微加快速度
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if df is None or len(df) < 65: continue
                
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['Vol'] = pd.to_numeric(df['Trading_Volume'], errors='coerce')
            df = df.dropna(subset=['close', 'Vol']).sort_values('date')
            
            curr_v = df['Vol'].iloc[-1]
            curr_p = df['close'].iloc[-1]
            
            # --- 調整門檻：3,000 張 (3,000,000 股) ---
            if curr_v < 500000 or curr_p < 10:
                continue
            
            # 指標計算
            ma_series = df['close'].rolling(20).mean()
            ma60_series = df['close'].rolling(60).mean()
            ma20, ma20_prev, ma60 = ma_series.iloc[-1], ma_series.iloc[-2], ma60_series.iloc[-1]
            high_10d = df['close'].iloc[-11:-1].max()
            vol_avg_5d = df['Vol'].iloc[-6:-1].mean()
            
            # --- 調整後的策略邏輯 ---
            is_trending = curr_p > ma20 > ma60
            is_ma20_up = ma20 > ma20_prev
            is_breakout = curr_p > high_10d and curr_v > vol_avg_5d * 1.2 # 放寬到 1.2 倍
            bias = (curr_p - ma20) / ma20
            is_safe_entry = bias < 0.10 # 放寬到 10%
            
            if is_trending and is_ma20_up and is_breakout and is_safe_entry:
                picks.append({
                    "股票代號": sid, "股票名稱": sname, "目前股價": curr_p,
                    "今日張數": int(curr_v / 1000), "量增倍數": round(curr_v/vol_avg_5d, 1),
                    "乖離率%": round(bias * 100, 2)
                })
        except: continue
    return picks

# --- UI ---
st.title("🏆 台股波段選股系統 (平衡優化版)")
st.write("目前設定：成交量 > 500 張 + 量增 1.2 倍 + 乖離 < 10%")

if st.button("🚀 開始掃描", use_container_width=True):
    bar = st.progress(0)
    status = st.empty()
    results = scan_market(bar, status)
    bar.progress(1.0)
    
    if results:
        st.balloons()
        df_res = pd.DataFrame(results)
        st.dataframe(df_res, use_container_width=True)
        csv = df_res.to_csv(index=False).encode('utf_8_sig')
        st.download_button("📥 下載結果", csv, "picks.csv", "text/csv")
    else:
        st.warning("依舊沒有標的？建議檢查目前是否為『盤中』，若是盤中，今日成交量可能尚未累積達標。")
