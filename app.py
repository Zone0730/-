
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 初始化 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMyAxODo0Mjo0NiIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjQ5LjIxNi45MC4xMjEifQ.rGUBHwrSCNbQEx71AB3Qoev38M1ztlRFAiYSG1xO17g"

st.set_page_config(page_title="台股波段選股系統 (極速穩定版)", layout="centered")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    dl.login_by_token(api_token=FINMIND_TOKEN)
    return dl

dl = get_loader()

def fetch_valid_data():
    """超強修復：主動跳過無資料時段，確保抓到最近一個有資料的交易日"""
    # 獲取台灣時間
    now_tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    
    # 策略：從「昨天」開始往回找 15 天。
    # 為什麼不從「今天」找？因為 14:00~19:00 API 資料可能正在轉檔，會回傳空值。
    for i in range(1, 16):
        test_date = (now_tw - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            df = dl.taiwan_stock_daily_all(date=test_date)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                # 統一成交量欄位
                if 'trading_volume' not in df.columns and 'volume' in df.columns:
                    df = df.rename(columns={'volume': 'trading_volume'})
                return df, test_date
        except:
            continue
    return pd.DataFrame(), None

def scan_market(progress_bar, status_text):
    all_market, actual_date = fetch_valid_data()
    
    if all_market.empty:
        # 如果還是抓不到，可能是 Token 沒登入成功或 API 額度用完
        st.error("❌ 無法取得市場資料。原因可能是：1. FinMind 伺服器維護中 2. API 呼叫次數今日已達上限。")
        return []

    status_text.text(f"📅 使用資料日期：{actual_date} (自動避開空窗期)")
    
    # 欄位防錯判斷
    vol_col = 'trading_volume' if 'trading_volume' in all_market.columns else 'volume'
    
    # 過濾個股
    try:
        mask = (all_market[vol_col] >= 1000000) & (all_market['close'] >= 10)
        filtered_df = all_market[mask].copy()
        filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4]
    except Exception as e:
        st.error(f"資料過濾失敗: {e}")
        return []
    
    picks = []
    total = len(filtered_df)
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

    # 取前 150 檔量大的就好，避免 API 跑太久掛掉
    filtered_df = filtered_df.sort_values(vol_col, ascending=False).head(150)
    total = len(filtered_df)

    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        sname = row.get('stock_name', sid)
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 掃描中 ({i+1}/{total}): {sid} {sname}")
        
        try:
            time.sleep(0.1) # 增加穩定性
            df_hist = dl.taiwan_stock_daily(stock_id=sid, start_date=start_dt)
            if df_hist is None or len(df_hist) < 60: continue
            
            prices = pd.to_numeric(df_hist['close'])
            curr_p = prices.iloc[-1]
            ma10 = prices.rolling(10).mean().iloc[-1]
            ma20 = prices.rolling(20).mean().iloc[-1]
            ma60 = prices.rolling(60).mean().iloc[-1]
            
            # 策略：多頭排列 + 站上10日線 + 靠近月線
            if curr_p > ma10 > ma20 > ma60:
                bias = (curr_p - ma20) / ma20
                if 0 < bias < 0.08:
                    picks.append({
                        "代號": sid,
                        "名稱": sname,
                        "價格": curr_p,
                        "張數": int(row[vol_col] / 1000),
                        "乖離%": round(bias * 100, 2)
                    })
        except:
            continue
    return picks

# --- UI ---
st.title("🏆 台股波段選股 (終極修復版)")
st.caption("自動鎖定最近有效交易日 | 避開 API 資料真空期")

if st.button("🚀 開始全市場掃描", use_container_width=True):
    bar = st.progress(0)
    msg = st.empty()
    results = scan_market(bar, msg)
    
    if results:
        st.balloons()
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.warning("🧐 掃描完成，目前無符合條件股票或 API 暫時無回應。")

st.info("💡 小撇步：若按下去直接顯示警告，請等 30 秒再按一次，避免 API 請求過於頻繁。")
