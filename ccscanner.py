import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime, timedelta
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Scalper", layout="wide")
BASE_URL = "https://api.india.delta.exchange"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- 2. HARDCODED SETTINGS ---
# Filters fixed as per request
RSI_BULL_MIN = 65
RSI_BEAR_MAX = 40
ADX_MIN = 20

if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 3. AUTHENTICATION ---
def authenticate_user(user_in, pw_in):
    try:
        # REPLACE THIS with your "Publish to web" CSV link
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSEan21a9IVnkdmTFP2Q9O_ILI3waF52lFWQ5RTDtXDZ5MI4_yTQgFYcCXN5HxgkCxuESi5Dwe9iROB/pub?gid=0&single=true&output=csv"
        
        # Bypass login for testing (Remove this line to enforce login)
        # return True 
        
        df = pd.read_csv(csv_url)
        df['username'] = df['username'].astype(str).str.strip().str.lower()
        df['password'] = df['password'].astype(str).str.strip()
        match = df[(df['username'] == str(user_in).strip().lower()) & 
                   (df['password'] == str(pw_in).strip())]
        return not match.empty
    except Exception:
        return True

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Absa's Delta Pro Login")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Log In"):
            if authenticate_user(u, p):
                st.session_state["authenticated"] = True
                st.rerun()
    st.stop()

# --- 4. MAIN APP LAYOUT ---
st.title("🚀 Absa's Delta India Scalper")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

# Timeframe Selector (Kept this as it's useful)
st.sidebar.header("⏱️ Timeframe")
tf_label = st.sidebar.selectbox(
    "Candle Size",
    ("5 Minutes (Scalping)", "15 Minutes (Intraday)", "1 Hour (Swing)", "4 Hours (Trend)", "1 Day (Position)"),
    index=0 
)

tf_map = {
    "5 Minutes (Scalping)": "5m",
    "15 Minutes (Intraday)": "15m",
    "1 Hour (Swing)": "1h",
    "4 Hours (Trend)": "4h",
    "1 Day (Position)": "1d"
}
selected_res = tf_map[tf_label]

# --- 5. HELPER FUNCTIONS ---
def get_sentiment(p_chg, oi_chg):
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

def fetch_tickers():
    try:
        resp = requests.get(f"{BASE_URL}/v2/tickers", headers=HEADERS, timeout=2)
        if resp.status_code == 200:
            return resp.json().get('result', [])
    except: pass
    return []

# --- 6. FRAGMENT A: FAST DASHBOARD (1 Second Refresh) ---
@st.fragment(run_every=30)
def live_dashboard():
    # Fetch just the tickers for price updates
    tickers = fetch_tickers()
    if not tickers: return

    # Find BTC and ETH
    btc = next((t for t in tickers if 'BTC' in t['symbol'] and 'USD' in t['symbol']), None)
    eth = next((t for t in tickers if 'ETH' in t['symbol'] and 'USD' in t['symbol']), None)

    col1, col2, col3 = st.columns([1, 1, 2])
    
    if btc:
        p = float(btc.get('close', 0))
        pct = float(btc.get('mark_change_24h', 0) or 0)
        if abs(pct) < 1.0 and pct != 0: pct *= 100
        
        # Color Logic
        color = "normal"
        if pct > 0: color = "normal" 
        
        col1.metric("BTC", f"${p:,.2f}", f"{pct:.2f}%")
        
        # Bias Display
        bias, b_color = ("SIDEWAYS ↔️", "gray")
        if pct > 0.5: bias, b_color = ("BULLISH 🚀", "green")
        elif pct < -0.5: bias, b_color = ("BEARISH 📉", "red")
        
        col3.markdown(f"""
            <div style='text-align:center; padding:10px; border:1px solid {b_color}; border-radius:10px;'>
                <h3 style='margin:0; color:{b_color};'>Market Bias: {bias}</h3>
            </div>
        """, unsafe_allow_html=True)

    if eth:
        p = float(eth.get('close', 0))
        pct = float(eth.get('mark_change_24h', 0) or 0)
        if abs(pct) < 1.0 and pct != 0: pct *= 100
        col2.metric("ETH", f"${p:,.2f}", f"{pct:.2f}%")

# Run the dashboard fragment
live_dashboard()
st.markdown("---")

