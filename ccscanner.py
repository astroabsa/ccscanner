import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Scanner (Debug)", layout="wide")

# --- 2. SIDEBAR CONTROLS ---
st.sidebar.header("⚙️ Scanner Settings")
rsi_min = st.sidebar.slider("Min RSI (Bullish)", 0, 100, 55) # Lowered default
rsi_max = st.sidebar.slider("Max RSI (Bearish)", 0, 100, 45) # Raised default
adx_min = st.sidebar.slider("Min ADX (Trend Strength)", 0, 50, 15) # Lowered default
show_debug = st.sidebar.checkbox("Show Debug Info (Why is it empty?)", value=True)

# --- 3. GLOBAL SETTINGS ---
BASE_URL = "https://api.india.delta.exchange"
# Headers to prevent being blocked
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 4. AUTHENTICATION ---
def authenticate_user(user_in, pw_in):
    # Bypass for testing if needed, otherwise use your CSV logic
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
            else:
                st.error("Invalid credentials.")
    st.stop()

# --- 5. MAIN APPLICATION ---
st.title("🚀 Absa's Delta India Scanner (Diagnostic Mode)")

def get_sentiment(p_chg, oi_chg):
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: FETCH DATA ---
def fetch_market_data():
    try:
        # 1. Get Tickers
        resp = requests.get(f"{BASE_URL}/v2/tickers", headers=HEADERS)
        if resp.status_code != 200:
            if show_debug: st.error(f"Ticker API Failed: {resp.status_code}")
            return {}, {}, []
        
        tickers = resp.json().get('result', [])
        
        # Filter for USDT pairs only
        valid_tickers = [t for t in tickers if t['symbol'].endswith('USDT')]
        
        # Sort by Volume to find active pairs
        valid_tickers.sort(key=lambda x: float(x.get('volume_24h', 0) or 0), reverse=True)
        top_tickers = valid_tickers[:25] # Top 25
        
        top_symbols = [t['symbol'] for t in top_tickers]
        ticker_map = {t['symbol']: t for t in top_tickers}
        
        # 2. Get Products (IDs)
        resp_prod = requests.get(f"{BASE_URL}/v2/products", headers=HEADERS)
        products = resp_prod.json().get('result', [])
        product_map = {p['symbol']: p for p in products if p['symbol'] in top_symbols}
        
        if show_debug:
            st.info(f"✅ Found {len(top_tickers)} active pairs. Mapping IDs for history fetch...")
            
        return product_map, ticker_map, top_symbols
        
    except Exception as e:
        st.error(f"Critical API Error: {e}")
        return {}, {}, []

@st.fragment(run_every=300)
def refreshable_data_tables():
    product_map, ticker_map, top_symbols = fetch_market_data()
    
    if not top_symbols:
        st.warning("⚠️ No pairs found. API might be down or blocked.")
        return

    st.markdown("---")
    
    bullish, bearish = [], []
    # Log for debugging
    debug_logs = []

    progress_bar = st.progress(0, text="Scanning...")
    
    for i, sym in enumerate(top_symbols):
        try:
            if sym not in product_map: 
                debug_logs.append(f"❌ {sym}: No Product ID found")
                continue
            
            # Data Points
            pid = product_map[sym]['id']
            tick = ticker_map[sym]
            ltp = float(tick.get('close', 0))
            
            # Percent Change Fix
            # If price is 100 and 24h change is 5, API might send 5.0
            raw_pct = float(tick.get('percent_change_24h', 0))
            # Heuristic: if raw < 1.0 (like 0.05), assume decimal. Else assume percentage.
            p_change = raw_pct * 100 if abs(raw_pct) < 1.0 and raw_pct != 0 else raw_pct
            
            curr_oi = float(tick.get('open_interest', 0))
            
            # OI Change
            prev_oi = st.session_state.oi_cache.get(sym, curr_oi)
            oi_chg_pct = ((curr_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
            st.session_state.oi_cache[sym] = curr_oi
            
            # Fetch History
            hist_url = f"{BASE_URL}/v2/history/candles?product_id={pid}&resolution=60&limit=60"
            resp = requests.get(hist_url, headers=HEADERS, timeout=5)
            
            if resp.status_code == 200:
                history = resp.json().get('result', [])
                if history and len(history) > 30:
                    df = pd.DataFrame(history)
                    df = df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low'})
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
                    
                    tv_url = f"https://india.delta.exchange/app/futures/trade/{sym}"
                    
                    row = {
                        "Symbol": tv_url,
                        "LTP": ltp,
                        "Mom %": momentum_pct,
                        "24h %": round(p_change, 2),
                        "RSI": round(curr_rsi, 1),
                        "ADX": round(curr_adx, 1),
                        "Sentiment": sentiment
                    }
                    
                    # FILTER LOGIC (Controlled by Sidebar)
                    if p_change > 0 and curr_rsi > rsi_min and curr_adx > adx_min:
                        bullish.append(row)
                        debug_logs.append(f"✅ {sym}: BULLISH (RSI {curr_rsi:.1f}, ADX {curr_adx:.1f})")
                    elif p_change < 0 and curr_rsi < rsi_max and curr_adx > adx_min:
                        bearish.append(row)
                        debug_logs.append(f"✅ {sym}: BEARISH (RSI {curr_rsi:.1f}, ADX {curr_adx:.1f})")
                    else:
                        # Log why it failed (very helpful for debugging!)
                        debug_logs.append(f"⚪ {sym}: Skipped. RSI: {curr_rsi:.1f}, ADX: {curr_adx:.1f}")
                else:
                    debug_logs.append(f"⚠️ {sym}: History empty or too short")
            else:
                debug_logs.append(f"❌ {sym}: History API {resp.status_code}")

            progress_bar.progress((i + 1) / len(top_symbols))
        except Exception as e:
            debug_logs.append(f"💥 {sym}: Error {str(e)}")
            continue
            
    progress_bar.empty()
    
    column_config = {
        "Symbol": st.column_config.LinkColumn("Pair", display_text="^(.*)$"),
        "LTP": st.column_config.NumberColumn("Price", format="$%.4f")
    }
    
    c1, c2 = st.columns(2)
    with c1:
        st.success(f"🟢 ACTIVE BULLS (RSI > {rsi_min})")
        if bullish:
            st.dataframe(pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bullish action matching filters.")
            
    with c2:
        st.error(f"🔴 ACTIVE BEARS (RSI < {rsi_max})")
        if bearish:
            st.dataframe(pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bearish action matching filters.")

    # Show Debug Logs if checkbox is on
    if show_debug:
        with st.expander("🕵️ Debug Logs (Check this if tables are empty)"):
            st.write(debug_logs)

    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Last Data Sync:** {ist_time} IST")
    st.markdown("<div style='text-align: center; color: grey;'>Powered by : i-Tech World</div>", unsafe_allow_html=True)

refreshable_data_tables()
