import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 設定與初始化 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股波段選股系統 (穩定版)", layout="centered")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    try: dl.login_by_token(api_token=FINMIND_TOKEN)
    except: pass
    return dl

dl = get_loader()

@st.cache_data(ttl=3600)
def get_all_ids():
    try:
        df = dl.taiwan_stock_info()
        df = df[df['type'].isin(['twse', 'tpex'])]
        df = df[df['stock_id'].str.len() == 4]
        # 排除權證與特殊標的
        df = df[~df['category'].str.contains('ETF|受益證券|存託憑證|權證', na=False)]
        return df[['stock_id', 'stock_name']].values.tolist()
    except: return []

def scan_market(progress_bar, status_text):
    all_stocks = get_all_ids()
    total = len(all_stocks)
    # 取近 120 天確保 MA20, MA60 正常
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    picks = []
    
    for i, (sid, sname) in enumerate(all_stocks):
        if i % 15 == 0:
            pct = i / total
            progress_bar.progress(pct)
            status_text.text(f"📊 掃描中: {i}/{total} ({sname})")
        
        try:
            time.sleep(0.12) 
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if df is None or len(df) < 60: continue
            
            df[['close', 'Trading_Volume']] = df[['close', 'Trading_Volume']].apply(pd.to_numeric)
            df = df.sort_values('date')
            
            curr_p = df['close'].iloc[-1]
            curr_v = df['Trading_Volume'].iloc[-1]
            
            # --- 基本門檻：成交量 > 1000 張 (確保一定有標的) ---
            if curr_v < 1000000 or curr_p < 10: continue
            
            # 指標計算
            ma20 = df['close'].rolling(20).mean().iloc[-1]
            ma60 = df['close'].rolling(60).mean().iloc[-1]
            ma10 = df['close'].rolling(10).mean().iloc[-1] # 新增 10 日線
            vol_avg_5d = df['Trading_Volume'].iloc[-6:-1].mean()
            
            # --- 邏輯修正：放寬突破條件 ---
            is_trending = curr_p > ma20 > ma60  # 趨勢向上
            is_strong = curr_p > ma10           # 股價在短均線之上 (不一定要創新高)
            is_vol_up = curr_v > vol_avg_5d     # 今天有增量 (不一定要 1.2 倍)
            bias = (curr_p - ma20) / ma20       # 乖離率
            
            if is_trending and is_strong and is_vol_up and bias < 0.12:
                picks.append({
                    "代號": sid, "名稱": sname, "股價": curr_p,
                    "張數": int(curr_v / 1000), "量比": round(curr_v/vol_avg_5d, 1),
                    "乖離%": round(bias * 100, 2)
                })
        except: continue
    return picks

# --- UI ---
st.title("🏆 台股波段選股系統 (穩定版)")
st.write("目前設定：1000張以上 + 均線多頭 + 帶量站上10日線")

if st.button("🚀 開始掃描", use_container_width=True):
    bar = st.progress(0)
    status = st.empty()
    results = scan_market(bar, status)
    bar.progress(1.0)
    
    if results:
        st.balloons()
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.warning("⚠️ 依舊沒有標的。這極可能是因為 FinMind 尚未更新今日收盤數據，請於 16:30 後再試一次，或檢查網路連線。")