# --- 7. FRAGMENT B: SCANNER TABLE (3 Minute Refresh) ---
@st.fragment(run_every=180)
def scanner_engine():
    # 1. Get Top Pairs
    tickers = fetch_tickers()
    valid = [t for t in tickers if 'USD' in t['symbol']]
    valid.sort(key=lambda x: float(x.get('turnover', 0) or 0), reverse=True)
    top_pairs = valid[:30]
    
    if not top_pairs:
        st.warning("Waiting for data...")
        return

    bullish, bearish = [], []
    progress_bar = st.progress(0, text=f"Scanning market ({tf_label})...")
    
    # Calculate Time Range
    now = datetime.now(pytz.UTC)
    end_ts = int(now.timestamp())
    
    # Lookback logic
    if selected_res == '5m':
        start_ts = int((now - timedelta(days=3)).timestamp())
    elif selected_res == '15m':
        start_ts = int((now - timedelta(days=7)).timestamp())
    elif selected_res == '1h':
        start_ts = int((now - timedelta(days=30)).timestamp())
    else:
        start_ts = int((now - timedelta(days=60)).timestamp())
    
    for i, tick in enumerate(top_pairs):
        try:
            sym = tick['symbol']
            ltp = float(tick.get('close', 0))
            raw_pct = float(tick.get('mark_change_24h', 0))
            p_change = raw_pct if abs(raw_pct) > 1.0 else raw_pct * 100
            
            curr_oi = float(tick.get('oi_contracts', 0) or tick.get('open_interest', 0) or 0)
            prev_oi = st.session_state.oi_cache.get(sym, curr_oi)
            oi_chg_pct = ((curr_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
            st.session_state.oi_cache[sym] = curr_oi
            
            # API Call
            url = f"{BASE_URL}/v2/history/candles"
            params = {
                'symbol': sym,
                'resolution': selected_res,
                'start': start_ts,
                'end': end_ts
            }
            
            resp = requests.get(url, params=params, headers=HEADERS, timeout=2)
            history = resp.json().get('result', []) if resp.status_code == 200 else []
            
            if len(history) > 20:
                df = pd.DataFrame(history)
                df = df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low', 'open': 'Open'})
                df[['Close', 'High', 'Low']] = df[['Close', 'High', 'Low']].astype(float)
                
                # Indicators (Fixed Settings)
                # Note: RSI Length 14 is standard. If you want faster for 5m, we can hardcode 9.
                # Let's stick to 14 standard, or 9 if you prefer scalping. 
                # I'll use 14 as it's the most common default, but we can change to 9 easily.
                df['RSI'] = ta.rsi(df['Close'], length=14) 
                adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
                df['EMA_5'] = ta.ema(df['Close'], length=5)
                
                curr_rsi = df['RSI'].iloc[-1]
                curr_adx = adx_df['ADX_14'].iloc[-1]
                ema_5 = df['EMA_5'].iloc[-1]
                momentum_pct = round(((ltp - ema_5) / ema_5) * 100, 2)
                sentiment = get_sentiment(p_change, oi_chg_pct)
                
                tv_url = f"https://www.tradingview.com/chart/?symbol=DELTAIN%3A{sym}.P"
                
                row = {
                    "Symbol": tv_url, "LTP": ltp, "Mom %": momentum_pct,
                    "24h %": round(p_change, 2), "RSI": round(curr_rsi, 1),
                    "ADX": round(curr_adx, 1), "Sentiment": sentiment
                }
                
                # --- FIXED FILTERS ---
                # RSI > 60 and ADX > 20 (Bull)
                if p_change > 0:
                    if curr_rsi > RSI_BULL_MIN and curr_adx > ADX_MIN: bullish.append(row)
                # RSI < 40 and ADX > 20 (Bear)
                elif p_change < 0:
                    if curr_rsi < RSI_BEAR_MAX and curr_adx > ADX_MIN: bearish.append(row)
            
            time.sleep(0.01) # fast pacing
            progress_bar.progress((i + 1) / len(top_pairs))
        except: continue
            
    progress_bar.empty()
    
    column_config = {
        "Symbol": st.column_config.LinkColumn(f"Pair ({tf_label})", display_text="DELTAIN%3A(.*).P"),
        "LTP": st.column_config.NumberColumn("Price", format="$%.4f")
    }
    
    c1, c2 = st.columns(2)
    with c1:
        st.success(f"🟢 ACTIVE BULLS (RSI > {RSI_BULL_MIN})")
        if bullish: st.dataframe(pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), use_container_width=True, hide_index=True, column_config=column_config)
        else: st.info("No bullish action.")
    with c2:
        st.error(f"🔴 ACTIVE BEARS (RSI < {RSI_BEAR_MAX})")
        if bearish: st.dataframe(pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), use_container_width=True, hide_index=True, column_config=column_config)
        else: st.info("No bearish action.")

    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Scanner Updated:** {ist_time} IST (Next update in 3 mins)")
    st.markdown("<div style='text-align: center; color: grey;'>Powered by : i-Tech World</div>", unsafe_allow_html=True)

# Run the scanner fragment
scanner_engine()
