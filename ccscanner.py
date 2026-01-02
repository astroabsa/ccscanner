import streamlit as st
from delta_rest_client import DeltaRestClient
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Scanner", layout="wide")

# --- 2. GLOBAL SETTINGS ---
# Delta India Symbols 
CRYPTO_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 
    'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT', 
    'MATICUSDT', 'LTCUSDT', 'ATOMUSDT', 'NEARUSDT', 'UNIUSDT', 
    'BCHUSDT', 'ETCUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT'
]

# Initialize Session State
if "oi_cache" not in st.session_state:
    st.session_state.oi_cache = {}

# --- 3. AUTHENTICATION ---
def authenticate_user(user_in, pw_in):
    try:
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
                st.error("Invalid credentials.")
    st.stop()

# --- 5. MAIN APPLICATION ---
st.title("🚀 Absa's Delta India Scanner")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

def get_sentiment(p_chg, oi_chg):
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: FETCH DATA ---
def fetch_market_dashboard(client):
    col1, col2, col3 = st.columns([1, 1, 2])
    
    # We will fetch 'products' to get the list of ALL pairs and their IDs
    # This acts as our "master map"
    try:
        products = client.get_products()
        # Create a dictionary: {'BTCUSDT': {'id': 123, 'symbol': 'BTCUSDT'}, ...}
        product_map = {p['symbol']: p for p in products}
        
        # Now fetch Price for Dashboard
        # Note: We must fetch tickers individually as there is no "get_all_tickers" method
        btc_ticker = client.get_ticker('BTCUSDT')
        eth_ticker = client.get_ticker('ETHUSDT')
        
        # Parse BTC
        btc_price = float(btc_ticker['close'])
        # Delta gives 24h change as a price difference, not percent directly sometimes, 
        # but usually 'percent_change_24h' exists in the product or ticker response.
        # Let's calculate manually to be safe: ((Close - Open) / Open) * 100
        btc_open = float(btc_ticker['open'])
        btc_pct = ((btc_price - btc_open) / btc_open) * 100
        
        # Parse ETH
        eth_price = float(eth_ticker['close'])
        eth_open = float(eth_ticker['open'])
        eth_pct = ((eth_price - eth_open) / eth_open) * 100

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
            
        return product_map
        
    except Exception as e:
        st.error(f"API Connection Error: {e}")
        return {}

@st.fragment(run_every=300)
def refreshable_data_tables():
    # 1. INITIALIZE CLIENT CORRECTLY
    # Base URL for India is crucial. API keys can be empty for public data.
    delta_client = DeltaRestClient(
        base_url='https://api.india.delta.exchange',
        api_key='3C0Ms8rQBuVGbCOi7ZDDUbnE2ur1P5',
        api_secret='v0GeBUZXG9hdKEm7EG3rL4EzcKvndjD0MSgOyhv6AxywY8ogHUx91zyd2a29'
    )
    
    # 2. GET PRODUCT MAP (IDs)
    product_map = fetch_market_dashboard(delta_client)
    st.markdown("---")
    
    if not product_map:
        st.stop()

    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Fetching Delta Data...")
    
    for i, sym in enumerate(CRYPTO_PAIRS):
        try:
            if sym not in product_map: continue
            
            # Get Product ID (Required for History)
            pid = product_map[sym]['id']
            
            # Get Live Ticker (Price, OI)
            ticker = delta_client.get_ticker(sym)
            ltp = float(ticker['close'])
            
            # Calculate 24h Change %
            open_24h = float(ticker['open'])
            p_change = ((ltp - open_24h) / open_24h) * 100
            
            # Open Interest
            # Delta Ticker response usually has 'open_interest' (contracts)
            # We use 'size' or value depending on what they return, usually pure number of contracts
            curr_oi = float(ticker.get('open_interest', 0))
            
            if sym in st.session_state.oi_cache:
                prev_oi = st.session_state.oi_cache[sym]
                oi_chg_pct = ((curr_oi - prev_oi) / prev_oi) * 100 if prev_oi > 0 else 0
            else:
                oi_chg_pct = 0
            st.session_state.oi_cache[sym] = curr_oi
            
            # Get History (Candles)
            # Resolution 60 = 1 Hour
            # We use the generic 'request' method to hit the candles endpoint safely
            # Endpoint: /v2/history/candles
            params = {
                'product_id': pid,
                'resolution': 60,
                'limit': 60
            }
            history_resp = delta_client.request("GET", "/v2/history/candles", params)
            
            if history_resp and len(history_resp) > 30:
                # API returns list of dicts: [{'t':..., 'o':..., 'h':..., 'l':..., 'c':...}]
                df = pd.DataFrame(history_resp)
                # Ensure columns are float
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
                
                if p_change > 0.5 and curr_rsi > 60 and curr_adx > 20:
                    bullish.append(row)
                elif p_change < -0.5 and curr_rsi < 45 and curr_adx > 20:
                    bearish.append(row)
                    
            progress_bar.progress((i + 1) / len(CRYPTO_PAIRS))
        except Exception:
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
            st.dataframe(pd.DataFrame(bullish).sort_values(by="Mom %", ascending=False).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bullish breakouts detected.")

    with col2:
        st.error("🔴 ACTIVE BEARS (Accelerating Down)")
        if bearish:
            st.dataframe(pd.DataFrame(bearish).sort_values(by="Mom %", ascending=True).head(10), 
                         use_container_width=True, hide_index=True, column_config=column_config)
        else:
            st.info("No bearish breakdowns detected.")

    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')
    st.write(f"🕒 **Last Data Sync:** {ist_time} IST (Auto-refreshing in 5 mins)")
    st.markdown("<div style='text-align: center; color: grey; padding-top: 20px;'>Powered by : i-Tech World</div>", unsafe_allow_html=True)

refreshable_data_tables()
