import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Crypto F&O Scanner", layout="wide")

# --- 2. GLOBAL SETTINGS ---
# Top Liquid Crypto Futures Pairs (USDT-M)
CRYPTO_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 
    'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 
    'MATIC/USDT', 'LTC/USDT', 'ATOM/USDT', 'NEAR/USDT', 'UNI/USDT', 
    'BCH/USDT', 'ETC/USDT', 'FIL/USDT', 'APT/USDT', 'ARB/USDT',
    'OP/USDT', 'INJ/USDT', 'RNDR/USDT', 'PEPE/USDT', 'SUI/USDT'
]

# Initialize Session State for OI Tracking (to calculate OI Change)
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
    st.title("🔐 Absa's Crypto Pro Login")
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
st.title("🚀 Absa's Crypto Futures Scanner (Binance)")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

def get_sentiment(p_chg, oi_chg):
    # Interpretation of Price vs OI
    if p_chg > 0 and oi_chg > 0: return "Long Buildup 🚀"
    if p_chg < 0 and oi_chg > 0: return "Short Buildup 📉"
    if p_chg < 0 and oi_chg < 0: return "Long Unwinding ⚠️"
    if p_chg > 0 and oi_chg < 0: return "Short Covering 💨"
    return "Neutral ➖"

# --- HELPER: MARKET DASHBOARD (BTC/ETH) ---
def fetch_market_dashboard(exchange):
    col1, col2, col3 = st.columns([1, 1, 2])
    
    targets = ['BTC/USDT', 'ETH/USDT']
    data = {}
    
    for sym in targets:
        try:
            ticker = exchange.fetch_ticker(sym)
            ltp = ticker['last']
            pct = ticker['percentage'] # 24h change %
            chg = ticker['change']
            data[sym] = {"ltp": ltp, "pct": pct, "chg": chg}
        except:
            data[sym] = {"ltp": 0, "pct": 0, "chg": 0}

    with col1:
        btc = data['BTC/USDT']
        st.metric("BTC/USDT", f"${btc['ltp']:,.2f}", f"{btc['pct']:.2f}%")
        
    with col2:
        eth = data['ETH/USDT']
        st.metric("ETH/USDT", f"${eth['ltp']:,.2f}", f"{eth['pct']:.2f}%")
        
    with col3:
        bias = "SIDEWAYS ↔️"
        color = "gray"
        if btc['pct'] > 0.5: 
            bias = "BULLISH 🚀"
            color = "green"
        elif btc['pct'] < -0.5: 
            bias = "BEARISH 📉"
            color = "red"
            
        st.markdown(f"""
            <div style="text-align: center; padding: 10px; border: 1px solid {color}; border-radius: 10px;">
                <h3 style="margin:0; color: {color};">Market Bias: {bias}</h3>
            </div>
        """, unsafe_allow_html=True)

@st.fragment(run_every=300)
def refreshable_data_tables():
    # Initialize CCXT Binance Futures
    exchange = ccxt.binanceusdm() 
    
    # 1. SHOW DASHBOARD
    fetch_market_dashboard(exchange)
    st.markdown("---")
    
    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Fetching Binance Futures Data...")
    
    for i, sym in enumerate(CRYPTO_PAIRS):
        try:
            # A. Fetch OHLCV (Hourly)
            ohlcv = exchange.fetch_ohlcv(sym, timeframe='1h', limit=60)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # B. Fetch Live Ticker (for Open Price & 24h stats)
            ticker_info = exchange.fetch_ticker(sym)
            
            # C. Fetch Open Interest
            try:
                oi_data = exchange.fetch_open_interest(sym)
                curr_oi = float(oi_data['openInterest'])
            except:
                curr_oi = 0
            
            # --- OI CHANGE LOGIC (Session State) ---
            # If we saw this symbol before, calculate change. If new, change is 0.
            if sym in st.session_state.oi_cache:
                prev_oi = st.session_state.oi_cache[sym]
                oi_chg_val = curr_oi - prev_oi
                # Percentage change of OI
                oi_chg_pct = ((curr_oi - prev_oi) / prev_oi) * 100 if prev_oi > 0 else 0
            else:
                oi_chg_pct = 0
            
            # Update cache for next refresh
            st.session_state.oi_cache[sym] = curr_oi
            
            if len(df) > 30:
                # Indicators
                df['RSI'] = ta.rsi(df['close'], length=14)
                adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
                df['EMA_5'] = ta.ema(df['close'], length=5)
                
                ltp = df['close'].iloc[-1]
                ema_5 = df['EMA_5'].iloc[-1]
                curr_rsi = df['RSI'].iloc[-1]
                curr_adx = adx_df['ADX_14'].iloc[-1]
                
                # Active Momentum (EMA Deviation)
                momentum_pct = round(((ltp - ema_5) / ema_5) * 100, 2)
                
                # 24h Change (from Ticker)
                p_change = float(ticker_info['percentage'])
                
                # Determine Sentiment
                sentiment = get_sentiment(p_change, oi_chg_pct)
                
                # TradingView Link (Binance Futures format)
                clean_sym = sym.replace("/", "") # BTC/USDT -> BTCUSDT
                tv_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_sym}.P"
                
                row = {
                    "Symbol": tv_url,
                    "LTP": ltp,
                    "Mom %": momentum_pct, # Active Trend
                    "24h %": round(p_change, 2),
                    "RSI": round(curr_rsi, 1),
                    "ADX": round(curr_adx, 1),
                    "Sentiment": sentiment
                }
                
                # Logic: RSI > 60 (Bull) / RSI < 45 (Bear) + ADX > 20
                if p_change > 0.5 and curr_rsi > 60 and curr_adx > 20:
                    bullish.append(row)
                elif p_change < -0.5 and curr_rsi < 45 and curr_adx > 20:
                    bearish.append(row)
            
            progress_bar.progress((i + 1) / len(CRYPTO_PAIRS))
        except Exception as e:
            continue
    
    progress_bar.empty()
    
    column_config = {
        "Symbol": st.column_config.LinkColumn(
            "Pair (Click to Chart)", 
            display_text="symbol=BINANCE:(.*).P" # Shows "BTCUSDT" text
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
