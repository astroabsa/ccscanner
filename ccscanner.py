import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import pytz
from datetime import datetime, timedelta
import time

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Absa's Delta India Detective", layout="wide")
BASE_URL = "https://api.india.delta.exchange"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- 2. AUTHENTICATION ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = True # Auto-login

# --- 3. MAIN APP ---
st.title("🕵️ Delta API Detective: Cracking the Code")

# Fetch ONE active pair to test on
st.info("Fetching a valid Product ID to test...")
try:
    resp = requests.get(f"{BASE_URL}/v2/tickers", headers=HEADERS)
    tickers = resp.json().get('result', [])
    # Find BTCUSDT or similar
    target = next((t for t in tickers if 'BTC' in t['symbol'] and 'USD' in t['symbol']), None)
    
    if not target:
        st.error("Could not find BTC pair to test.")
        st.stop()
        
    product_id = target['product_id']
    symbol = target['symbol']
    st.success(f"Target Acquired: **{symbol}** (ID: {product_id})")
    
except Exception as e:
    st.error(f"Setup failed: {e}")
    st.stop()

st.markdown("---")
st.subheader("🧪 Experiment Results")

# --- EXPERIMENT 1: Resolution '60' ---
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### Attempt 1: Resolution '60'")
    params = {'product_id': product_id, 'resolution': '60', 'limit': 50}
    try:
        r = requests.get(f"{BASE_URL}/v2/history/candles", params=params, headers=HEADERS)
        if r.status_code == 200:
            count = len(r.json().get('result', []))
            st.success(f"✅ Success! Got {count} candles.")
            st.write(r.json().get('result', [])[:2]) # Show sample
        else:
            st.error(f"❌ Failed: {r.status_code}")
            st.code(r.text) # PRINT THE ERROR MESSAGE
    except Exception as e:
        st.error(f"Error: {e}")

# --- EXPERIMENT 2: Resolution '1h' ---
with col2:
    st.markdown("### Attempt 2: Resolution '1h'")
    params = {'product_id': product_id, 'resolution': '1h', 'limit': 50}
    try:
        r = requests.get(f"{BASE_URL}/v2/history/candles", params=params, headers=HEADERS)
        if r.status_code == 200:
            count = len(r.json().get('result', []))
            st.success(f"✅ Success! Got {count} candles.")
        else:
            st.error(f"❌ Failed: {r.status_code}")
            st.code(r.text) # PRINT THE ERROR MESSAGE
    except Exception as e:
        st.error(f"Error: {e}")

# --- EXPERIMENT 3: Chart Endpoint (Fallback) ---
with col3:
    st.markdown("### Attempt 3: Chart API (1h)")
    # Calculate timestamps
    to_ts = int(time.time())
    from_ts = to_ts - (30 * 24 * 60 * 60) # 30 days
    url = f"{BASE_URL}/v2/chart/history?symbol={symbol}&resolution=60&from={from_ts}&to={to_ts}"
    try:
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 200:
            data = r.json().get('result', [])
            count = len(data)
            st.warning(f"⚠️ Status 200 but got {count} candles.")
            st.write(f"First candle time: {data[0]['time'] if data else 'None'}")
        else:
            st.error(f"❌ Failed: {r.status_code}")
    except Exception as e:
        st.error(f"Error: {e}")
