import math
from datetime import date

import pandas as pd
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="Business Profit Manager", page_icon="📊", layout="wide")

BUSINESSES = "businesses"
PRODUCTS = "products"
INDIRECT = "indirect_costs"
CATEGORIES = [
    "Rent",
    "Utilities",
    "Salaries",
    "Marketing",
    "Insurance",
    "Depreciation",
    "Other Overheads",
]

# Firestore layout
# businesses/{business_id}                      -> name, owner, date_created
# businesses/{business_id}/products/{id}        -> product + direct cost data
# businesses/{business_id}/indirect_costs/{id}  -> indirect cost entries


# ---------------------------------------------------------------- Firebase
@st.cache_resource
def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(cred)
    return firestore.client()


db = get_db()


def biz_sub(bid, name):
    return db.collection(BUSINESSES).document(bid).collection(name)


def list_docs(col):
    rows = []
    for d in col.stream():
        item = d.to_dict()
        item["id"] = d.id
        rows.append(item)
    return rows


def add_doc(col, data):
    _, ref = col.add({**data, "created_at": firestore.SERVER_TIMESTAMP})
    return ref.id


def update_doc(col, doc_id, data):
    col.document(doc_id).update(data)


def delete_doc(col, doc_id):
    col.document(doc_id).delete()


def delete_business(bid):
    """Delete a business and everything under it."""
    for sub in (PRODUCTS, INDIRECT):
        for d in biz_sub(bid, sub).stream():
            d.reference.delete()
    db.collection(BUSINESSES).document(bid).delete()


def money(x):
    return f"RM{x:,.2f}"


# ---------------------------------------------------------------- Calculations
def build_product_df(products):
    rows = []
    for p in products:
        direct = p.get("materials", 0) + p.get("labour", 0) + p.get("other_direct", 0)
        price = p.get("price", 0)
        units = p.get("units", 0)
        gp_unit = price - direct
        rows.append(
            {
                "id": p["id"],
                "Product": p.get("name", ""),
                "Price": price,
                "Direct Cost/Unit": direct,
                "Gross Profit/Unit": gp_unit,
                "Gross Margin %": (gp_unit / price * 100) if price else 0.0,
                "Units/Month": units,
                "Revenue": price * units,
                "Total Direct Cost": direct * units,
                "Gross Profit": gp_unit * units,
            }
        )
    df = pd.DataFrame(rows)
    return df.sort_values("Product").reset_index(drop=True) if not df.empty else df


def break_even(df, fixed, target=0.0):
    """Multi-product break-even using the expected sales mix."""
    total_units = df["Units/Month"].sum()
    if total_units <= 0:
        return None
    wacm = (df["Gross Profit/Unit"] * df["Units/Month"]).sum() / total_units
    if wacm <= 0:
        return None
    be_units_total = (fixed + target) / wacm
    mix = df["Units/Month"] / total_units
    per_units = (be_units_total * mix).apply(math.ceil)
    per_sales = per_units * df["Price"]
    return {
        "wacm": wacm,
        "units": math.ceil(be_units_total),
        "sales": float(per_sales.sum()),
        "per_product_units": per_units,
        "per_product_sales": per_sales,
    }


# ---------------------------------------------------------------- Forms
def business_form(key, d=None, label="Save"):
    d = d or {}
    try:
        default_date = date.fromisoformat(d["date_created"]) if d.get("date_created") else date.today()
    except ValueError:
        default_date = date.today()
    with st.form(key, clear_on_submit=not d):
        name = st.text_input("Business name", value=d.get("name", ""))
        owner = st.text_input("Owner name", value=d.get("owner", ""))
        created = st.date_input("Date created", value=default_date)
        submitted = st.form_submit_button(label)
    return submitted, {"name": name.strip(), "owner": owner.strip(), "date_created": created.isoformat()}


def product_form(key, d=None, label="Save"):
    d = d or {}
    with st.form(key, clear_on_submit=not d):
        name = st.text_input("Product name", value=d.get("name", ""))
        c1, c2 = st.columns(2)
        price = c1.number_input("Selling price / unit (RM)", min_value=0.0, step=0.5, value=float(d.get("price", 0.0)))
        units = c2.number_input("Expected units sold / month", min_value=0, step=1, value=int(d.get("units", 0)))
        st.markdown("**Direct cost per unit**")
        c3, c4, c5 = st.columns(3)
        materials = c3.number_input("Direct materials (RM)", min_value=0.0, step=0.5, value=float(d.get("materials", 0.0)))
        labour = c4.number_input("Direct labour (RM)", min_value=0.0, step=0.5, value=float(d.get("labour", 0.0)))
        other = c5.number_input("Other direct (RM)", min_value=0.0, step=0.5, value=float(d.get("other_direct", 0.0)))
        submitted = st.form_submit_button(label)
    return submitted, {
        "name": name.strip(),
        "price": price,
        "units": int(units),
        "materials": materials,
        "labour": labour,
        "other_direct": other,
    }


