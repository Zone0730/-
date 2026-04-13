
import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 初始化設定 ---
# 使用你最新的 Token
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMyAxODo0Mjo0NiIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjQ5LjIxNi45MC4xMjEifQ.rGUBHwrSCNbQEx71AB3Qoev38M1ztlRFAiYSG1xO17g"

st.set_page_config(page_title="台股籌碼波段系統", layout="wide")

@st.cache_resource
def get_loader():
    dl = DataLoader()
    dl.login_by_token(api_token=FINMIND_TOKEN)
    return dl

dl = get_loader()

def fetch_valid_data():
    """關鍵：自動回溯找到有資料的最近交易日"""
    now_tw = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    # 從昨天開始往回找 10 天
    for i in range(1, 10):
        test_date = (now_tw - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            df = dl.taiwan_stock_daily_all(date=test_date)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df, test_date
        except:
            continue
    return pd.DataFrame(), None

def scan_market(progress_bar, status_text):
    # 1. 抓取行情快照
    all_market, actual_date = fetch_valid_data()
    if all_market.empty:
        st.error("❌ 無法取得市場資料，請稍後再試或檢查 API 權限。")
        return []

    status_text.text(f"📅 偵測交易日：{actual_date} | 篩選量大個股中...")
    
    # 2. 初步過濾：成交量 > 1500 張 + 價格 > 10 (縮小範圍提升速度)
    vol_col = 'trading_volume' if 'trading_volume' in all_market.columns else 'volume'
    mask = (all_market[vol_col] >= 1500000) & (all_market['close'] >= 10)
    filtered_df = all_market[mask].copy()
    filtered_df = filtered_df[filtered_df['stock_id'].str.len() == 4]
    
    # 為了避免 API 請求過多，針對成交量前 60 檔進行深度籌碼掃描
    filtered_df = filtered_df.sort_values(vol_col, ascending=False).head(60)
    
    picks = []
    total = len(filtered_df)
    start_dt = (datetime.datetime.strptime(actual_date, "%Y-%m-%d") - datetime.timedelta(days=100)).strftime("%Y-%m-%d")

    for i, (idx, row) in enumerate(filtered_df.iterrows()):
        sid = row['stock_id']
        sname = row.get('stock_name', sid)
        progress_bar.progress((i + 1) / total)
        status_text.text(f"🔍 深度分析 ({i+1}/{total}): {sid} {sname}")
        
        try:
            time.sleep(0.1) # 避開頻率限制
            
            # A. 抓取技術面資料 (MA)
            df_hist = dl.taiwan_stock_daily(stock_id=sid, start_date=start_dt)
            if len(df_hist) < 20: continue
            
            close_series = df_hist['close']
            ma20 = close_series.rolling(20).mean().iloc[-1]
            curr_p = close_series.iloc[-1]
            
            # B. 抓取籌碼面資料 (分點進出 - 依據你提供的截圖 API)
            df_broker = dl.taiwan_stock_broker_ability(stock_id=sid, date=actual_date)
            
            # 計算分點買賣力道
            broker_power = 0
            if df_broker is not None and not df_broker.empty:
                # 買入分點家數 vs 賣出分點家數 (籌碼集中度判斷)
                buy_side = df_broker[df_broker['buy'] > 0]
                sell_side = df_broker[df_broker['sell'] > 0]
                broker_power = len(buy_side) - len(sell_side)

            # 選股邏輯：站上月線 + 籌碼不渙散 (買方分點較多或持平)
            if curr_p > ma20:
                bias = (curr_p - ma20) / ma20
                if 0 < bias < 0.07: # 低乖離，離月線不遠
                    picks.append({
                        "代號": sid,
                        "名稱": sname,
                        "股價": curr_p,
                        "成交張數": int(row[vol_col] / 1000),
                        "月線乖離%": round(bias * 100, 2),
                        "分點買賣差": broker_power
                    })
        except:
            continue
    return picks

# --- 3. UI 介面 ---
st.title("🚀 台股波段 + 分點籌碼監控")
st.info("此版本已修正『抓不到資料』的問題，並整合了分點買賣力道分析。")

if st.button("🔥 開始深度掃描市場", use_container_width=True):
    bar = st.progress(0)
    msg = st.empty()
    
    results = scan_market(bar, msg)
    
    if results:
        st.balloons()
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔潛力股")
        df_res = pd.DataFrame(results)
        
        # 排序：優先顯示乖離低且分點買盤強的
        df_res = df_res.sort_values(['分點買賣差', '月線乖離%'], ascending=[False, True])
        
        st.dataframe(
            df_res, 
            use_container_width=True,
            column_config={
                "月線乖離%": st.column_config.NumberColumn("月線乖離", format="%.2f%%"),
                "分點買賣差": st.column_config.NumberColumn("籌碼熱度", help="正數代表買進分點較多")
            }
        )
    else:
        st.warning("🧐 目前市場標的未符合篩選條件，或 API 回傳異常。")

st.divider()
st.caption("建議執行時間：平日 19:00 後，資料最為齊全。")
