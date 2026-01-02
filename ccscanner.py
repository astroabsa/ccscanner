import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime, timedelta
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Scanner", layout="wide")
BASE_URL = "https://api.india.delta.exchange"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 2. AUTHENTICATION ---
def authenticate_user(user_in, pw_in):
    try:
        # REPLACE THIS with your "Publish to web" CSV link
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSEan21a9IVnkdmTFP2Q9O_ILI3waF52lFWQ5RTDtXDZ5MI4_yTQgFYcCXN5HxgkCxuESi5Dwe9iROB/pub?gid=0&single=true&output=csv"
        
        # Bypass login for testing (Remove this line to enforce login)
        return True 
        
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

# --- 3. MAIN APP ---
st.title("🚀 Absa's Delta India Scanner")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

# Sidebar Filters
st.sidebar.header("Filter Settings")
rsi_min = st.sidebar.slider("Min RSI (Bull)", 0, 100, 50)
rsi_max = st.sidebar.slider("Max RSI (Bear)", 0, 100, 50)
adx_min = st.sidebar.slider("Min ADX", 0, 50, 15)

def get_sentiment(p_chg, oi_chg):
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: FETCH TOP PAIRS ---
def fetch_top_pairs():
    try:
        resp = requests.get(f"{BASE_URL}/v2/tickers", headers=HEADERS)
        if resp.status_code != 200: return []
        tickers = resp.json().get('result', [])
        # Strict Filter: Must have 'USD' in symbol
        valid = [t for t in tickers if 'USD' in t['symbol']]
        # Sort by Turnover
        valid.sort(key=lambda x: float(x.get('turnover', 0) or 0), reverse=True)
        return valid[:30]
    except Exception:
        return []

@st.fragment(run_every=300)
def refreshable_data_tables():
    top_pairs = fetch_top_pairs()
    if not top_pairs:
        st.warning("Waiting for data...")
        return

    # Dashboard
    col1, col2, col3 = st.columns([1, 1, 2])
    def find_pair(name): return next((t for t in top_pairs if name in t['symbol']), None)
    btc = find_pair('BTC')
    eth = find_pair('ETH')
    
    if btc:
        p = float(btc.get('close', 0))
        pct = float(btc.get('mark_change_24h', 0) or 0)
        if abs(pct) < 1.0 and pct != 0: pct *= 100
        col1.metric("BTC", f"${p:,.2f}", f"{pct:.2f}%")
        bias, color = ("SIDEWAYS ↔️", "gray")
        if pct > 0.5: bias, color = ("BULLISH 🚀", "green")
        elif pct < -0.5: bias, color = ("BEARISH 📉", "red")
        col3.markdown(f"<div style='text-align:center; padding:10px; border:1px solid {color}; border-radius:10px;'><h3 style='margin:0; color:{color};'>Market Bias: {bias}</h3></div>", unsafe_allow_html=True)
    if eth:
        p = float(eth.get('close', 0))
        pct = float(eth.get('mark_change_24h', 0) or 0)
        if abs(pct) < 1.0 and pct != 0: pct *= 100
        col2.metric("ETH", f"${p:,.2f}", f"{pct:.2f}%")

    st.markdown("---")
    
    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Scanning active pairs...")
    
    # Time Range: Last 5 Days
    now = datetime.now(pytz.UTC)
    end_ts = int(now.timestamp())
    start_ts = int((now - timedelta(days=5)).timestamp())
    
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
            
            # --- API CALL: HISTORY/CANDLES ---
            url = f"{BASE_URL}/v2/history/candles"
            params = {
                'symbol': sym,
                'resolution': '5m',
                'start': start_ts,
                'end': end_ts
            }
            
            resp = requests.get(url, params=params, headers=HEADERS, timeout=2)
            history = []
            
            if resp.status_code == 200:
                history = resp.json().get('result', [])
            
            if history and len(history) > 15:
                df = pd.DataFrame(history)
                # Normalize Columns
                df = df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low', 'open': 'Open'})
                df['Close'] = df['Close'].astype(float)
                df['High'] = df['High'].astype(float)
                df['Low'] = df['Low'].astype(float)
                
                df['RSI'] = ta.rsi(df['Close'], length=14)
                adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
                df['EMA_5'] = ta.ema(df['Close'], length=5)
                
                curr_rsi = df['RSI'].iloc[-1]
                curr_adx = adx_df['ADX_14'].iloc[-1]
                ema_5 = df['EMA_5'].iloc[-1]
                
                momentum_pct = round(((ltp - ema_5) / ema_5) * 100, 2)
                sentiment = get_sentiment(p_change, oi_chg_pct)
                
                # --- NEW TRADINGVIEW URL LOGIC ---
                # Format: https://www.tradingview.com/chart/?symbol=DELTAIN:BTCUSD.P
                tv_url = f"https://www.tradingview.com/chart/?symbol=DELTAIN%3A{sym}.P"
                
                row = {
                    "Symbol": tv_url, "LTP": ltp, "Mom %": momentum_pct,
                    "24h %": round(p_change, 2), "RSI": round(curr_rsi, 1),
                    "ADX": round(curr_adx, 1), "Sentiment": sentiment
                }
                
                if p_change > 0:
                    if curr_rsi > rsi_min and curr_adx > adx_min: bullish.append(row)
                elif p_change < 0:
                    if curr_rsi < rsi_max and curr_adx > adx_min: bearish.append(row)
            
            time.sleep(0.01)
            progress_bar.progress((i + 1) / len(top_pairs))
        except: continue
            
    progress_bar.empty()
    
    # Configure Columns to show Symbol Name but link to TV
    column_config = {
        "Symbol": st.column_config.LinkColumn(
            "Pair (TV Chart)", 
            display_text="DELTAIN%3A(.*).P" # Extracts symbol name for display
        ),
        "LTP": st.column_config.NumberColumn("Price", format="$%.4f")
    }
    
    c1, c2 = st.columns(2)
    with c1:
        st.success("🟢 ACTIVE BULLS")
        if bullish: st.dataframe(pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), use_container_width=True, hide_index=True, column_config=column_config)
        else: st.info("No bullish action matching filters.")
    with c2:
        st.error("🔴 ACTIVE BEARS")
        if bearish: st.dataframe(pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), use_container_width=True, hide_index=True, column_config=column_config)
        else: st.info("No bearish action matching filters.")

    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Last Data Sync:** {ist_time} IST")
    st.markdown("<div style='text-align: center; color: grey;'>Powered by : i-Tech World</div>", unsafe_allow_html=True)

refreshable_data_tables()