def indirect_form(key, d=None, label="Save"):
    d = d or {}
    idx = CATEGORIES.index(d["category"]) if d.get("category") in CATEGORIES else 0
    with st.form(key, clear_on_submit=not d):
        category = st.selectbox("Category", CATEGORIES, index=idx)
        description = st.text_input("Description (optional)", value=d.get("description", ""))
        amount = st.number_input("Amount per month (RM)", min_value=0.0, step=10.0, value=float(d.get("amount", 0.0)))
        submitted = st.form_submit_button(label)
    return submitted, {"category": category, "description": description.strip(), "amount": amount}


# ---------------------------------------------------------------- Business selection (sidebar)
businesses = sorted(list_docs(db.collection(BUSINESSES)), key=lambda b: b.get("name", "").lower())
biz_by_id = {b["id"]: b for b in businesses}

# apply a pending selection (set after creating a business) before the widget is built
if "pending_biz" in st.session_state:
    st.session_state["active_biz"] = st.session_state.pop("pending_biz")
if st.session_state.get("active_biz") not in biz_by_id:
    st.session_state.pop("active_biz", None)

with st.sidebar:
    st.header("🏪 Active Business")
    if businesses:
        bid = st.selectbox(
            "Select business",
            list(biz_by_id.keys()),
            format_func=lambda i: biz_by_id[i]["name"],
            key="active_biz",
        )
    else:
        bid = None
        st.info("No business yet. Create one in the 'Businesses' tab.")
    if bid:
        b = biz_by_id[bid]
        st.markdown(f"**Owner:** {b.get('owner', '-')}")
        st.markdown(f"**Created:** {b.get('date_created', '-')}")

st.title("📊 Business Profit Manager")
if bid:
    st.caption(f"Working on: **{biz_by_id[bid]['name']}**  •  all figures per month (RM)")
else:
    st.caption("Create a business to get started")

tab_biz, tab_prod, tab_ind, tab_gp, tab_be = st.tabs(
    ["🏪 Businesses", "📦 Products (Direct Cost)", "🏢 Indirect Costs", "💰 Gross Profit & Margin", "🎯 Break Even"]
)

# ================================================================ BUSINESSES
with tab_biz:
    v, a, e, x = st.tabs(["View", "Add", "Edit", "Delete"])

    with v:
        if not businesses:
            st.info("No businesses yet. Add one in the 'Add' tab.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Business Name": b.get("name"),
                            "Owner Name": b.get("owner"),
                            "Date Created": b.get("date_created"),
                        }
                        for b in businesses
                    ]
                ),
                hide_index=True,
            )

    with a:
        ok, data = business_form("add_business", label="Create business")
        if ok:
            if not data["name"] or not data["owner"]:
                st.error("Business name and owner name are required.")
            else:
                new_id = add_doc(db.collection(BUSINESSES), data)
                st.session_state["pending_biz"] = new_id
                st.success(f"Created '{data['name']}'.")
                st.rerun()

    with e:
        if not businesses:
            st.info("Nothing to edit yet.")
        else:
            eid = st.selectbox("Select business", biz_by_id.keys(), format_func=lambda i: biz_by_id[i]["name"], key="edit_b")
            ok, data = business_form(f"edit_business_{eid}", biz_by_id[eid], "Save changes")
            if ok:
                if not data["name"] or not data["owner"]:
                    st.error("Business name and owner name are required.")
                else:
                    update_doc(db.collection(BUSINESSES), eid, data)
                    st.success("Updated.")
                    st.rerun()

    with x:
        if not businesses:
            st.info("Nothing to delete.")
        else:
            did = st.selectbox("Select business", biz_by_id.keys(), format_func=lambda i: biz_by_id[i]["name"], key="del_b")
            st.warning("Deleting a business also deletes all its products and indirect costs.")
            sure = st.checkbox("I understand this cannot be undone", key="del_b_ok")
            if st.button("Delete business", type="primary", disabled=not sure):
                delete_business(did)
                st.success("Deleted.")
                st.rerun()

# Everything below needs an active business
if not bid:
    for t in (tab_prod, tab_ind, tab_gp, tab_be):
        with t:
            st.info("Create and select a business first (Businesses tab).")
    st.stop()

prod_col = biz_sub(bid, PRODUCTS)
ind_col = biz_sub(bid, INDIRECT)
products = list_docs(prod_col)
indirects = list_docs(ind_col)
pdf = build_product_df(products)
total_indirect = sum(i.get("amount", 0) for i in indirects)

