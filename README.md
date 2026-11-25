# Profit & Break-Even Manager (Streamlit + Firebase)

## Setup
1. Firebase Console -> create project -> Build -> Firestore Database -> Create database.
2. Project settings -> Service accounts -> Generate new private key (JSON).
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the JSON values.
4. `pip install -r requirements.txt` then `streamlit run app.py`

Collections created automatically: `products`, `indirect_costs`.
Do NOT commit secrets.toml. On Streamlit Cloud, paste it in App settings -> Secrets.
