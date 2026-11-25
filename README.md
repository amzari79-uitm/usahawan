# Business Profit Manager (Streamlit + Firebase)

Multi-business app: each business (name, owner, date created) has its own products,
indirect costs, gross profit/margin and break-even analysis.

## Firestore structure
```
businesses/{business_id}                      name, owner, date_created
businesses/{business_id}/products/{id}        name, price, units, materials, labour, other_direct
businesses/{business_id}/indirect_costs/{id}  category, description, amount
```

## Setup
1. Firebase Console -> create project -> Build -> Firestore Database -> Create database.
2. Project settings -> Service accounts -> Generate new private key (JSON).
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the JSON values.
4. `pip install -r requirements.txt` then `streamlit run app.py`

Never commit secrets.toml (already in .gitignore). On Streamlit Cloud, paste it in App settings -> Secrets.
