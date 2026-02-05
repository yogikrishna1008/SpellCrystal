import streamlit as st
import pandas as pd
from datetime import date, datetime
import os
import re
import uuid
from PIL import Image

# ============================================================
# Jyogi Manager — v10 (Rewrite)
# Local Excel + Images folder
# ============================================================

# ---------- PATHS ----------
FOLDER_PATH = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(FOLDER_PATH, "crystal_data.xlsx")
IMAGE_FOLDER = os.path.join(FOLDER_PATH, "images")

os.makedirs(IMAGE_FOLDER, exist_ok=True)  # Folder Safety ✅

st.set_page_config(
    page_title="Jyogi Manager",
    page_icon="🔮",
    layout="wide"
)

# ============================================================
# ✅ CRITICAL FIX: AGGRESSIVE SANITIZER (DO NOT REMOVE)
# Prevents: SyntaxError: Invalid regular expression (Streamlit crash)
# ============================================================
def safe_text(text):
    if pd.isna(text):
        return ""
    text = str(text)
    # Allows letters, numbers, spaces, and basic punctuation.
    # Intentionally strips: $, \, (, ), etc to prevent frontend regex issues.
    return re.sub(r"[^a-zA-Z0-9 \.\,\!\-\@\:\/]", "", text)

def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.astype(str)  # Strict Type Casting ✅
    for col in df.columns:
        df[col] = df[col].apply(safe_text)
    return df

# Extra: safe filename that WILL survive safe_text cleaning
# (avoid underscores etc). This prevents "image not found" after reload.
def safe_filename(text: str) -> str:
    if pd.isna(text):
        return ""
    text = str(text).strip()
    text = re.sub(r"[^a-zA-Z0-9\.\- ]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text[:80]

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def today_str():
    return str(date.today())

# ============================================================
# SETTINGS: Public mode + Admin passcode
# ============================================================
# For sharing: put on Streamlit Cloud and set secrets:
# .streamlit/secrets.toml
# ADMIN_PASSCODE="yourpass"
# PUBLIC_MODE="true"   (or "false")

def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def str_to_bool(v: str, default=False):
    if v is None:
        return default
    v = str(v).strip().lower()
    return v in ["1", "true", "yes", "y", "on"]

PUBLIC_MODE = str_to_bool(get_secret("PUBLIC_MODE", "false"), default=False)
ADMIN_PASSCODE = str(get_secret("ADMIN_PASSCODE", "")).strip()

# session admin auth
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ============================================================
# DATA SCHEMA (Excel Sheets)
# ============================================================
SCHEMA = {
    "Orders": ["ID", "Date", "Customer", "Item", "Amount", "Status", "Notes"],
    "Healings": ["ID", "Date", "Client Name", "Request Type", "Intention", "Status", "Notes"],
    "Designs": ["ID", "Created On", "Design Name", "Category", "Components", "My Cost", "Selling Price", "Public", "Image Path", "Notes"],
    "Suppliers": ["ID", "Supplier Name", "Material", "Price Per Unit", "MOQ", "Contact Info", "Notes"],
    "Reviews": ["ID", "Date", "Design ID", "Reviewer Name", "Rating", "Review", "Status", "Admin Reply"],
    "Readings": ["ID", "Date", "Client Name", "Reading Type", "Question", "Notes", "Status"],
}

def ensure_workbook():
    if os.path.exists(FILE_PATH):
        return
    try:
        with pd.ExcelWriter(FILE_PATH, engine="openpyxl") as writer:
            for sheet, cols in SCHEMA.items():
                pd.DataFrame(columns=cols).to_excel(writer, sheet_name=sheet, index=False)
    except Exception:
        pass

def ensure_columns(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]

def ensure_ids(df: pd.DataFrame) -> pd.DataFrame:
    # stable row identity
    if df.empty:
        return df
    df["ID"] = df["ID"].astype(str)
    mask = df["ID"].isin(["", "nan", "None"])
    if mask.any():
        df.loc[mask, "ID"] = [str(uuid.uuid4()) for _ in range(mask.sum())]
    return df

def load_all_data():
    ensure_workbook()
    data = {}
    try:
        xl = pd.ExcelFile(FILE_PATH)
        for sheet, cols in SCHEMA.items():
            if sheet in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name=sheet)
                df = ensure_columns(df, cols)
                df = clean_df(df)
                df = ensure_ids(df)
                data[sheet] = df
            else:
                data[sheet] = pd.DataFrame(columns=cols)
        return data
    except Exception:
        # fallback empty dfs
        return {k: pd.DataFrame(columns=v) for k, v in SCHEMA.items()}