# ================================================================ PRODUCTS
with tab_prod:
    v, a, e, x = st.tabs(["View", "Add", "Edit", "Delete"])
    by_id = {p["id"]: p for p in products}

    with v:
        if pdf.empty:
            st.info("No products yet. Add one in the 'Add' tab.")
        else:
            st.dataframe(pdf[["Product", "Price", "Direct Cost/Unit", "Units/Month"]], hide_index=True)
            st.caption("Direct Cost/Unit = Direct Materials + Direct Labour + Other Direct")

    with a:
        ok, data = product_form(f"add_product_{bid}", label="Add product")
        if ok:
            if not data["name"]:
                st.error("Name is required.")
            else:
                add_doc(prod_col, data)
                st.success(f"Added '{data['name']}'.")
                st.rerun()

    with e:
        if not products:
            st.info("Nothing to edit yet.")
        else:
            pid = st.selectbox("Select product", by_id.keys(), format_func=lambda i: by_id[i]["name"], key=f"edit_p_{bid}")
            ok, data = product_form(f"edit_product_{bid}_{pid}", by_id[pid], "Save changes")
            if ok:
                if not data["name"]:
                    st.error("Name is required.")
                else:
                    update_doc(prod_col, pid, data)
                    st.success("Updated.")
                    st.rerun()

    with x:
        if not products:
            st.info("Nothing to delete.")
        else:
            pid = st.selectbox("Select product", by_id.keys(), format_func=lambda i: by_id[i]["name"], key=f"del_p_{bid}")
            sure = st.checkbox("I understand this cannot be undone", key=f"del_p_ok_{bid}")
            if st.button("Delete product", type="primary", disabled=not sure):
                delete_doc(prod_col, pid)
                st.success("Deleted.")
                st.rerun()

# ================================================================ INDIRECT
with tab_ind:
    v, a, e, x = st.tabs(["View", "Add", "Edit", "Delete"])
    ind_by_id = {i["id"]: i for i in indirects}

    def ind_label(i):
        r = ind_by_id[i]
        desc = f" – {r['description']}" if r.get("description") else ""
        return f"{r['category']}{desc} ({money(r['amount'])})"

    with v:
        if not indirects:
            st.info("No indirect costs yet. Add rent, utilities, salaries, etc.")
        else:
            idf = pd.DataFrame(indirects)
            if "description" not in idf:
                idf["description"] = ""
            summary = idf.groupby("category")["amount"].sum().reindex(CATEGORIES).fillna(0).reset_index()
            summary.columns = ["Category", "Amount / Month (RM)"]
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown("**Summary by category**")
                st.dataframe(summary, hide_index=True)
                st.markdown("**All entries**")
                st.dataframe(
                    idf[["category", "description", "amount"]].rename(
                        columns={"category": "Category", "description": "Description", "amount": "Amount (RM)"}
                    ),
                    hide_index=True,
                )
            with c2:
                st.metric("Total Indirect Costs / Month", money(total_indirect))
                st.caption("Rent + Utilities + Salaries + Marketing + Insurance + Depreciation + Other Overheads")
                if not pdf.empty and pdf["Units/Month"].sum() > 0:
                    units_total = pdf["Units/Month"].sum()
                    per_unit = total_indirect / units_total
                    st.metric("Indirect Cost per Unit (avg)", money(per_unit))
                    st.metric("Total Cost per Unit (avg)", money(pdf["Total Direct Cost"].sum() / units_total + per_unit))

    with a:
        ok, data = indirect_form(f"add_indirect_{bid}", label="Add cost")
        if ok:
            add_doc(ind_col, data)
            st.success("Added.")
            st.rerun()

    with e:
        if not indirects:
            st.info("Nothing to edit yet.")
        else:
            iid = st.selectbox("Select entry", ind_by_id.keys(), format_func=ind_label, key=f"edit_i_{bid}")
            ok, data = indirect_form(f"edit_indirect_{bid}_{iid}", ind_by_id[iid], "Save changes")
            if ok:
                update_doc(ind_col, iid, data)
                st.success("Updated.")
                st.rerun()

    with x:
        if not indirects:
            st.info("Nothing to delete.")
        else:
            iid = st.selectbox("Select entry", ind_by_id.keys(), format_func=ind_label, key=f"del_i_{bid}")
            sure = st.checkbox("I understand this cannot be undone", key=f"del_i_ok_{bid}")
            if st.button("Delete entry", type="primary", disabled=not sure):
                delete_doc(ind_col, iid)
                st.success("Deleted.")
                st.rerun()

