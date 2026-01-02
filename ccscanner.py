import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Scanner", layout="wide")

# --- 2. GLOBAL SETTINGS ---
BASE_URL = "https://api.india.delta.exchange"

# Initialize Session State
if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 3. AUTHENTICATION ---
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

# --- 4. LOGIN GATE ---
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
st.title("🚀 Absa's Delta India Scanner (Auto-Discovery)")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

def get_sentiment(p_chg, oi_chg):
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: FETCH DATA & AUTO-DISCOVER ---
def fetch_market_data():
    try:
        # 1. Get ALL Tickers
        resp = requests.get(f"{BASE_URL}/v2/tickers")
        if resp.status_code != 200: return {}, {}, []
        
        tickers = resp.json().get('result', [])
        
        # FIX: Accept 'USD' OR 'USDT' (Matches your raw data 'ZROUSD')
        valid_tickers = [t for t in tickers if t['symbol'].endswith('USD') or t['symbol'].endswith('USDT')]
        
        # FIX: Sort by 'turnover' (present in your raw data) or 'volume'
        # This ensures we get the most active pairs first
        valid_tickers.sort(key=lambda x: float(x.get('turnover', 0) or x.get('volume', 0)), reverse=True)
        top_tickers = valid_tickers[:30] # Top 30 Active Pairs
        
        top_symbols = [t['symbol'] for t in top_tickers]
        ticker_map = {t['symbol']: t for t in top_tickers}
        
        # 2. Get Products (to map IDs for history)
        resp_prod = requests.get(f"{BASE_URL}/v2/products")
        products = resp_prod.json().get('result', [])
        product_map = {p['symbol']: p for p in products if p['symbol'] in top_symbols}
        
        return product_map, ticker_map, top_symbols
        
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}, {}, []

def render_dashboard(ticker_map):
    col1, col2, col3 = st.columns([1, 1, 2])
    
    # Try to find BTC/ETH (could be BTCUSD or BTCUSDT)
    btc_sym = next((s for s in ticker_map if s.startswith('BTC')), None)
    eth_sym = next((s for s in ticker_map if s.startswith('ETH')), None)
    
    if btc_sym:
        btc = ticker_map[btc_sym]
        p = float(btc.get('close', 0))
        # Use 'mark_change_24h' or calculate manually if pct missing
        pct = float(btc.get('mark_change_24h', 0) or 0)
            
        col1.metric(f"{btc_sym}", f"${p:,.2f}", f"{pct:.2f}%")
        
        bias, color = ("SIDEWAYS ↔️", "gray")
        if pct > 0.5: bias, color = ("BULLISH 🚀", "green")
        elif pct < -0.5: bias, color = ("BEARISH 📉", "red")
        
        col3.markdown(f"""
            <div style="text-align: center; padding: 10px; border: 1px solid {color}; border-radius: 10px;">
                <h3 style="margin:0; color: {color};">Market Bias: {bias}</h3>
            </div>
        """, unsafe_allow_html=True)

    if eth_sym:
        eth = ticker_map[eth_sym]
        p = float(eth.get('close', 0))
        pct = float(eth.get('mark_change_24h', 0) or 0)
        col2.metric(f"{eth_sym}", f"${p:,.2f}", f"{pct:.2f}%")

@st.fragment(run_every=300)
def refreshable_data_tables():
    # 1. AUTO-DISCOVER
    product_map, ticker_map, top_symbols = fetch_market_data()
    
    if not top_symbols:
        st.warning("Waiting for Delta Exchange data...")
        return

    # 2. DASHBOARD
    render_dashboard(ticker_map)
    st.markdown("---")
    
    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Analyzing Market Data...")
    
    for i, sym in enumerate(top_symbols):
        try:
            if sym not in product_map: continue
            
            # Data Points
            pid = product_map[sym]['id']
            tick = ticker_map[sym]
            ltp = float(tick.get('close', 0))
            
            # Use 'mark_change_24h' from your raw data (it was 7.4427)
            p_change = float(tick.get('mark_change_24h', 0))
            
            # OI (contracts)
            curr_oi = float(tick.get('oi_contracts', 0) or tick.get('open_interest', 0))
            
            # OI Change Cache
            prev_oi = st.session_state.oi_cache.get(sym, curr_oi)
            oi_chg_pct = ((curr_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
            st.session_state.oi_cache[sym] = curr_oi
            
            # History Fetch
            hist_url = f"{BASE_URL}/v2/history/candles?product_id={pid}&resolution=60&limit=60"
            resp = requests.get(hist_url, timeout=5)
            
            if resp.status_code == 200:
                history = resp.json().get('result', [])
                if history and len(history) > 30:
                    df = pd.DataFrame(history)
                    # Normalize columns (Delta returns t, o, h, l, c, v)
                    df = df.rename(columns={'close': 'Close', 'high': 'High', 'low': 'Low'})
                    df['Close'] = df['Close'].astype(float)
                    df['High'] = df['High'].astype(float)
                    df['Low'] = df['Low'].astype(float)
                    
                    # Indicators
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
                    
                    # Logic: Standard RSI/ADX filters
                    if p_change > 0.5 and curr_rsi > 60 and curr_adx > 20:
                        bullish.append(row)
                    elif p_change < -0.5 and curr_rsi < 45 and curr_adx > 20:
                        bearish.append(row)
                        
            progress_bar.progress((i + 1) / len(top_symbols))
        except Exception:
            continue
            
    progress_bar.empty()
    
    # Display Tables
    column_config = {
        "Symbol": st.column_config.LinkColumn("Pair", display_text="^(.*)$"),
        "LTP": st.column_config.NumberColumn("Price", format="$%.4f")
    }
    
    c1, c2 = st.columns(2)
    with c1:
        st.success("🟢 ACTIVE BULLS")
        if bullish:
            st.dataframe(pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bullish action.")
            
    with c2:
        st.error("🔴 ACTIVE BEARS")
        if bearish:
            st.dataframe(pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bearish action.")

    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Last Data Sync:** {ist_time} IST")
    st.markdown("<div style='text-align: center; color: grey;'>Powered by : i-Tech World</div>", unsafe_allow_html=True)

refreshable_data_tables()