def save_all_data(data: dict):
    try:
        with pd.ExcelWriter(FILE_PATH, engine="openpyxl") as writer:
            for sheet, cols in SCHEMA.items():
                df = data.get(sheet, pd.DataFrame(columns=cols))
                df = ensure_columns(df, cols)
                df = clean_df(df)
                df.to_excel(writer, sheet_name=sheet, index=False)
        st.toast("✅ Saved successfully!")
    except PermissionError:
        st.error("⚠️ CLOSE THE EXCEL FILE! I cannot save while it is open.")
    except Exception as e:
        st.error(f"Save failed: {e}")

# ============================================================
# UI SAFETY: force all columns as text (prevents parsing crashes)
# ============================================================
def text_columns_config(df: pd.DataFrame, disabled=None):
    disabled = disabled or []
    config = {c: st.column_config.TextColumn(c) for c in df.columns}
    return config, disabled

def parse_money(s: str) -> float:
    try:
        s = safe_text(s)
        s = s.replace(",", "").strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0

def make_share_link(design_id: str) -> str:
    # Uses query params; works when hosted (Streamlit Cloud etc).
    # In local, it still shows the params.
    # Example: ?page=showcase&design=<id>
    return f"?page=showcase&design={design_id}"

# ============================================================
# LOAD DATA
# ============================================================
data = load_all_data()

df_orders = data["Orders"]
df_healings = data["Healings"]
df_designs = data["Designs"]
df_suppliers = data["Suppliers"]
df_reviews = data["Reviews"]
df_readings = data["Readings"]

# ============================================================
# AUTH / MODE GATING
# ============================================================
def admin_gate_sidebar():
    with st.sidebar:
        st.caption("🔐 Admin Access")
        if st.session_state.is_admin:
            st.success("Admin mode ON")
            if st.button("Log out"):
                st.session_state.is_admin = False
                st.rerun()
        else:
            if ADMIN_PASSCODE:
                code = st.text_input("Passcode", type="password")
                if st.button("Unlock Admin"):
                    if code.strip() == ADMIN_PASSCODE:
                        st.session_state.is_admin = True
                        st.rerun()
                    else:
                        st.error("Wrong passcode.")
            else:
                st.info("No ADMIN_PASSCODE set in secrets. Admin unlock disabled.")

