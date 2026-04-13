import streamlit as st
import pandas as pd
from FinMind.data import DataLoader
import datetime
import time

# --- 1. 設定區 ---
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wNC0xMiAxNjo1MjozMyIsInVzZXJfaWQiOiJab25lIiwiZW1haWwiOiJkZW5pc2U5MTMzMEBnbWFpbC5jb20iLCJpcCI6IjEwMS4xMC45My4xOTgifQ.THF8SO6tE3RlrHH-oXvAjJ3om1s8FO7fG9SJX3KWOB8"

st.set_page_config(page_title="台股大成交量選股系統 v2.0", layout="centered")

@st.cache_resource
def get_loader():
    """初始化 DataLoader"""
    dl = DataLoader()
    try:
        dl.login_by_token(api_token=FINMIND_TOKEN)
    except:
        pass
    return dl

dl = get_loader()

# --- 2. 核心功能 ---

@st.cache_data(ttl=3600)
def get_all_ids():
    """精確取得台股上市櫃『普通股』清單，排除權證與 ETF"""
    try:
        df = dl.taiwan_stock_info()
        # 篩選上市與上櫃
        df = df[df['type'].isin(['twse', 'tpex'])]
        # 關鍵：股票代碼必須為 4 碼 (排除權證)
        df = df[df['stock_id'].str.len() == 4]
        # 關鍵：排除名稱或類別包含 ETF、受益證券、存託憑證 (DR) 的標的
        exclude_list = ['ETF', '受益證券', '存託憑證', '權證']
        pattern = '|'.join(exclude_list)
        df = df[~df['category'].str.contains(pattern, na=False)]
        
        # 再次確保不包含 00 開頭的 ETF
        df = df[~df['stock_id'].str.startswith('00')]
        
        return df[['stock_id', 'stock_name']].values.tolist()
    except:
        return []

def scan_market(progress_bar, status_text):
    all_stocks = get_all_ids()
    total = len(all_stocks)
    
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    
    picks = []
    
    for i, (sid, sname) in enumerate(all_stocks):
        # UI 更新進度
        if i % 10 == 0:
            pct = i / total
            progress_bar.progress(pct)
            status_text.text(f"📊 掃描進度: {i}/{total} - 檢查中: {sid} {sname}")
        
        try:
            # API 節流防護
            time.sleep(0.12) 
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            
            if df is None or len(df) < 65:
                continue
                
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['Vol'] = pd.to_numeric(df['Trading_Volume'], errors='coerce')
            df = df.dropna(subset=['close', 'Vol']).sort_values('date')
            
            curr_v = df['Vol'].iloc[-1]
            curr_p = df['close'].iloc[-1]
            
            # --- 篩選門檻：成交量超過 5,000 張 (5,000,000 股) ---
            if curr_v < 5000000 or curr_p < 10:
                continue
            
            # --- 技術指標 ---
            ma_series = df['close'].rolling(20).mean()
            ma60_series = df['close'].rolling(60).mean()
            
            ma20 = ma_series.iloc[-1]
            ma20_prev = ma_series.iloc[-2]
            ma60 = ma60_series.iloc[-1]
            
            high_10d = df['close'].iloc[-11:-1].max()
            vol_avg_5d = df['Vol'].iloc[-6:-1].mean()
            
            # --- 選股策略邏輯 ---
            is_trending = curr_p > ma20 > ma60 # 多頭排列
            is_ma20_up = ma20 > ma20_prev       # 均線走揚
            is_breakout = curr_p > high_10d and curr_v > vol_avg_5d * 1.5 # 帶量突破
            bias = (curr_p - ma20) / ma20
            is_safe_entry = bias < 0.08         # 乖離不過大
            
            if is_trending and is_ma20_up and is_breakout and is_safe_entry:
                picks.append({
                    "股票代號": sid,
                    "股票名稱": sname,
                    "目前股價": curr_p,
                    "今日張數": int(curr_v / 1000),
                    "量增倍數": round(curr_v/vol_avg_5d, 1),
                    "乖離率%": round(bias * 100, 2)
                })
        except Exception:
            continue
            
    return picks

# --- 3. Streamlit 介面 ---

st.title("🏆 台股大成交量選股系統")
st.markdown("### 策略核心：人氣熱門股 + 技術面多頭突破")
st.info("💡 已自動剔除 ETF、權證與受益證券，僅掃描普通股標的。")

if st.button("🚀 開始掃描全市場標的", use_container_width=True):
    start_time = time.time()
    bar = st.progress(0)
    status = st.empty()
    
    results = scan_market(bar, status)
    
    end_time = time.time()
    bar.progress(1.0)
    status.success(f"✅ 掃描完成！耗時: {round((end_time - start_time)/60, 1)} 分鐘")
    
    if results:
        st.balloons()
        df_res = pd.DataFrame(results)
        st.subheader(f"🔥 符合條件標的 ({len(results)} 檔)")
        st.dataframe(df_res, use_container_width=True)
        
        csv = df_res.to_csv(index=False).encode('utf_8_sig')
        st.download_button("📥 下載選股結果 (CSV)", csv, "stock_picks.csv", "text/csv")
    else:
        st.warning("今日未發現符合 5,000 張以上且帶量突破之標的。")

st.divider()
st.caption("提示：精簡後掃描總數約 1,800+ 檔，掃描速度將顯著提升。")
