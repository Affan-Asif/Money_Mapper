import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import joblib
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import google.generativeai as genai

# ============================================================
#                   FASTAPI SETUP
# ============================================================
app = FastAPI(
    title="Cross-Border Intelligence API",
    description="Tax Evasion Risk, Fee Calculator, News Risk Intelligence (Gemini)",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
#                   API KEYS
# ============================================================
WISE_API_KEY = os.getenv("WISE_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-3.1-flash-lite")


# ============================================================
#            COUNTRY → CURRENCY & FEE TABLES
# ============================================================
COUNTRY_TO_CCY = {
    "USA": "USD", "Germany": "EUR", "UK": "GBP", "France": "EUR",
    "Japan": "JPY", "Canada": "CAD", "Netherlands": "EUR",
    "Switzerland": "CHF", "India": "INR", "Brazil": "BRL",
    "China": "CNY", "Mexico": "MXN", "South Africa": "ZAR",
}

BASE_ORIGIN_FEE = {
    "USA": 0.010, "Germany": 0.011, "UK": 0.012, "France": 0.011,
    "Japan": 0.010, "Canada": 0.010, "Netherlands": 0.011, "Switzerland": 0.010,
}

DEST_SURCHARGE = {
    "India": 0.003, "Brazil": 0.003, "China": 0.0025,
    "USA": 0.001, "Mexico": 0.003, "South Africa": 0.003,
    "UK": 0.0015,
}

INTERMEDIATE_BASE_SURCHARGE = 0.001
TAX_HAVENS = {"Cayman Islands", "Mauritius", "Luxembourg", "Hong Kong", "Singapore"}
TAX_HAVEN_EXTRA = 0.0015


# ============================================================
#                     WISE RATE HELPER
# ============================================================
def get_wise_rate(source: str, target: str) -> float:
    url = "https://api.transferwise.com/v1/rates"
    headers = {"Authorization": f"Bearer {WISE_API_KEY}"}
    params = {"source": source, "target": target}

    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()

    data = r.json()
    if not data:
        raise ValueError("No rate returned from Wise")

    return float(data[0]["rate"])


# ============================================================
#                 LOAD TAX EVASION MODEL
# ============================================================
model = joblib.load("best_tax_evasion_model.pkl")
df = pd.read_csv("PS3F_augmented_10000.csv")

categorical_cols = [
    "Origin Country", "Destination Country", "Intermediate Nodes",
    "Transaction Type", "Transaction Currency", "Tax Treaty Applicable"
]

encoders = {}
for col in categorical_cols:
    le = LabelEncoder()
    cleaned = df[col].fillna("Missing").astype(str)
    le.fit(cleaned)
    encoders[col] = le

numerical_cols = [
    c for c in df.columns
    if c not in categorical_cols + ["Tax Evasion Risk Index"]
]


# ============================================================
#                     REQUEST MODELS
# ============================================================
class RiskRequest(BaseModel):
    origin_country: str
    destination_country: str
    intermediate_nodes: str
    transaction_type: str
    transaction_currency: str
    tax_treaty_applicable: bool

class FeeRequest(BaseModel):
    amount: float
    origin: str
    destination: str
    intermediate_choice: str = "None"

class NewsRequest(BaseModel):
    country_name: str


# ============================================================
#           FEE CALCULATION LOGIC
# ============================================================
def parse_intermediate(choice: str):
    if choice == "None":
        return []
    return [p.strip() for p in choice.split(";") if p.strip()]

def calculate_fees_logic(req: FeeRequest):
    src_ccy = COUNTRY_TO_CCY[req.origin]
    dst_ccy = COUNTRY_TO_CCY[req.destination]

    mid_rate = get_wise_rate(src_ccy, dst_ccy)

    base_fee = BASE_ORIGIN_FEE[req.origin]
    dest_fee = DEST_SURCHARGE[req.destination]

    nodes = parse_intermediate(req.intermediate_choice)
    interm_fee = 0.0
    tax_haven_cnt = 0

    for n in nodes:
        interm_fee += INTERMEDIATE_BASE_SURCHARGE
        if n in TAX_HAVENS:
            interm_fee += TAX_HAVEN_EXTRA
            tax_haven_cnt += 1

    service_fee_pct = base_fee + dest_fee + interm_fee
    service_fee = req.amount * service_fee_pct

    gst_pct = 0.18 if "India" in (req.origin, req.destination) else 0.0
    gst_amount = service_fee * gst_pct
    total_fees_src = service_fee + gst_amount

    base_spread = 0.004
    extra_spread = tax_haven_cnt * 0.002
    fx_spread_pct = base_spread + extra_spread

    effective_rate = mid_rate * (1 - fx_spread_pct)
    recipient_gets = (req.amount - total_fees_src) * effective_rate
    fx_spread_cost = req.amount * mid_rate * fx_spread_pct

    return {
        "src_ccy": src_ccy,
        "dst_ccy": dst_ccy,
        "mid_rate": round(mid_rate, 6),
        "effective_rate": round(effective_rate, 6),
        "service_fee_pct": round(service_fee_pct * 100, 3),
        "service_fee": round(service_fee, 2),
        "gst_pct": round(gst_pct * 100, 1),
        "gst_amount": round(gst_amount, 2),
        "total_fees_src": round(total_fees_src, 2),
        "total_fee_pct": round(total_fees_src / req.amount * 100, 2),
        "fx_spread_pct": round(fx_spread_pct * 100, 3),
        "fx_spread_cost": round(fx_spread_cost, 2),
        "recipient_gets": round(recipient_gets, 2),
        "intermediate_nodes": nodes,
    }


# ============================================================
#               NEWS + GEMINI RISK ANALYSIS
# ============================================================
COUNTRY_CODE_MAP = {
    "india": "IN", "united states": "US", "usa": "US",
    "america": "US", "united kingdom": "GB", "uk": "GB",
    "england": "GB", "canada": "CA", "japan": "JP",
    "china": "CN", "brazil": "BR", "mexico": "MX",
    "south africa": "ZA", "france": "FR", "germany": "DE",
    "switzerland": "CH", "netherlands": "NL",
    "singapore": "SG", "hong kong": "HK", "ireland": "IE",
}

def convert_country_to_code(name):
    return COUNTRY_CODE_MAP.get(name.strip().lower())

def fetch_financial_news(country_name):
    code = convert_country_to_code(country_name)
    if not code:
        return None, f"Country '{country_name}' not supported."

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
        return None, "Error fetching news"

    data = resp.json()
    articles = data.get("results", [])

    cleaned = [
        {
            "title": a.get("title"),
            "description": a.get("description"),
            "link": a.get("link")
        }
        for a in articles[:5]
    ]

    return cleaned, None

def gemini_risk_summary(articles):
    text = ""
    for i, a in enumerate(articles, start=1):
        text += f"\n{i}. {a['title']}\n{a['description']}\n"

    prompt = f"""
    You are a financial intelligence engine.
    Give a 1-line risk summary based ONLY on the news:
    Articles:
    {text}
    """

    resp = gemini_model.generate_content(prompt)
    return resp.text.strip()


# ============================================================
#                       API ENDPOINTS
# ============================================================

@app.get("/")
def home():
    return {"message": "Unified Cross-Border Intelligence API is running!"}


@app.post("/predict")
async def predict_risk(req: RiskRequest):
    try:
        data = {
            "Origin Country": req.origin_country,
            "Destination Country": req.destination_country,
            "Intermediate Nodes": req.intermediate_nodes,
            "Transaction Type": req.transaction_type,
            "Transaction Currency": req.transaction_currency,
            "Tax Treaty Applicable": "Yes" if req.tax_treaty_applicable else "No",
        }

        encoded = {
            col: encoders[col].transform([val])[0]
            if val in encoders[col].classes_ else -1
            for col, val in data.items()
        }

        for col in numerical_cols:
            encoded[col] = df[col].mean()

        encoded["Nodes Count"] = req.intermediate_nodes.count(";") + 1

        input_df = pd.DataFrame([encoded])
        prediction = float(model.predict(input_df)[0])

        return {"success": True, "risk_index": round(prediction, 3)}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/calculate-fees")
async def calculate_fees(req: FeeRequest):
    try:
        return {"success": True, "data": calculate_fees_logic(req)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/news-risk")
async def news_risk(req: NewsRequest):
    articles, err = fetch_financial_news(req.country_name)

    if err:
        return {"success": False, "error": err}

    summary = gemini_risk_summary(articles)

    return {
        "success": True,
        "articles": articles,
        "summary": summary
    }






# import os
# from fastapi import FastAPI, Query
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# import requests
# import joblib
# import pandas as pd
# from sklearn.preprocessing import LabelEncoder
# import google.generativeai as genai

# # ============================================================
# #                   FASTAPI SETUP
# # ============================================================
# app = FastAPI(
#     title="Cross-Border Intelligence API",
#     description="Tax Evasion Risk, Fee Calculator, News Risk Intelligence (Gemini)",
#     version="3.0.1"
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ============================================================
# #                         API KEYS
# # ============================================================
# WISE_API_KEY = "YOUR_WISE_KEY"
# NEWSDATA_API_KEY = "YOUR_NEWSDATA_KEY"
# GEMINI_API_KEY = "YOUR_GEMINI_KEY"

# genai.configure(api_key=GEMINI_API_KEY)
# gemini_model = genai.GenerativeModel("gemini-2.5-flash")


# # ============================================================
# #            COUNTRY → CURRENCY & FEE TABLES
# # ============================================================
# COUNTRY_TO_CCY = {
#     "USA": "USD", "Germany": "EUR", "UK": "GBP", "France": "EUR",
#     "Japan": "JPY", "Canada": "CAD", "Netherlands": "EUR",
#     "Switzerland": "CHF", "India": "INR", "Brazil": "BRL",
#     "China": "CNY", "Mexico": "MXN", "South Africa": "ZAR",
# }

# BASE_ORIGIN_FEE = {
#     "USA": 0.010, "Germany": 0.011, "UK": 0.012, "France": 0.011,
#     "Japan": 0.010, "Canada": 0.010, "Netherlands": 0.011, "Switzerland": 0.010,
# }

# DEST_SURCHARGE = {
#     "India": 0.003, "Brazil": 0.003, "China": 0.0025,
#     "USA": 0.001, "Mexico": 0.003, "South Africa": 0.003,
#     "UK": 0.0015,
# }

# INTERMEDIATE_BASE_SURCHARGE = 0.001
# TAX_HAVENS = {"Cayman Islands", "Mauritius", "Luxembourg", "Hong Kong", "Singapore"}
# TAX_HAVEN_EXTRA = 0.0015


# # ============================================================
# #                     WISE RATE HELPER
# # ============================================================
# def get_wise_rate(source: str, target: str) -> float:
#     url = "https://api.transferwise.com/v1/rates"
#     headers = {"Authorization": f"Bearer {WISE_API_KEY}"}
#     params = {"source": source, "target": target}

#     r = requests.get(url, headers=headers, params=params, timeout=10)
#     r.raise_for_status()

#     data = r.json()
#     if not data:
#         raise ValueError("No rate returned from Wise")

#     return float(data[0]["rate"])


# # ============================================================
# #                 LOAD TAX EVASION MODEL
# # ============================================================
# model = joblib.load("best_tax_evasion_model.pkl")
# df = pd.read_csv("PS3F_augmented_10000.csv")

# categorical_cols = [
#     "Origin Country", "Destination Country", "Intermediate Nodes",
#     "Transaction Type", "Transaction Currency", "Tax Treaty Applicable"
# ]

# encoders = {}
# for col in categorical_cols:
#     le = LabelEncoder()
#     cleaned = df[col].fillna("Missing").astype(str)
#     le.fit(cleaned)
#     encoders[col] = le

# numerical_cols = [
#     c for c in df.columns
#     if c not in categorical_cols + ["Tax Evasion Risk Index"]
# ]


# # ============================================================
# #                     REQUEST MODELS
# # ============================================================
# class RiskRequest(BaseModel):
#     origin_country: str
#     destination_country: str
#     intermediate_nodes: str
#     transaction_type: str
#     transaction_currency: str
#     tax_treaty_applicable: bool


# class FeeRequest(BaseModel):
#     amount: float
#     origin: str
#     destination: str
#     intermediate_choice: str = "None"


# # ============================================================
# #               FEE CALCULATION LOGIC
# # ============================================================
# def parse_intermediate(choice: str):
#     if choice == "None":
#         return []
#     return [p.strip() for p in choice.split(";") if p.strip()]


# def calculate_fees_logic(req: FeeRequest):
#     src_ccy = COUNTRY_TO_CCY[req.origin]
#     dst_ccy = COUNTRY_TO_CCY[req.destination]

#     mid_rate = get_wise_rate(src_ccy, dst_ccy)

#     base_fee = BASE_ORIGIN_FEE[req.origin]
#     dest_fee = DEST_SURCHARGE[req.destination]

#     nodes = parse_intermediate(req.intermediate_choice)
#     interm_fee = 0.0
#     tax_haven_cnt = 0

#     for n in nodes:
#         interm_fee += INTERMEDIATE_BASE_SURCHARGE
#         if n in TAX_HAVENS:
#             interm_fee += TAX_HAVEN_EXTRA
#             tax_haven_cnt += 1

#     service_fee_pct = base_fee + dest_fee + interm_fee
#     service_fee = req.amount * service_fee_pct

#     gst_pct = 0.18 if "India" in (req.origin, req.destination) else 0.0
#     gst_amount = service_fee * gst_pct
#     total_fees_src = service_fee + gst_amount

#     base_spread = 0.004
#     extra_spread = tax_haven_cnt * 0.002
#     fx_spread_pct = base_spread + extra_spread

#     effective_rate = mid_rate * (1 - fx_spread_pct)
#     recipient_gets = (req.amount - total_fees_src) * effective_rate
#     fx_spread_cost = req.amount * mid_rate * fx_spread_pct

#     return {
#         "src_ccy": src_ccy,
#         "dst_ccy": dst_ccy,
#         "mid_rate": round(mid_rate, 6),
#         "effective_rate": round(effective_rate, 6),
#         "service_fee_pct": round(service_fee_pct * 100, 3),
#         "service_fee": round(service_fee, 2),
#         "gst_pct": round(gst_pct * 100, 1),
#         "gst_amount": round(gst_amount, 2),
#         "total_fees_src": round(total_fees_src, 2),
#         "total_fee_pct": round(total_fees_src / req.amount * 100, 2),
#         "fx_spread_pct": round(fx_spread_pct * 100, 3),
#         "fx_spread_cost": round(fx_spread_cost, 2),
#         "recipient_gets": round(recipient_gets, 2),
#         "intermediate_nodes": nodes,
#     }


# # ============================================================
# #               NEWS + GEMINI RISK ANALYSIS
# # ============================================================
# COUNTRY_CODE_MAP = {
#     "india": "IN", "united states": "US", "usa": "US",
#     "america": "US", "united kingdom": "GB", "uk": "GB",
#     "england": "GB", "canada": "CA", "japan": "JP",
#     "china": "CN", "brazil": "BR", "mexico": "MX",
#     "south africa": "ZA", "france": "FR", "germany": "DE",
#     "switzerland": "CH", "netherlands": "NL",
#     "singapore": "SG", "hong kong": "HK", "ireland": "IE",
# }


# def convert_country_to_code(name):
#     return COUNTRY_CODE_MAP.get(name.strip().lower())


# def fetch_financial_news(country_name):
#     code = convert_country_to_code(country_name)
#     if not code:
#         return None, f"Country '{country_name}' not supported."

#     url = "https://newsdata.io/api/1/news"
#     params = {
#         "apikey": NEWSDATA_API_KEY,
#         "q": "finance OR economy OR banking OR investment",
#         "country": code,
#         "language": "en",
#         "category": "business"
#     }

#     resp = requests.get(url, params=params)
#     if resp.status_code != 200:
#         return None, "Error fetching news"

#     data = resp.json()
#     articles = data.get("results", [])

#     cleaned = [
#         {
#             "title": a.get("title"),
#             "description": a.get("description"),
#             "link": a.get("link")
#         }
#         for a in articles[:5]
#     ]

#     return cleaned, None


# def gemini_risk_summary(articles):
#     text = ""
#     for i, a in enumerate(articles, start=1):
#         text += f"\n{i}. {a['title']}\n{a['description']}\n"

#     prompt = f"""
#     You are a financial intelligence engine.
#     Give a 1-line risk summary based ONLY on the news:
#     Articles:
#     {text}
#     """

#     resp = gemini_model.generate_content(prompt)
#     return resp.text.strip()


# # ============================================================
# #                       API ENDPOINTS
# # ============================================================
# @app.get("/")
# def home():
#     return {"message": "Unified Cross-Border Intelligence API is running!"}


# @app.post("/predict")
# async def predict_risk(req: RiskRequest):
#     try:
#         data = {
#             "Origin Country": req.origin_country,
#             "Destination Country": req.destination_country,
#             "Intermediate Nodes": req.intermediate_nodes,
#             "Transaction Type": req.transaction_type,
#             "Transaction Currency": req.transaction_currency,
#             "Tax Treaty Applicable": "Yes" if req.tax_treaty_applicable else "No",
#         }

#         encoded = {
#             col: encoders[col].transform([val])[0]
#             if val in encoders[col].classes_ else -1
#             for col, val in data.items()
#         }

#         for col in numerical_cols:
#             encoded[col] = df[col].mean()

#         encoded["Nodes Count"] = req.intermediate_nodes.count(";") + 1

#         input_df = pd.DataFrame([encoded])
#         prediction = float(model.predict(input_df)[0])

#         return {"success": True, "risk_index": round(prediction, 3)}

#     except Exception as e:
#         return {"success": False, "error": str(e)}


# @app.post("/calculate-fees")
# async def calculate_fees(req: FeeRequest):
#     try:
#         return {"success": True, "data": calculate_fees_logic(req)}
#     except Exception as e:
#         return {"success": False, "error": str(e)}


# # ============================================================
# #       MODIFIED NEWS-RISK ENDPOINT (Query Parameter)
# # ============================================================
# @app.get("/news-risk")
# async def news_risk(country_name: str = Query(..., description="Country to fetch news for")):
#     articles, err = fetch_financial_news(country_name)

#     if err:
#         return {"success": False, "error": err}

#     summary = gemini_risk_summary(articles)

#     return {
#         "success": True,
#         "country": country_name,
#         "articles": articles,
#         "summary": summary
#     }
