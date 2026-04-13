
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 設定與初始化 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股波段選股系統 (快掃版)", layout="wide")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    try:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    except:
        pass
    return dl

dl = get_loader()

def get_trading_date():
    """自動判斷抓取日期 (16:30前抓前一天)"""
    now = datetime.datetime.now()
    if now.hour < 17:
        target_date = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = now.strftime("%Y-%m-%d")
    return target_date

def scan_market(progress_bar, status_text):
    target_date = get_trading_date()
    status_text.text(f"📅 檢查 {target_date} 全市場數據...")
    
    # 1. 抓取全市場當日行情 (一次性)
    try:
        all_market = dl.taiwan_stock_daily_all(date=target_date)
        if all_market.empty:
            return []
    except:
        return []

    # 2. 初步過濾：成交量 > 1500 張 (1,500,000股) 且 股價 > 10 元
    # 這樣會把 1000 支過濾剩下約 50-80 支，大幅節省 API 次數
    filtered_df = all_market[(all_market['Trading_Volume'] >= 1500000) & (all_market['close'] >= 10)]
    filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4]
    
    picks = []
    total = len(filtered_df)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=150)).strftime("%Y-%m-%d")
    
    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        
        # 進度條更新
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 深度分析中 ({i+1}/{total}): {sid}")
        
        try:
            time.sleep(0.15) # 避開 API 頻率限制
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date)
            
            if len(df) < 60: continue
            
            df = df.sort_values('date')
            df['close'] = pd.to_numeric(df['close'])
            df['Trading_Volume'] = pd.to_numeric(df['Trading_Volume'])
            
            curr_p = df['close'].iloc[-1]
            curr_v = df['Trading_Volume'].iloc[-1]
            
            # 指標計算
            ma10 = df['close'].rolling(10).mean().iloc[-1]
            ma20 = df['close'].rolling(20).mean().iloc[-1]
            ma60 = df['close'].rolling(60).mean().iloc[-1]
            vol_avg_5d = df['Trading_Volume'].iloc[-6:-1].mean()
            
            # 選股邏輯
            is_trending = curr_p > ma20 > ma60  # 均線多頭
            is_strong = curr_p > ma10           # 站上短均線
            is_vol_up = curr_v > vol_avg_5d     # 量增
            bias = (curr_p - ma20) / ma20       # 乖離率
            
            if is_trending and is_strong and is_vol_up and bias < 0.10:
                picks.append({
                    "代號": sid,
                    "股價": curr_p,
                    "漲跌": round(curr_p - df['close'].iloc[-2], 2),
                    "張數": int(curr_v / 1000),
                    "量比": round(curr_v / vol_avg_5d, 2),
                    "乖離%": round(bias * 100, 2)
                })
        except:
            continue
            
    return picks

# --- UI 介面 ---
st.title("🏆 台股波段選股系統 (穩定快掃版)")
st.info("策略：成交量 > 1500張 + 均線多頭排佈 + 帶量站上10日線 + 低乖離 (10%以內)")

if st.button("🚀 開始全市場掃描", use_container_width=True):
    bar = st.progress(0)
    status = st.empty()
    
    start_time = time.time()
    results = scan_market(bar, status)
    end_time = time.time()
    
    bar.progress(1.0)
    status.text(f"✅ 掃描完成！耗時: {int(end_time - start_time)} 秒")
    
    if results:
        st.balloons()
        df_res = pd.DataFrame(results)
        st.dataframe(df_res.sort_values("量比", ascending=False), use_container_width=True)
    else:
        st.warning("⚠️ 未發現符合條件標的。請確認目前是否為開盤日 16:30 以後，或嘗試調低成交量門檻。")

