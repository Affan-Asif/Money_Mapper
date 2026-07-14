# import streamlit as st
# import requests
# import json
# # from dotenv import load_dotenv
# import os
# import google.generativeai as genai

# # -------------------- LOAD ENV --------------------
# # load_dotenv()
# NEWSDATA_API_KEY = "YOUR_NEWSDATA_KEY"
# GEMINI_API_KEY = "YOUR_GEMINI_KEY"

# if not NEWSDATA_API_KEY:
#     st.error("NEWSDATA_API_KEY missing in .env")
# if not GEMINI_API_KEY:
#     st.error("GEMINI_API_KEY missing in .env")

# # Gemini setup
# genai.configure(api_key=GEMINI_API_KEY)
# model = genai.GenerativeModel("gemini-2.5-flash")


# # -------------------- FUNCTION: GET NEWS --------------------
# def get_financial_news(country):
#     """
#     Uses NewsData.io free API to fetch latest business/finance news.
#     """
#     url = "https://newsdata.io/api/1/news"

#     params = {
#         "apikey": NEWSDATA_API_KEY,
#         "q": "finance OR economy OR banking OR investment",
#         "country": country.lower(),
#         "language": "en",
#         "category": "business"
#     }

#     resp = requests.get(url, params=params)
#     if resp.status_code != 200:
#         return None, f"Error fetching news: {resp.text}"

#     data = resp.json()
#     articles = data.get("results", [])

#     if not articles:
#         return None, "No financial news found."

#     # Extract top 5 articles
#     cleaned = []
#     for a in articles[:5]:
#         cleaned.append({
#             "title": a.get("title"),
#             "description": a.get("description"),
#             "link": a.get("link")
#         })

#     return cleaned, None


# # -------------------- FUNCTION: GEMINI ANALYSIS --------------------
# def analyze_risk_with_gemini(articles):
#     """
#     Send collected news text to Gemini and ask for a short risk summary.
#     """
#     text = ""

#     for i, a in enumerate(articles, start=1):
#         text += f"\n{i}. {a['title']}\n{a['description']}\n"

#     prompt = f"""
#     You are a financial risk intelligence system.
#     Based on the following recent news articles, identify any:
#     - financial discrepancies
#     - economic instability signs
#     - possible threats
#     - fraud/money laundering red flags
#     - regulatory risks

#     Give your answer in STRICTLY 1–2 lines.
    
#     Articles:
#     {text}
#     """

#     response = model.generate_content(prompt)
#     return response.text.strip()


# # -------------------- STREAMLIT UI --------------------
# st.title("🌍 Financial Threat Detector (News + Gemini AI)")

# country = st.text_input("Enter country name (e.g., India, USA, Brazil):")

# if st.button("Analyze Latest Financial Risks"):
#     if not country:
#         st.warning("Please enter a country.")
#     else:
#         with st.spinner("Fetching latest financial news..."):
#             articles, error = get_financial_news(country)

#         if error:
#             st.error(error)
#         else:
#             # Only display the AI summary header and analysis (no article list)
#             with st.spinner("Analyzing risks using Gemini..."):
#                 analysis = analyze_risk_with_gemini(articles)

#             st.subheader("⚠ Financial Risk Summary (AI)")
#             st.info(analysis)





import streamlit as st
import requests
import google.generativeai as genai

# -------------------- API KEYS --------------------
NEWSDATA_API_KEY = "YOUR_NEWSDATA_KEY"
GEMINI_API_KEY = "YOUR_GEMINI_KEY"

# Gemini setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# -------------------- COUNTRY NAME → CODE MAP --------------------
COUNTRY_CODE_MAP = {
    "india": "IN",
    "united states": "US",
    "usa": "US",
    "america": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "canada": "CA",
    "japan": "JP",
    "china": "CN",
    "brazil": "BR",
    "mexico": "MX",
    "south africa": "ZA",
    "france": "FR",
    "germany": "DE",
    "switzerland": "CH",
    "netherlands": "NL",
    "singapore": "SG",
    "hong kong": "HK",
    "ireland": "IE",
}

def convert_country_to_code(name):
    name = name.strip().lower()
    return COUNTRY_CODE_MAP.get(name)


# -------------------- FETCH NEWS FUNCTION --------------------
def get_financial_news(country_name):
    code = convert_country_to_code(country_name)

    if not code:
        return None, f"Country '{country_name}' is not supported. Add it to COUNTRY_CODE_MAP."

    url = "https://newsdata.io/api/1/news"

    params = {
        "apikey": NEWSDATA_API_KEY,
        "q": "finance OR economy OR banking OR investment",
        "country": code,
        "language": "en",
        "category": "business"
    }

    resp = requests.get(url, params=params)

    if resp.status_code != 200:
        return None, f"Error fetching news: {resp.text}"

    data = resp.json()
    articles = data.get("results", [])

    if not articles:
        return None, "No financial news found."

    cleaned = []
    for a in articles[:5]:
        cleaned.append({
            "title": a.get("title"),
            "description": a.get("description"),
            "link": a.get("link"),
        })

    return cleaned, None


# -------------------- GEMINI ANALYSIS --------------------
def analyze_risk_with_gemini(articles):
    text = ""

    for i, a in enumerate(articles, start=1):
        text += f"\n{i}. {a['title']}\n{a['description']}\n"

    prompt = f"""
    You are a financial intelligence model.
    Based ONLY on the provided news, summarize in 1 line:
    - financial discrepancies
    - economic instability
    - market risks
    - fraud or regulatory concerns
    - threats to currency/capital flows

    Articles:
    {text}
    """

    resp = model.generate_content(prompt)
    return resp.text.strip()


# -------------------- STREAMLIT UI --------------------
st.title("🌍 Financial Threat Detector (Latest News + Gemini AI)")

country_input = st.text_input("Enter a country name (e.g., India, USA, Brazil):")

if st.button("Analyze Financial Risk"):
    if not country_input:
        st.warning("Please enter a country.")
    else:
        with st.spinner("Fetching latest financial news..."):
            articles, error = get_financial_news(country_input)

        if error:
            st.error(error)

        else:
            with st.spinner("Analyzing risks using Gemini..."):
                summary = analyze_risk_with_gemini(articles)

            st.subheader("⚠ Financial Risk Summary")
            st.info(summary)