def top_brand():
    st.markdown(
        """
        <div style="padding: 14px 18px; border-radius: 14px; background: rgba(120, 70, 200, 0.08);">
          <div style="font-size: 20px; font-weight: 700;">🔮 Jyogi Manager</div>
          <div style="opacity: 0.8;">Crystal business + design showcase + reviews</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================
# NAVIGATION
# ============================================================
# query params support
params = dict(st.query_params)
param_page = (params.get("page", [""])[0] if isinstance(params.get("page"), list) else params.get("page", ""))
param_design = (params.get("design", [""])[0] if isinstance(params.get("design"), list) else params.get("design", ""))

with st.sidebar:
    top_brand()
    st.divider()

    if PUBLIC_MODE and not st.session_state.is_admin:
        page = "✨ Design Showcase"
        st.caption("Public Mode is ON")
    else:
        page = st.radio(
            "Go to",
            [
                "🏠 Dashboard",
                "📦 Orders",
                "🙏 Healings & Spells",
                "🎨 Design Library (Admin)",
                "✨ Design Showcase (Public)",
                "🏭 Suppliers & Costs",
                "🔮 Tarot & Astrology (Starter)",
                "🧰 Review Moderation (Admin)",
            ],
        )
    st.divider()
    st.caption("v10 - rewrite + public showcase")

admin_gate_sidebar()

# If query param asks for showcase, override page
if param_page.strip().lower() == "showcase":
    page = "✨ Design Showcase (Public)"

# ============================================================
# PAGE: DASHBOARD
# ============================================================
if page == "🏠 Dashboard":
    st.header("👋 Namaste, Jyogi!")
    c1, c2, c3, c4 = st.columns(4)

    total_orders = len(df_orders)
    total_spells = len(df_healings)
    total_designs = len(df_designs)

    paid_total = 0.0
    if not df_orders.empty:
        paid_total = sum(parse_money(x) for x in df_orders.loc[df_orders["Status"] == "Paid", "Amount"].astype(str).tolist())

    c1.metric("Total Orders", total_orders)
    c2.metric("Total Spells", total_spells)
    c3.metric("Designs Created", total_designs)
    c4.metric("Paid Total (best-effort)", f"{paid_total:.2f}")

    st.divider()
    st.subheader("✨ Quick vibes")
    left, right = st.columns([1, 1])
    with left:
        st.info("Tip: Mark designs as **Public = Yes** to show them on the Showcase page.")
    with right:
        st.success("Share a design link: open a design in Showcase → copy the share link shown there.")

# ============================================================
# PAGE: ORDERS
# ============================================================
elif page == "📦 Orders":
    st.header("📦 Order Management")

    with st.expander("➕ Add New Order", expanded=False):
        with st.form("order_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            d_date = c1.date_input("Date", date.today())
            d_name = c2.text_input("Customer Name")
            d_item = st.text_input("Item")
            d_amt = st.text_input("Amount (No $)")
            d_stat = st.selectbox("Status", ["Paid", "Processing", "Shipped"])
            d_note = st.text_input("Notes")

            if st.form_submit_button("Save"):
                new = pd.DataFrame([{
                    "ID": str(uuid.uuid4()),
                    "Date": str(d_date),
                    "Customer": safe_text(d_name),
                    "Item": safe_text(d_item),
                    "Amount": safe_text(d_amt),
                    "Status": safe_text(d_stat),
                    "Notes": safe_text(d_note),
                }])
                df_orders = pd.concat([df_orders, new], ignore_index=True)
                data["Orders"] = df_orders
                save_all_data(data)
                st.rerun()

    st.divider()
    if df_orders.empty:
        st.info("No orders yet.")
    else:
        cfg, disabled = text_columns_config(df_orders, disabled=["ID"])
        edited = st.data_editor(
            df_orders,
            num_rows="dynamic",
            use_container_width=True,
            key="ord_ed",
            column_config=cfg,  # Column Configuration ✅
            disabled=disabled
        )
        if st.button("💾 Save Changes"):
            df_orders = edited
            data["Orders"] = df_orders
            save_all_data(data)
            st.rerun()

# ============================================================
# PAGE: HEALINGS
# ============================================================
elif page == "🙏 Healings & Spells":
    st.header("🙏 Healing Requests")

    with st.expander("➕ Add New Request", expanded=False):
        with st.form("heal_form", clear_on_submit=True):
            h_date = st.date_input("Date", date.today())
            h_name = st.text_input("Client Name")
            h_type = st.selectbox("Type", ["Love Spell", "Protection", "Money Ritual", "Other"])
            h_stat = st.selectbox("Status", ["New", "In Progress", "Completed"])
            h_int = st.text_area("Intention")

            if st.form_submit_button("Start Ritual"):
                new = pd.DataFrame([{
                    "ID": str(uuid.uuid4()),
                    "Date": str(h_date),
                    "Client Name": safe_text(h_name),
                    "Request Type": safe_text(h_type),
                    "Intention": safe_text(h_int),
                    "Status": safe_text(h_stat),
                    "Notes": "",
                }])
                df_healings = pd.concat([df_healings, new], ignore_index=True)
                data["Healings"] = df_healings
                save_all_data(data)
                st.rerun()

    st.divider()
    if df_healings.empty:
        st.info("No healing requests yet.")
    else:
        cfg, disabled = text_columns_config(df_healings, disabled=["ID"])
        edited = st.data_editor(
            df_healings,
            num_rows="dynamic",
            use_container_width=True,
            key="heal_ed",
            column_config=cfg,
            disabled=disabled
        )
        if st.button("💾 Save Healings"):
            df_healings = edited
            data["Healings"] = df_healings
            save_all_data(data)
            st.rerun()

# ============================================================
# PAGE: DESIGN LIBRARY (ADMIN)
# ============================================================
elif page == "🎨 Design Library (Admin)":
    if not st.session_state.is_admin:
        st.warning("Admin mode required for Design Library editing.")
    else:
        st.header("🎨 Design Library (Admin)")

        with st.expander("➕ Create New Design", expanded=False):
            with st.form("design_form", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                d_name = c1.text_input("Design Name")
                d_cat = c2.text_input("Category (e.g. Bracelet, Ring, Set)")
                d_public = c3.selectbox("Public?", ["No", "Yes"])

                c4, c5 = st.columns(2)
                d_cost = c4.text_input("My Cost")
                d_sell = c5.text_input("Selling Price")

                d_comp = st.text_area("Components Used")
                uploaded_file = st.file_uploader("Upload Photo", type=["png", "jpg", "jpeg"])

                if st.form_submit_button("Save Design"):
                    image_filename = "None"
                    if uploaded_file is not None:
                        try:
                            base = safe_filename(d_name)
                            orig = safe_filename(os.path.splitext(uploaded_file.name)[0])
                            ext = os.path.splitext(uploaded_file.name)[1].lower()
                            if ext not in [".png", ".jpg", ".jpeg"]:
                                ext = ".jpg"
                            image_filename = f"{base}-{orig}{ext}".strip("-")
                            save_path = os.path.join(IMAGE_FOLDER, image_filename)

                            i = 1
                            while os.path.exists(save_path):
                                image_filename = f"{base}-{orig}-{i}{ext}"
                                save_path = os.path.join(IMAGE_FOLDER, image_filename)
                                i += 1

                            with open(save_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                        except Exception as e:
                            st.error(f"Image failed to save: {e}")
                            image_filename = "None"

                    new = pd.DataFrame([{
                        "ID": str(uuid.uuid4()),
                        "Created On": now_str(),
                        "Design Name": safe_text(d_name),
                        "Category": safe_text(d_cat),
                        "Components": safe_text(d_comp),
                        "My Cost": safe_text(d_cost),
                        "Selling Price": safe_text(d_sell),
                        "Public": safe_text(d_public),
                        "Image Path": safe_text(image_filename),
                        "Notes": "",
                    }])
                    df_designs = pd.concat([df_designs, new], ignore_index=True)
                    data["Designs"] = df_designs
                    save_all_data(data)
                    st.rerun()

        st.divider()

        if df_designs.empty:
            st.info("No designs yet.")
        else:
            left, right = st.columns([1, 1])

            with left:
                st.subheader("📚 Designs (Admin Table)")
                cfg, disabled = text_columns_config(df_designs, disabled=["ID", "Image Path", "Created On"])
                edited = st.data_editor(
                    df_designs,
                    use_container_width=True,
                    num_rows="dynamic",
                    key="design_admin_editor",
                    column_config=cfg,
                    disabled=disabled
                )

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("💾 Save Design Table"):
                        df_designs = edited
                        data["Designs"] = df_designs
                        save_all_data(data)
                        st.rerun()

                with c2:
                    if st.button("🧹 Remove Empty Rows"):
                        tmp = edited.copy()
                        # remove rows where all non-ID fields are empty
                        cols = [c for c in tmp.columns if c != "ID"]
                        mask = tmp[cols].apply(lambda r: all(str(x).strip() == "" for x in r), axis=1)
                        tmp = tmp.loc[~mask].reset_index(drop=True)
                        df_designs = tmp
                        data["Designs"] = df_designs
                        save_all_data(data)
                        st.rerun()

            with right:
                st.subheader("🖼️ Preview & Share")
                options = df_designs[["ID", "Design Name"]].drop_duplicates()
                selected_id = st.selectbox(
                    "Select design",
                    options["ID"].tolist(),
                    format_func=lambda x: options.loc[options["ID"] == x, "Design Name"].iloc[0],
                    key="design_admin_select",
                )
                row = df_designs[df_designs["ID"] == selected_id].iloc[0]

                st.markdown(f"**Name:** {row['Design Name']}")
                st.markdown(f"**Category:** {row['Category']}")
                st.markdown(f"**Price:** {row['Selling Price']}")
                st.markdown(f"**Public:** {row['Public']}")
                st.markdown(f"**Components:** {row['Components']}")

                img_path = row["Image Path"]
                if img_path and img_path != "None":
                    full_path = os.path.join(IMAGE_FOLDER, img_path)
                    if os.path.exists(full_path):
                        st.image(full_path, caption=row["Design Name"], use_container_width=True)
                    else:
                        st.warning("Image file not found.")
                else:
                    st.info("No image uploaded for this design.")

                st.divider()
                st.caption("Share this design (Showcase link):")
                st.code(make_share_link(selected_id), language="text")

                # Delete (optional)
                st.divider()
                if st.button("🗑️ Delete this design"):
                    # remove design
                    df_designs = df_designs[df_designs["ID"] != selected_id].reset_index(drop=True)
                    data["Designs"] = df_designs

                    # remove reviews for it (optional)
                    df_reviews_local = data["Reviews"]
                    df_reviews_local = df_reviews_local[df_reviews_local["Design ID"] != selected_id].reset_index(drop=True)
                    data["Reviews"] = df_reviews_local

                    save_all_data(data)
                    st.rerun()

# ============================================================
# PAGE: DESIGN SHOWCASE (PUBLIC)
# ============================================================
elif page == "✨ Design Showcase (Public)":
    st.header("✨ Design Showcase")
    st.caption("Browse designs, view photos, and leave reviews. (Public-friendly)")

    # Only show public designs (unless admin)
    show_df = df_designs.copy()
    if not st.session_state.is_admin:
        show_df = show_df[show_df["Public"].str.lower() == "yes"].reset_index(drop=True)

    if show_df.empty:
        st.info("No public designs yet. (Admin: set Public = Yes in Design Library)")
    else:
        # filters
        c1, c2, c3 = st.columns([1, 1, 1])
        q = c1.text_input("Search name/components", value="")
        cats = ["All"] + sorted([x for x in show_df["Category"].astype(str).unique().tolist() if x.strip()])
        cat = c2.selectbox("Category", cats)
        sort = c3.selectbox("Sort", ["Newest", "Name A→Z", "Price Low→High", "Price High→Low"])

        filtered = show_df.copy()
        if q.strip():
            qq = safe_text(q).lower()
            filtered = filtered[
                filtered["Design Name"].str.lower().str.contains(qq, na=False)
                | filtered["Components"].str.lower().str.contains(qq, na=False)
            ]

        if cat != "All":
            filtered = filtered[filtered["Category"] == cat]

        # sorting
        if sort == "Newest":
            # Created On is string; best-effort sort
            filtered = filtered.sort_values(by="Created On", ascending=False)
        elif sort == "Name A→Z":
            filtered = filtered.sort_values(by="Design Name", ascending=True)
        elif sort == "Price Low→High":
            filtered = filtered.assign(_p=filtered["Selling Price"].apply(parse_money)).sort_values("_p", ascending=True).drop(columns=["_p"])
        elif sort == "Price High→Low":
            filtered = filtered.assign(_p=filtered["Selling Price"].apply(parse_money)).sort_values("_p", ascending=False).drop(columns=["_p"])

        filtered = filtered.reset_index(drop=True)

        # if query param design id exists, preselect that
        design_ids = filtered["ID"].tolist()
        preselect_id = safe_text(param_design) if param_design else ""
        if preselect_id and preselect_id in design_ids:
            default_index = design_ids.index(preselect_id)
        else:
            default_index = 0

        selected_id = st.selectbox(
            "Pick a design",
            design_ids,
            index=default_index,
            format_func=lambda x: filtered.loc[filtered["ID"] == x, "Design Name"].iloc[0],
            key="showcase_pick",
        )

        row = filtered[filtered["ID"] == selected_id].iloc[0]

        # layout
        left, right = st.columns([1, 1])
        with left:
            st.subheader(row["Design Name"])
            st.markdown(f"**Category:** {row['Category']}")
            st.markdown(f"**Price:** {row['Selling Price']}")
            st.markdown("**Components:**")
            st.write(row["Components"] if row["Components"].strip() else "—")

            st.divider()
            st.caption("Share link:")
            st.code(make_share_link(selected_id), language="text")

        with right:
            img_path = row["Image Path"]
            if img_path and img_path != "None":
                full_path = os.path.join(IMAGE_FOLDER, img_path)
                if os.path.exists(full_path):
                    st.image(full_path, use_container_width=True)
                else:
                    st.warning("Image file not found.")
            else:
                st.info("No image for this design.")

        st.divider()
        st.subheader("⭐ Reviews")

        # show approved reviews
        design_reviews = df_reviews[df_reviews["Design ID"] == selected_id].copy()
        approved = design_reviews[design_reviews["Status"].str.lower() == "approved"]

        if approved.empty:
            st.info("No approved reviews yet. Be the first ✨")
        else:
            for _, r in approved.sort_values(by="Date", ascending=False).iterrows():
                st.markdown(f"**{r['Reviewer Name']}** — {r['Rating']} / 5")
                st.write(r["Review"])
                if str(r.get("Admin Reply", "")).strip():
                    st.markdown(f"> **Jyogi Reply:** {r['Admin Reply']}")
                st.divider()

        # review form
        st.markdown("### Leave a review")
        with st.form("review_form", clear_on_submit=True):
            name = st.text_input("Your name")
            rating = st.selectbox("Rating", ["5", "4", "3", "2", "1"], index=0)
            review = st.text_area("Your review")
            submit = st.form_submit_button("Submit Review")

            if submit:
                new = pd.DataFrame([{
                    "ID": str(uuid.uuid4()),
                    "Date": now_str(),
                    "Design ID": safe_text(selected_id),
                    "Reviewer Name": safe_text(name) if name.strip() else "Anonymous",
                    "Rating": safe_text(rating),
                    "Review": safe_text(review),
                    "Status": "Pending" if not st.session_state.is_admin else "Approved",
                    "Admin Reply": "",
                }])
                df_reviews = pd.concat([df_reviews, new], ignore_index=True)
                data["Reviews"] = df_reviews
                save_all_data(data)
                st.success("✨ Review submitted!")
                st.rerun()

# ============================================================
# PAGE: SUPPLIERS
# ============================================================
elif page == "🏭 Suppliers & Costs":
    st.header("🏭 Supplier & Costs")

    with st.expander("➕ Add New Material / Supplier", expanded=False):
        with st.form("sup_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            s_name = c1.text_input("Supplier Name")
            s_mat = c2.text_input("Material Name")
            s_price = c1.text_input("Price Per Unit")
            s_moq = c2.text_input("MOQ")
            s_cont = st.text_input("Contact Info")
            s_notes = st.text_input("Notes")

            if st.form_submit_button("Save Supplier"):
                new = pd.DataFrame([{
                    "ID": str(uuid.uuid4()),
                    "Supplier Name": safe_text(s_name),
                    "Material": safe_text(s_mat),
                    "Price Per Unit": safe_text(s_price),
                    "MOQ": safe_text(s_moq),
                    "Contact Info": safe_text(s_cont),
                    "Notes": safe_text(s_notes),
                }])
                df_suppliers = pd.concat([df_suppliers, new], ignore_index=True)
                data["Suppliers"] = df_suppliers
                save_all_data(data)
                st.rerun()

    st.divider()
    st.subheader("🔎 Filter")

    if df_suppliers.empty:
        st.info("No suppliers yet.")
    else:
        all_suppliers = ["Show All"] + sorted(list(df_suppliers["Supplier Name"].unique()))
        selected_sup = st.selectbox("Supplier", all_suppliers)

        if selected_sup == "Show All":
            display_df = df_suppliers
        else:
            display_df = df_suppliers[df_suppliers["Supplier Name"] == selected_sup].copy()

        st.info(f"Showing {len(display_df)} items for: **{selected_sup}**")

        cfg, disabled = text_columns_config(display_df, disabled=["ID"])
        edited = st.data_editor(
            display_df,
            num_rows="dynamic" if selected_sup == "Show All" else "fixed",
            use_container_width=True,
            key="sup_editor",
            column_config=cfg,
            disabled=disabled
        )

        if st.button("💾 Save Supplier Changes"):
            # If filtered: merge by ID into full df
            if selected_sup != "Show All":
                base = df_suppliers.set_index("ID")
                patch = edited.set_index("ID")
                base.update(patch)
                df_suppliers = base.reset_index()
            else:
                df_suppliers = edited

            data["Suppliers"] = df_suppliers
            save_all_data(data)
            st.rerun()

# ============================================================
# PAGE: TAROT & ASTROLOGY (STARTER MODULE)
# ============================================================
elif page == "🔮 Tarot & Astrology (Starter)":
    st.header("🔮 Tarot & Astrology — Starter")
    st.caption("This is a clean storage-ready module you can merge with your Tarot/Astro app.")

    with st.expander("➕ Add Reading", expanded=False):
        with st.form("reading_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            r_date = c1.date_input("Date", date.today())
            client = c2.text_input("Client Name")
            r_type = st.selectbox("Reading Type", ["Tarot", "Astrology", "Tarot + Astrology", "Other"])
            question = st.text_input("Question / Focus")
            notes = st.text_area("Notes / Cards / Observations")
            status = st.selectbox("Status", ["New", "In Progress", "Completed"])

            if st.form_submit_button("Save Reading"):
                new = pd.DataFrame([{
                    "ID": str(uuid.uuid4()),
                    "Date": str(r_date),
                    "Client Name": safe_text(client),
                    "Reading Type": safe_text(r_type),
                    "Question": safe_text(question),
                    "Notes": safe_text(notes),
                    "Status": safe_text(status),
                }])
                df_readings = pd.concat([df_readings, new], ignore_index=True)
                data["Readings"] = df_readings
                save_all_data(data)
                st.rerun()

    st.divider()
    if df_readings.empty:
        st.info("No readings yet.")
    else:
        cfg, disabled = text_columns_config(df_readings, disabled=["ID"])
        edited = st.data_editor(
            df_readings,
            num_rows="dynamic",
            use_container_width=True,
            key="readings_editor",
            column_config=cfg,
            disabled=disabled
        )
        if st.button("💾 Save Readings"):
            df_readings = edited
            data["Readings"] = df_readings
            save_all_data(data)
            st.rerun()

# ============================================================
# PAGE: REVIEW MODERATION (ADMIN)
# ============================================================
elif page == "🧰 Review Moderation (Admin)":
    if not st.session_state.is_admin:
        st.warning("Admin mode required for review moderation.")
    else:
        st.header("🧰 Review Moderation")

        if df_reviews.empty:
            st.info("No reviews yet.")
        else:
            pending = df_reviews[df_reviews["Status"].str.lower() == "pending"].copy()
            st.subheader(f"Pending Reviews: {len(pending)}")

            cfg, disabled = text_columns_config(df_reviews, disabled=["ID"])
            edited = st.data_editor(
                df_reviews,
                num_rows="dynamic",
                use_container_width=True,
                key="reviews_editor",
                column_config=cfg,
                disabled=disabled
            )

            st.caption("Set Status to Approved / Rejected. Add Admin Reply if you want.")
            if st.button("💾 Save Review Updates"):
                df_reviews = edited
                data["Reviews"] = df_reviews
                save_all_data(data)
                st.rerun()

