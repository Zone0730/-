
from FinMind.data import DataLoader
import pandas as pd
import datetime
import time
import streamlit as st # 新增 Streamlit 支援

# --- 設定區 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8" 

# 初始化
dl = DataLoader()
try:
    dl.login_by_token(api_token=FINMIND_TOKEN)
    # print 改為 st 相關顯示 (在後續介面中處理)
except:
    pass

def get_all_ids():
    """取得台股上市櫃股票清單"""
    try:
        df = dl.taiwan_stock_info()
        df = df[df['type'].isin(['twse', 'tpex'])]
        df = df[df['stock_id'].str.len() == 4]
        return df['stock_id'].tolist()
    except Exception as e:
        return []

def scan_market(progress_bar, status_text):
    all_ids = get_all_ids()
    total = len(all_ids)
    
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    
    picks = []
    
    for i, sid in enumerate(all_ids):
        # 更新介面上的進度條
        if i % 10 == 0:
            pct = i / total
            progress_bar.progress(pct)
            status_text.text(f"📊 目前進度: {i}/{total} ({round(pct*100, 1)}%) - 掃描中...")
        
        try:
            time.sleep(0.3) 
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            
            if len(df) < 65: continue
            
            df = df.sort_values('date')
            df['close'] = df['close'].astype(float)
            df['Vol'] = df['Trading_Volume'].astype(float)
            
            curr_p = df['close'].iloc[-1]
            ma20 = df['close'].rolling(20).mean().iloc[-1]
            ma20_prev = df['close'].rolling(20).mean().iloc[-2]
            ma60 = df['close'].rolling(60).mean().iloc[-1]
            high_10d = df['close'].iloc[-11:-1].max()
            vol_avg_5d = df['Vol'].iloc[-6:-1].mean()
            curr_v = df['Vol'].iloc[-1]
            
            # --- 原有選股邏輯 ---
            is_trending = curr_p > ma20 > ma60
            is_ma20_up = ma20 > ma20_prev
            is_breakout = curr_p > high_10d and curr_v > vol_avg_5d * 1.5
            bias = (curr_p - ma20) / ma20
            is_safe_entry = bias < 0.08
            is_liquid = curr_v > 300000 and curr_p > 10
            
            if is_trending and is_ma20_up and is_breakout and is_safe_entry and is_liquid:
                picks.append({
                    "股票代號": sid, 
                    "目前股價": curr_p, 
                    "成交量比": round(curr_v/vol_avg_5d, 1),
                    "乖離率%": round(bias * 100, 2)
                })
        except Exception as e:
            if "Rate limit" in str(e):
                st.error("🛑 觸發 API 限制")
                break
            continue
            
    return picks

# --- Streamlit APP 介面 ---
st.set_page_config(page_title="台股自動選股", layout="centered")
st.title("🏆 波段價值選股系統")
st.write("策略：MA多頭排列 + 帶量突破 + 低乖離")

if st.button("🚀 開始掃描全市場標的", use_container_width=True):
    start_time = time.time()
    
    # 建立進度顯示區塊
    bar = st.progress(0)
    status = st.empty()
    
    results = scan_market(bar, status)
    
    end_time = time.time()
    bar.progress(1.0)
    status.text(f"✅ 掃描完成！耗時: {round((end_time - start_time)/60, 1)} 分鐘")
    
    if results:
        st.balloons()
        st.subheader(f"🔥 今日推薦標的 ({len(results)} 檔)")
        st.table(pd.DataFrame(results))
    else:
        st.info("今日市場未發現符合條件之標的。")

st.divider()
st.caption("提示：手機執行時請保持螢幕開啟，避免程式因休眠中斷。")
