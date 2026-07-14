import streamlit as st
import requests
import os

# ---------- CONFIG ----------

WISE_API_KEY = "YOUR_WISE_KEY"
WISE_API_BASE = "https://api.transferwise.com"

ORIGINS = ['USA', 'Germany', 'UK', 'France', 'Japan', 'Canada',
           'Netherlands', 'Switzerland']

DESTINATIONS = ['India', 'Brazil', 'China', 'USA', 'Mexico',
                'South Africa', 'UK']

INTERMEDIATE_CHOICES = [
    'None',
    'Netherlands;Singapore',
    'Luxembourg',
    'Hong Kong',
    'Ireland',
    'Singapore',
    'Cayman Islands',
    'Mauritius',
    'Singapore;Hong Kong',
    'Luxembourg;Cayman Islands',
    'Luxembourg;Hong Kong',
]

COUNTRY_TO_CCY = {
    "USA": "USD",
    "Germany": "EUR",
    "UK": "GBP",
    "France": "EUR",
    "Japan": "JPY",
    "Canada": "CAD",
    "Netherlands": "EUR",
    "Switzerland": "CHF",

    "India": "INR",
    "Brazil": "BRL",
    "China": "CNY",
    "Mexico": "MXN",
    "South Africa": "ZAR",
}

BASE_ORIGIN_FEE = {
    "USA": 0.010,
    "Germany": 0.011,
    "UK": 0.012,
    "France": 0.011,
    "Japan": 0.010,
    "Canada": 0.010,
    "Netherlands": 0.011,
    "Switzerland": 0.010,
}

DEST_SURCHARGE = {
    "India": 0.003,
    "Brazil": 0.003,
    "China": 0.0025,
    "USA": 0.001,
    "Mexico": 0.003,
    "South Africa": 0.003,
    "UK": 0.0015,
}

INTERMEDIATE_BASE_SURCHARGE = 0.001
TAX_HAVENS = {"Cayman Islands", "Mauritius", "Luxembourg", "Hong Kong", "Singapore"}
TAX_HAVEN_EXTRA = 0.0015


# ---------- HELPERS ----------

def get_wise_rate(source_ccy: str, target_ccy: str) -> float:
    """
    Get mid-market FX rate from Wise API.
    """
    url = f"{WISE_API_BASE}/v1/rates"
    headers = {"Authorization": f"Bearer {WISE_API_KEY}"}
    params = {"source": source_ccy, "target": target_ccy}

    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError("No rate data from Wise")
    return float(data[0]["rate"])


def parse_intermediate(choice: str):
    """
    'Luxembourg;Cayman Islands' -> ['Luxembourg', 'Cayman Islands']
    'None'                       -> []
    """
    if choice == "None":
        return []
    parts = [p.strip() for p in choice.split(";") if p.strip()]
    return parts


def calculate_fees(amount: float, origin: str, destination: str,
                   intermediate_str: str):
    src_ccy = COUNTRY_TO_CCY[origin]
    dst_ccy = COUNTRY_TO_CCY[destination]

    # 1) FX rate from Wise
    mid_rate = get_wise_rate(src_ccy, dst_ccy)

    # 2) Service fee %
    base_fee = BASE_ORIGIN_FEE[origin]
    dest_fee = DEST_SURCHARGE[destination]

    intermediate_nodes = parse_intermediate(intermediate_str)

    interm_fee = 0.0
    num_tax_havens = 0
    for node in intermediate_nodes:
        interm_fee += INTERMEDIATE_BASE_SURCHARGE
        if node in TAX_HAVENS:
            interm_fee += TAX_HAVEN_EXTRA
            num_tax_havens += 1

    service_fee_pct = base_fee + dest_fee + interm_fee
    service_fee = amount * service_fee_pct

    # 3) GST
    gst_pct = 0.18 if ("India" in (origin, destination)) else 0.0
    gst_amount = service_fee * gst_pct

    # 4) Bank fee (you can tweak this)
    bank_fee_flat = 0.0

    total_fees_src = bank_fee_flat + service_fee + gst_amount

    # 5) FX spread %
    base_spread_pct = 0.004
    extra_spread_per_tax_haven = 0.002
    fx_spread_pct = base_spread_pct + num_tax_havens * extra_spread_per_tax_haven

    effective_rate = mid_rate * (1 - fx_spread_pct)
    fx_spread_cost = amount * mid_rate * fx_spread_pct  # in dst_ccy

    # 6) Recipient gets
    net_amount_src = max(amount - total_fees_src, 0.0)
    recipient_gets = net_amount_src * effective_rate

    total_fee_pct = (total_fees_src / amount * 100) if amount > 0 else 0.0

    return {
        "src_ccy": src_ccy,
        "dst_ccy": dst_ccy,
        "mid_rate": mid_rate,
        "effective_rate": effective_rate,
        "service_fee_pct": service_fee_pct,
        "service_fee": service_fee,
        "gst_pct": gst_pct,
        "gst_amount": gst_amount,
        "bank_fee": bank_fee_flat,
        "total_fees_src": total_fees_src,
        "total_fee_pct": total_fee_pct,
        "fx_spread_pct": fx_spread_pct,
        "fx_spread_cost": fx_spread_cost,
        "recipient_gets": recipient_gets,
        "intermediate_nodes": intermediate_nodes,
    }


# ---------- STREAMLIT UI ----------

def main():
    st.set_page_config(page_title="Route-based Fee Calculator", layout="centered")
    st.title("Cross-Border Route Fee Calculator")

    amount = st.number_input("You send exactly", min_value=0.0,
                             value=100000.0, step=1000.0)

    col1, col2 = st.columns(2)
    with col1:
        origin = st.selectbox("Origin country", ORIGINS)
    with col2:
        destination = st.selectbox("Destination country", DESTINATIONS)

    intermediate_choice = st.selectbox(
        "Intermediate route (optional)",
        INTERMEDIATE_CHOICES,
        index=0
    )

    if st.button("Calculate"):
        try:
            res = calculate_fees(amount, origin, destination, intermediate_choice)

            st.subheader("Recipient gets")
            st.success(f"{res['recipient_gets']:.2f} {res['dst_ccy']}")

            st.write(f"Mid-market rate: {res['mid_rate']:.6f} "
                     f"{res['dst_ccy']}/{res['src_ccy']}")
            st.write(f"Effective rate (after FX spread): "
                     f"{res['effective_rate']:.6f} {res['dst_ccy']}/{res['src_ccy']}")

            st.markdown("### Fee breakdown (in origin currency)")
            st.write(f"Service fee ({res['service_fee_pct']*100:.2f}%): "
                     f"{res['service_fee']:.2f} {res['src_ccy']}")
            st.write(f"GST ({res['gst_pct']*100:.1f}% on fee): "
                     f"{res['gst_amount']:.2f} {res['src_ccy']}")
            st.write(f"Bank fee: {res['bank_fee']:.2f} {res['src_ccy']}")
            st.write(f"**Total included fees**: {res['total_fees_src']:.2f} "
                     f"{res['src_ccy']} ({res['total_fee_pct']:.2f}%)")

            st.markdown("### FX spread")
            st.write(f"FX spread: {res['fx_spread_pct']*100:.2f}%")
            st.write(f"Cost of FX spread: {res['fx_spread_cost']:.2f} {res['dst_ccy']}")

            if res["intermediate_nodes"]:
                st.info("Intermediate nodes used: " +
                        ", ".join(res["intermediate_nodes"]))
            else:
                st.info("Direct route (no intermediate)")

        except Exception as e:
            st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
