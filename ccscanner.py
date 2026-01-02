import streamlit as st
from delta_rest_client import DeltaRestClient # The new library
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta Exchange Scanner", layout="wide")

# --- 2. GLOBAL SETTINGS ---
# Delta Exchange Symbol Format (usually standard pairs)
CRYPTO_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT', 
    'MATICUSDT', 'LTCUSDT', 'ATOMUSDT', 'NEARUSDT', 'UNIUSDT', 
    'BCHUSDT', 'ETCUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT'
]

# Initialize Session State for OI Tracking
if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 3. AUTHENTICATION (Same CSV Method) ---
def authenticate_user(user_in, pw_in):
    try:
        # REPLACE THIS with your "Publish to web" CSV link
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSEan21a9IVnkdmTFP2Q9O_ILI3waF52lFWQ5RTDtXDZ5MI4_yTQgFYcCXN5HxgkCxuESi5Dwe9iROB/pub?gid=0&single=true&output=csv"
        
        df = pd.read_csv(csv_url)
        df['username'] = df['username'].astype(str).str.strip().str.lower()
        df['password'] = df['password'].astype(str).str.strip()
        
        match = df[(df['username'] == str(user_in).strip().lower()) & 
                   (df['password'] == str(pw_in).strip())]
        return not match.empty
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return False

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
                st.error("Invalid credentials or Connection Failed.")
    st.stop()

# --- 5. MAIN APPLICATION ---
st.title("🚀 Absa's Delta Exchange Scanner")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

def get_sentiment(p_chg, oi_chg):
    # REAL OI LOGIC
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: MARKET DASHBOARD ---
def fetch_market_dashboard(client):
    col1, col2, col3 = st.columns([1, 1, 2])
    
    try:
        # Fetch Ticker Data for BTC and ETH
        # Delta API usually returns a list of all tickers
        tickers = client.get_tickers()
        # Convert list to dictionary for easy access
        ticker_map = {t['symbol']: t for t in tickers}
        
        btc = ticker_map.get('BTCUSDT', {})
        eth = ticker_map.get('ETHUSDT', {})
        
        btc_price = float(btc.get('close', 0))
        btc_pct = float(btc.get('percent_change_24h', 0)) * 100 # Delta sends decimals like 0.05 for 5%
        
        eth_price = float(eth.get('close', 0))
        eth_pct = float(eth.get('percent_change_24h', 0)) * 100

        with col1:
            st.metric("BTCUSDT", f"${btc_price:,.2f}", f"{btc_pct:.2f}%")
        with col2:
            st.metric("ETHUSDT", f"${eth_price:,.2f}", f"{eth_pct:.2f}%")
        with col3:
            bias = "SIDEWAYS ↔️"
            color = "gray"
            if btc_pct > 0.5: 
                bias = "BULLISH 🚀"
                color = "green"
            elif btc_pct < -0.5: 
                bias = "BEARISH 📉"
                color = "red"
            st.markdown(f"""
                <div style="text-align: center; padding: 10px; border: 1px solid {color}; border-radius: 10px;">
                    <h3 style="margin:0; color: {color};">Market Bias: {bias}</h3>
                </div>
            """, unsafe_allow_html=True)
            
        return ticker_map # Pass this to the main loop to save API calls!
        
    except Exception as e:
        st.error(f"Dashboard Error: {e}")
        return {}

@st.fragment(run_every=300)
def refreshable_data_tables():
    # Initialize Delta Client (No API Key needed for public data usually)
    # If Delta India requires a specific base_url, add base_url='...' here
    delta_client = DeltaRestClient()
    
    # 1. SHOW DASHBOARD & GET ALL TICKERS (Optimized: 1 API Call)
    all_tickers = fetch_market_dashboard(delta_client)
    st.markdown("---")
    
    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Fetching Delta Exchange Data...")
    
    # If fetch failed, stop
    if not all_tickers:
        st.warning("Could not fetch data from Delta Exchange.")
        return

    for i, sym in enumerate(CRYPTO_PAIRS):
        try:
            # A. Get Live Data from the map we already fetched
            if sym not in all_tickers: continue
            
            ticker_data = all_tickers[sym]
            ltp = float(ticker_data['close'])
            p_change = float(ticker_data['percent_change_24h']) * 100
            
            # --- REAL OPEN INTEREST ---
            # Delta API typically includes 'oi' or 'open_interest' in the ticker endpoint
            curr_oi = float(ticker_data.get('open_interest', 0))
            
            # OI Change Logic
            if sym in st.session_state.oi_cache:
                prev_oi = st.session_state.oi_cache[sym]
                oi_chg_pct = ((curr_oi - prev_oi) / prev_oi) * 100 if prev_oi > 0 else 0
            else:
                oi_chg_pct = 0
            st.session_state.oi_cache[sym] = curr_oi # Update cache
            
            # B. Get History for EMA/RSI (This requires individual calls)
            # Resolution: 60 (1 hour)
            history = delta_client.get_history(symbol=sym, resolution=60)
            
            if history and len(history) > 30:
                # Delta returns earliest first, standard OHLC format
                df = pd.DataFrame(history)
                # Ensure columns are correct (Delta usually gives: t, o, h, l, c, v)
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
                
                # Active Momentum
                momentum_pct = round(((ltp - ema_5) / ema_5) * 100, 2)
                sentiment = get_sentiment(p_change, oi_chg_pct)
                
                # TradingView Link (Delta Exchange)
                # Link format: https://www.delta.exchange/app/futures/trade/BTCUSDT
                tv_url = f"https://www.delta.exchange/app/futures/trade/{sym}"
                
                row = {
                    "Symbol": tv_url,
                    "LTP": ltp,
                    "Mom %": momentum_pct,
                    "24h %": round(p_change, 2),
                    "RSI": round(curr_rsi, 1),
                    "ADX": round(curr_adx, 1),
                    "Sentiment": sentiment
                }
                
                if p_change > 0.5 and curr_rsi > 60 and curr_adx > 20:
                    bullish.append(row)
                elif p_change < -0.5 and curr_rsi < 45 and curr_adx > 20:
                    bearish.append(row)
            
            progress_bar.progress((i + 1) / len(CRYPTO_PAIRS))
        except Exception as e:
            # st.write(f"Error {sym}: {e}") # Uncomment to debug
            continue
    
    progress_bar.empty()
    
    column_config = {
        "Symbol": st.column_config.LinkColumn(
            "Pair (Click to Trade)", 
            display_text="(.*)USDT"
        ),
        "LTP": st.column_config.NumberColumn("Price ($)", format="$%.4f")
    }
    
    col1, col2 = st.columns(2)
    with col1:
        st.success("🟢 ACTIVE BULLS (Accelerating Up)")
        if bullish:
            st.dataframe(
                pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), 
                use_container_width=True, 
                hide_index=True,
                column_config=column_config
            )
        else:
            st.info("No bullish breakouts detected.")

    with col2:
        st.error("🔴 ACTIVE BEARS (Accelerating Down)")
        if bearish:
            st.dataframe(
                pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), 
                use_container_width=True, 
                hide_index=True,
                column_config=column_config
            )
        else:
            st.info("No bearish breakdowns detected.")

    # --- FOOTER ---
    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Last Data Sync:** {ist_time} IST (Auto-refreshing in 5 mins)")
    st.markdown("""
        <div style='text-align: center; color: grey; padding-top: 20px;'>
            Powered by : i-Tech World
        </div>
    """, unsafe_allow_html=True)

refreshable_data_tables()
