# import streamlit as st
# import pandas as pd
# import numpy as np
# import joblib

# # ------------------
# # Load Model + Data
# # ------------------
# model = joblib.load("best_tax_evasion_model.pkl")
# df = pd.read_csv("PS3F_augmented_10000.csv")

# # Required columns
# categorical_cols = [
#     "Origin Country", "Destination Country", "Intermediate Nodes",
#     "Transaction Type", "Transaction Currency", "Tax Treaty Applicable"
# ]
# numerical_cols = [
#     col for col in df.columns
#     if col not in categorical_cols + ["Tax Evasion Risk Index"]
# ]

# # Fit LabelEncoder separately for each col
# from sklearn.preprocessing import LabelEncoder
# encoders = {}
# for col in categorical_cols:
#     le = LabelEncoder()
#     df[col] = le.fit_transform(df[col])
#     encoders[col] = le

# st.title("Tax Evasion Risk Index Predictor")

# st.subheader("Input Parameters")

# # -------------------------
# # UI INPUTS (DROPDOWN + NUMBER)
# # -------------------------
# user_inputs = {}

# # Dropdowns for categorical columns
# for col in categorical_cols:
#     unique_vals = encoders[col].classes_.tolist()
#     selected = st.selectbox(f"{col}", unique_vals)
    
#     # Encode user input
#     user_inputs[col] = encoders[col].transform([selected])[0]

# # Inputs for numeric columns
# for col in numerical_cols:
#     default_val = float(df[col].mean())
#     val = st.number_input(col, value=default_val)
#     user_inputs[col] = val

# # Compute Nodes Count (same logic as your training code)
# if "Intermediate Nodes" in user_inputs:
#     text = st.write("Nodes Count auto-generated from Intermediate Nodes")
#     intermediate_text = encoders["Intermediate Nodes"].inverse_transform(
#         [user_inputs["Intermediate Nodes"]]
#     )[0]
#     nodes_count = str(intermediate_text).count(",") + 1
#     user_inputs["Nodes Count"] = nodes_count

# # Convert to DataFrame
# input_df = pd.DataFrame([user_inputs])

# # -------------------------
# # PREDICT BUTTON
# # -------------------------
# if st.button("Predict Risk Score"):
#     prediction = model.predict(input_df)[0]

#     st.success(f"Predicted Tax Evasion Risk Index: {round(prediction, 3)}")








# app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import numpy as np

app = FastAPI(title="Tax Evasion Risk Predictor API")

# Allow Flutter app to connect (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model and data
model = joblib.load("best_tax_evasion_model.pkl")
df = pd.read_csv("PS3F_augmented_10000.csv")

# Categorical columns
categorical_cols = [
    "Origin Country", "Destination Country", "Intermediate Nodes",
    "Transaction Type", "Transaction Currency", "Tax Treaty Applicable"
]

# Fit encoders once at startup
encoders = {}
for col in categorical_cols:
    le = LabelEncoder()
    # Handle NaN if any
    cleaned_col = df[col].fillna("Missing").astype(str)
    le.fit(cleaned_col)
    encoders[col] = le

# Numerical columns (all except categorical + target)
numerical_cols = [col for col in df.columns if col not in categorical_cols + ["Tax Evasion Risk Index"]]

class PredictionRequest(BaseModel):
    origin_country: str
    destination_country: str
    intermediate_nodes: str
    transaction_type: str
    transaction_currency: str
    tax_treaty_applicable: bool
    # Optional: add numeric fields later if needed

@app.post("/predict")
async def predict_risk(request: PredictionRequest):
    try:
        # Prepare input
        data = {
            "Origin Country": request.origin_country,
            "Destination Country": request.destination_country,
            "Intermediate Nodes": request.intermediate_nodes,
            "Transaction Type": request.transaction_type,
            "Transaction Currency": request.transaction_currency,
            "Tax Treaty Applicable": "Yes" if request.tax_treaty_applicable else "No"
        }

        # Encode categorical values
        encoded_data = {}
        for col, value in data.items():
            le = encoders[col]
            if value not in le.classes_:
                # Handle unseen labels
                encoded_data[col] = -1
            else:
                encoded_data[col] = le.transform([value])[0]

        # Add numeric columns with mean values (safe default)
        for col in numerical_cols:
            encoded_data[col] = df[col].mean()

        # Special: Nodes Count
        nodes_str = request.intermediate_nodes
        nodes_count = nodes_str.count(";") + 1
        encoded_data["Nodes Count"] = nodes_count

        # Create DataFrame
        input_df = pd.DataFrame([encoded_data])

        # Predict
        prediction = model.predict(input_df)[0]

        return {
            "success": True,
            "risk_index": round(float(prediction), 3)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/")
def home():
    return {"message": "Tax Evasion Risk API is running!"}