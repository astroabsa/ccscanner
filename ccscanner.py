import streamlit as st
import requests
import pandas as pd

st.set_page_config(layout="wide", page_title="Absa's API Inspector")

st.title("🕵️ Delta India API Inspector")

# 1. Fetch Raw Tickers
BASE_URL = "https://api.india.delta.exchange"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

st.write("Connecting to:", BASE_URL)

try:
    resp = requests.get(f"{BASE_URL}/v2/tickers", headers=HEADERS)
    
    if resp.status_code == 200:
        data = resp.json()
        tickers = data.get('result', [])
        
        st.success(f"✅ Connection Successful! Fetched {len(tickers)} raw tickers.")
        
        if len(tickers) > 0:
            # 2. Show the First 5 Raw Items
            st.subheader("🧐 What do the symbols look like?")
            
            # Convert to DataFrame for easy viewing
            df = pd.DataFrame(tickers)
            
            # Show specific columns to check Symbol format
            cols_to_show = ['symbol', 'contract_type', 'mark_price', 'volume_24h']
            # Only show columns that actually exist in the data
            valid_cols = [c for c in cols_to_show if c in df.columns]
            
            st.dataframe(df[valid_cols].head(10), use_container_width=True)
            
            # 3. Check for 'USDT' existence
            usdt_pairs = [t['symbol'] for t in tickers if 'USDT' in t.get('symbol', '')]
            usd_pairs = [t['symbol'] for t in tickers if 'USD' in t.get('symbol', '')]
            inr_pairs = [t['symbol'] for t in tickers if 'INR' in t.get('symbol', '')]
            
            st.write(f"📊 **Symbol Analysis:**")
            st.write(f"- Pairs containing 'USDT': **{len(usdt_pairs)}** (Examples: {usdt_pairs[:3]})")
            st.write(f"- Pairs containing 'USD': **{len(usd_pairs)}** (Examples: {usd_pairs[:3]})")
            st.write(f"- Pairs containing 'INR': **{len(inr_pairs)}** (Examples: {inr_pairs[:3]})")
            
            st.info("💡 **Next Step:** Tell me which format is shown above (e.g., is it `BTCUSD` or `BTCINR`?) and I will update the main scanner code to match it!")
            
            with st.expander("View Full Raw JSON of First Item"):
                st.json(tickers[0])
        else:
            st.warning("⚠️ API connected but returned an empty list '[]'.")
    else:
        st.error(f"❌ API Error: Status Code {resp.status_code}")
        st.write(resp.text)

except Exception as e:
    st.error(f"💥 Critical Error: {e}")
