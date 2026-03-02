import os
import requests
from dotenv import load_dotenv
import streamlit as st

# -------------------------------------------------------
# Load environment
# -------------------------------------------------------
load_dotenv()
FX_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

FX_BASE_URL = "https://v6.exchangerate-api.com/v6"


# -------------------------------------------------------
# Helper: Call ExchangeRate API
# -------------------------------------------------------
def get_fx_rates(base_currency: str):
    url = f"{FX_BASE_URL}/{FX_API_KEY}/latest/{base_currency}"
    try:
        response = requests.get(url)
        data = response.json()
        return data
    except Exception as e:
        return {"error": str(e)}


# -------------------------------------------------------
# Helper: Call your FastAPI backend for route analysis
# -------------------------------------------------------
def get_route_analysis(source, dest, amount):
    url = f"{BACKEND_URL}/routes"
    payload = {
        "source_country": source,
        "dest_country": dest,
        "amount": amount
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


# -------------------------------------------------------
# Streamlit UI Config
# -------------------------------------------------------
st.set_page_config(
    page_title="Global Capital Routing Dashboard",
    layout="wide"
)

st.title("Global Capital Routing & FX Intelligence Dashboard")
st.markdown("Analyze **Cheapest**, **Fastest**, and **Safest** routes internationally + Live FX rates.")

# -------------------------------------------------------
# SECTION 1: LIVE FX CONVERTER
# -------------------------------------------------------
st.header("1. Live FX Converter")

CURRENCIES = ["INR", "USD", "EUR", "GBP", "SGD", "AED", "JPY", "AUD", "CAD", "CHF", "CNY"]

col1, col2, col3 = st.columns(3)
with col1:
    base_currency = st.selectbox("Base Currency", CURRENCIES, index=0)
with col2:
    target_currency = st.selectbox("Target Currency", CURRENCIES, index=1)
with col3:
    fx_amount = st.number_input("Amount", min_value=0.0, value=100000.0)

if st.button("Get Live FX Rate"):
    fx_data = get_fx_rates(base_currency)

    if fx_data.get("result") == "success":
        rate = fx_data["conversion_rates"].get(target_currency)
        if rate:
            converted = fx_amount * rate
            st.success(f"1 {base_currency} = {rate:.4f} {target_currency}")
            st.info(f"Converted Amount: {converted:,.2f} {target_currency}")
        else:
            st.error("Target currency not found in API response.")
    else:
        st.error("Failed to load FX data.")


st.markdown("---")

# -------------------------------------------------------
# SECTION 2: ROUTE ANALYSIS (Cheapest / Fastest / Safest)
# -------------------------------------------------------
st.header("2. Cross-Border Route Analysis (Cheapest / Fastest / Safest)")

colA, colB, colC = st.columns(3)
with colA:
    source_country = st.selectbox("Source Country", ["India", "Singapore", "UAE", "USA"])
with colB:
    dest_country = st.selectbox("Destination Country", ["USA", "Singapore", "India", "UAE"])
with colC:
    amount = st.number_input("Amount to Transfer (INR)", min_value=1000, value=100000, step=1000)

if st.button("Analyze Routes"):
    results = get_route_analysis(source_country, dest_country, amount)

    if "routes" in results:

        st.subheader("Route Comparison Table")

        for r in results["routes"]:
            route_str = " → ".join(r["route"])

            with st.container():
                st.markdown(f"### Route: {route_str}")

                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**Total Cost:** ₹{r['total_cost']:,.2f}")
                with col2:
                    st.write(f"**Speed:** {r['total_speed_days']} days")
                with col3:
                    st.write(f"**Risk:** {r['total_risk']}")
                with col4:
                    st.write(f"**Received:** ₹{r['effective_amount_received']:,.2f}")

                badge = ""
                if r["is_cheapest"]:
                    badge += "🟢 **Cheapest**  "
                if r["is_fastest"]:
                    badge += "🔵 **Fastest**  "
                if r["is_safest"]:
                    badge += "🟡 **Safest**"

                if badge:
                    st.success(badge)
                st.markdown("---")

    else:
        st.error("Error fetching route analysis from backend.")


# -------------------------------------------------------
# FOOTER
# -------------------------------------------------------
st.markdown("Built with ExchangeRate API + FastAPI backend.")












