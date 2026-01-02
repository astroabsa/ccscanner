import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Crypto Scanner Pro", layout="wide")

# --- 2. GLOBAL SETTINGS (Yahoo Finance Symbols) ---
# We use 'BTC-USD' format which is reliable on Streamlit Cloud
CRYPTO_PAIRS = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'XRP-USD', 
    'DOGE-USD', 'ADA-USD', 'AVAX-USD', 'LINK-USD', 'DOT-USD', 
    'MATIC-USD', 'LTC-USD', 'ATOM-USD', 'NEAR-USD', 'UNI-USD', 
    'BCH-USD', 'ETC-USD', 'FIL-USD', 'APT-USD', 'ARB-USD',
    'OP-USD', 'INJ-USD', 'RNDR-USD', 'PEPE-USD', 'SUI-USD'
]

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
st.title("🚀 Absa's Crypto Scanner Pro")
if st.sidebar.button("Log out"):
    st.session_state["authenticated"] = False
    st.rerun()

def get_sentiment(p_chg, vol_chg):
    # Volume Analysis as Proxy for OI
    # Price UP + Volume UP = Strong Buying
    if p_chg > 0 and vol_chg > 0: return "Strong Buying 🚀"
    # Price DOWN + Volume UP = Strong Selling
    if p_chg < 0 and vol_chg > 0: return "Strong Selling 📉"
    # Price UP + Volume DOWN = Weak Buying (Caution)
    if p_chg > 0 and vol_chg < 0: return "Weak Buying ⚠️"
    # Price DOWN + Volume DOWN = Weak Selling (Caution)
    if p_chg < 0 and vol_chg < 0: return "Weak Selling 💤"
    return "Neutral ➖"

# --- HELPER: MARKET DASHBOARD (BTC/ETH) ---
def fetch_market_dashboard():
    col1, col2, col3 = st.columns([1, 1, 2])
    targets = {'BTC-USD': 'Bitcoin', 'ETH-USD': 'Ethereum'}
    data = {}
    
    for sym, name in targets.items():
        try:
            # Fetch 5 days history for robust calculation
            hist = yf.Ticker(sym).history(period="5d")
            if not hist.empty:
                ltp = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                chg = ltp - prev
                pct = (chg / prev) * 100
                data[sym] = {"ltp": ltp, "pct": pct}
            else:
                data[sym] = {"ltp": 0, "pct": 0}
        except:
            data[sym] = {"ltp": 0, "pct": 0}

    with col1:
        btc = data['BTC-USD']
        st.metric("BTC (USD)", f"${btc['ltp']:,.2f}", f"{btc['pct']:.2f}%")
        
    with col2:
        eth = data['ETH-USD']
        st.metric("ETH (USD)", f"${eth['ltp']:,.2f}", f"{eth['pct']:.2f}%")
        
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
    # 1. SHOW DASHBOARD
    fetch_market_dashboard()
    st.markdown("---")
    
    bullish, bearish = [], []
    progress_bar = st.progress(0, text="Fetching Live Crypto Data...")
    
    for i, sym in enumerate(CRYPTO_PAIRS):
        try:
            ticker = yf.Ticker(sym)
            data = ticker.history(period='5d', interval='1h') 
            
            if len(data) > 30:
                data['RSI'] = ta.rsi(data['Close'], length=14)
                adx_df = ta.adx(data['High'], data['Low'], data['Close'], length=14)
                data['EMA_5'] = ta.ema(data['Close'], length=5)
                
                ltp = data['Close'].iloc[-1]
                ema_5 = data['EMA_5'].iloc[-1]
                
                # Active Momentum (EMA Deviation)
                momentum_pct = round(((ltp - ema_5) / ema_5) * 100, 2)
                
                curr_rsi = data['RSI'].iloc[-1]
                curr_adx = adx_df['ADX_14'].iloc[-1]
                
                # Calculate Price Change (vs 24h ago approx)
                prev_close = data['Close'].iloc[-24] if len(data) >= 24 else data['Close'].iloc[0]
                p_change = round(((ltp - prev_close) / prev_close) * 100, 2)
                
                # Calculate Volume Change (Current vs Average)
                curr_vol = data['Volume'].iloc[-1]
                avg_vol = data['Volume'].tail(24).mean()
                vol_chg = curr_vol - avg_vol
                
                sentiment = get_sentiment(p_change, vol_chg)
                
                # TradingView Link (Binance Spot Format)
                clean_sym = sym.replace("-USD", "USDT") # BTC-USD -> BTCUSDT
                tv_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean_sym}"
                
                row = {
                    "Symbol": tv_url,
                    "LTP": round(ltp, 4), # 4 decimals for crypto
                    "Mom %": momentum_pct,
                    "24h %": p_change,
                    "RSI": round(curr_rsi, 1),
                    "ADX": round(curr_adx, 1),
                    "Sentiment": sentiment
                }
                
                if p_change > 0.5 and curr_rsi > 60 and curr_adx > 20:
                    bullish.append(row)
                elif p_change < -0.5 and curr_rsi < 45 and curr_adx > 20:
                    bearish.append(row)
            
            progress_bar.progress((i + 1) / len(CRYPTO_PAIRS))
        except:
            continue
    
    progress_bar.empty()
    
    column_config = {
        "Symbol": st.column_config.LinkColumn(
            "Pair (Click to Chart)", 
            display_text="symbol=BINANCE:(.*)"
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