# ================================================================ GROSS PROFIT
with tab_gp:
    if pdf.empty:
        st.info("Add products first.")
    else:
        revenue = pdf["Revenue"].sum()
        direct_total = pdf["Total Direct Cost"].sum()
        gross_profit = pdf["Gross Profit"].sum()
        gross_margin = (gross_profit / revenue * 100) if revenue else 0.0
        net_profit = gross_profit - total_indirect

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Revenue", money(revenue))
        m2.metric("Direct Costs (COGS)", money(direct_total))
        m3.metric("Gross Profit", money(gross_profit))
        m4.metric("Gross Margin", f"{gross_margin:.1f}%")
        m5.metric("Net Profit", money(net_profit))

        st.markdown("**Per product**")
        st.dataframe(
            pdf.drop(columns=["id"]).style.format(
                {
                    "Price": "{:,.2f}",
                    "Direct Cost/Unit": "{:,.2f}",
                    "Gross Profit/Unit": "{:,.2f}",
                    "Gross Margin %": "{:.1f}%",
                    "Revenue": "{:,.2f}",
                    "Total Direct Cost": "{:,.2f}",
                    "Gross Profit": "{:,.2f}",
                }
            ),
            hide_index=True,
        )
        st.caption(
            "Gross Profit = Revenue − Direct Costs  |  Gross Margin % = Gross Profit ÷ Revenue × 100  |  "
            "Net Profit = Gross Profit − Indirect Costs"
        )

# ================================================================ BREAK EVEN
with tab_be:
    if pdf.empty:
        st.info("Add products first.")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        scope = c1.selectbox("Calculate for", ["All products (sales mix)"] + list(pdf["Product"]), key=f"scope_{bid}")
        target = c2.number_input("Target profit / month (RM)", min_value=0.0, step=500.0, value=3000.0, key=f"target_{bid}")
        c3.metric("Fixed (Indirect) Costs", money(total_indirect))

        if scope == "All products (sales mix)":
            calc_df = pdf.copy()
        else:
            calc_df = pdf[pdf["Product"] == scope].reset_index(drop=True)
            st.caption("Single-product mode: this product carries all the indirect costs.")

        if calc_df["Units/Month"].sum() <= 0:
            calc_df["Units/Month"] = 1

        be = break_even(calc_df, total_indirect, 0.0)
        bt = break_even(calc_df, total_indirect, target)

        if be is None:
            st.warning(
                "Break-even can't be calculated: contribution margin is zero or negative "
                "(selling price must be higher than direct cost)."
            )
        else:
            st.markdown("### Break Even")
            k1, k2, k3 = st.columns(3)
            k1.metric("Break-Even Units", f"{be['units']:,}")
            k2.metric("Break-Even Sales", money(be["sales"]))
            k3.metric("Avg Contribution / Unit", money(be["wacm"]))

            st.markdown("### Break Even with Target Profit")
            t1, t2, t3 = st.columns(3)
            t1.metric("Units Needed", f"{bt['units']:,}")
            t2.metric("Sales Needed", money(bt["sales"]))
            t3.metric("Target Profit", money(target))

            table = pd.DataFrame(
                {
                    "Product": calc_df["Product"],
                    "Price": calc_df["Price"],
                    "Contribution/Unit": calc_df["Gross Profit/Unit"],
                    "Break-Even Units": be["per_product_units"],
                    "Break-Even Sales": be["per_product_sales"],
                    "Units for Target": bt["per_product_units"],
                    "Sales for Target": bt["per_product_sales"],
                }
            )
            st.markdown("**Breakdown by product**")
            st.dataframe(
                table.style.format(
                    {
                        "Price": "{:,.2f}",
                        "Contribution/Unit": "{:,.2f}",
                        "Break-Even Sales": "{:,.2f}",
                        "Sales for Target": "{:,.2f}",
                    }
                ),
                hide_index=True,
            )

            total_u = calc_df["Units/Month"].sum()
            avg_price = (calc_df["Price"] * calc_df["Units/Month"]).sum() / total_u
            avg_vc = (calc_df["Direct Cost/Unit"] * calc_df["Units/Month"]).sum() / total_u
            max_units = max(bt["units"], be["units"], 1) * 1.5
            step = max(1, int(max_units // 40))
            xs = list(range(0, int(max_units) + step, step))
            chart = pd.DataFrame(
                {
                    "Units": xs,
                    "Revenue": [u * avg_price for u in xs],
                    "Total Cost": [total_indirect + u * avg_vc for u in xs],
                }
            ).set_index("Units")
            st.markdown("**Revenue vs Total Cost** (lines cross at break-even)")
            st.line_chart(chart)

        with st.expander("Formulas used"):
            st.markdown(
                """
- **Contribution Margin/Unit** = Selling Price − Direct (Variable) Cost per Unit
- **Break-Even Units** = Fixed (Indirect) Costs ÷ Contribution Margin per Unit
- **Break-Even Sales** = Break-Even Units × Selling Price
- **Units for Target Profit** = (Fixed Costs + Target Profit) ÷ Contribution Margin per Unit
- For several products, the *weighted average* contribution margin is used, based on each
  product's expected units/month (your sales mix).
"""
            )
