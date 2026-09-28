"""
dvi_admin_app.py
=====================================================================
RECONCILE — UNIFIED PORTAL (Admin + Investigator)

This file serves as the single entry point for both roles.
A shared login page authenticates either an Admin or an Investigator
using their respective credentials. After login the correct portal
experience is rendered based on st.session_state.role:

  Admin   → Dashboard / Investigation / History (all investigators)
  Investigator → Investigation / History (own cases only)

Shared styling / auth / Supabase / matching / report code lives in
dvi_common.py and is imported here (not duplicated).
=====================================================================
"""

import pandas as pd
import streamlit as st

import dvi_common as dvi

# =====================================================================
# PAGE SETUP
# =====================================================================

dvi.configure_page("RECONCILE")
dvi.inject_theme()
dvi.init_session_state()

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "DVI-Admin@2026!"
DEFAULT_INVESTIGATOR_USERNAME = "user"
DEFAULT_INVESTIGATOR_PASSWORD = "DVI@123"

ADMIN_USERNAME = str(dvi.secret_value("auth", "admin_username", DEFAULT_ADMIN_USERNAME))
ADMIN_PASSWORD = str(dvi.secret_value("auth", "admin_password", DEFAULT_ADMIN_PASSWORD))
INVESTIGATOR_USERNAME = str(dvi.secret_value("auth", "user_username", DEFAULT_INVESTIGATOR_USERNAME))
INVESTIGATOR_PASSWORD = str(dvi.secret_value("auth", "user_password", DEFAULT_INVESTIGATOR_PASSWORD))

dvi.require_unified_login(
    admin_username=ADMIN_USERNAME,
    admin_password=ADMIN_PASSWORD,
    investigator_username=INVESTIGATOR_USERNAME,
    investigator_password=INVESTIGATOR_PASSWORD,
    admin_landing_page="Dashboard",
    investigator_landing_page="Investigation",
)

# =====================================================================
# HEADER + NAVIGATION  — pages vary by role
# =====================================================================

is_admin = st.session_state.role == "admin"

if is_admin:
    console_subtitle = "RECONCILE &nbsp;•&nbsp; Administrator Console"
    pages = ["DASHBOARD", "HISTORY"]
    page_names = {"DASHBOARD": "Dashboard", "HISTORY": "History"}
    default_page = "Dashboard"
else:
    console_subtitle = "RECONCILE &nbsp;•&nbsp; Investigator Console"
    pages = ["INVESTIGATION", "UPLOAD DATA", "HISTORY"]
    page_names = {"INVESTIGATION": "Investigation", "UPLOAD DATA": "Upload Data", "HISTORY": "History"}
    default_page = "Investigation"

dvi.render_header(console_subtitle)

if st.session_state.page not in page_names.values():
    st.session_state.page = default_page
current_option = next((o for o in pages if page_names[o] == st.session_state.page), pages[0])
selected_option = st.segmented_control(
    "Navigation", pages, default=current_option, key="top_navigation", label_visibility="collapsed"
)

logout_col, role_col = st.columns([1, 5])
with logout_col:
    if st.button("LOG OUT"):
        dvi.logout_and_reset(landing_page=default_page)
        st.rerun()
with role_col:
    st.caption(f"Signed in as: {st.session_state.username} | Role: {st.session_state.role.upper()}")

if selected_option:
    selected_page = page_names[selected_option]
    if selected_page != st.session_state.page:
        st.session_state.page = selected_page
        st.rerun()

st.markdown(f'<p class="dvi-caption">{st.session_state.page}</p>', unsafe_allow_html=True)

df = dvi.load_database()

# =====================================================================
# AUTO-DEDUP — runs once per session on first load.
# If Supabase contains duplicate Body_IDs (e.g. from double inserts),
# the deduplicated df is written back immediately and silently.
# =====================================================================
if df is not None and not df.empty and "db_dedup_done" not in st.session_state:
    _bid_col = dvi.find_column(df, ["Body_ID"])
    if _bid_col:
        _dupes = df[_bid_col].astype(str).str.strip()
        _dupes = _dupes[_dupes.duplicated()].unique().tolist()
        if _dupes:
            dvi.save_database_df(df)   # df is already deduped by load_database()
            dvi.log_activity("DB_AUTO_DEDUP", None, {"removed_dupes": _dupes})
            st.cache_data.clear()
            df = dvi.load_database()   # reload clean version
    st.session_state["db_dedup_done"] = True

# =====================================================================
# DASHBOARD  — admin only
# =====================================================================

if st.session_state.page == "Dashboard" and is_admin:

    st.header("RECONCILE Dashboard")
    st.info(
        "RECONCILE decision-support console. Review potential record matches "
        "and require qualified forensic confirmation before identification."
    )

    total_records = len(df) if df is not None else 0
    if df is not None and "Sex" in df.columns:
        male_count = df["Sex"].astype(str).str.lower().eq("male").sum()
        female_count = df["Sex"].astype(str).str.lower().eq("female").sum()
    else:
        male_count = female_count = 0
    dna_count = int(df["DNA_Profile"].notna().sum()) if df is not None and "DNA_Profile" in df.columns else 0

    st.subheader("Database Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Body Records", total_records)
    col2.metric("Male Records", male_count)
    col3.metric("Female Records", female_count)
    col4.metric("DNA Profiles", dna_count)

    st.divider()
    st.subheader("RECONCILE System Status")
    status1, status2, status3, status4 = st.columns(4)
    status1.metric("Matching Engine", "ACTIVE")
    status2.metric("DNA Matching", "ENABLED")
    status3.metric("Candidate Results", "TOP 3")
    status4.metric("Storage", "LOCAL CSV")

    st.divider()

    # ---- CSV upload ----
    st.subheader("Upload Master Body Database")
    uploaded_file = st.file_uploader("Choose CSV file", type=["csv"], key="database_upload")
    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            preview = pd.read_csv(uploaded_file)
            preview.columns = [str(c).strip() for c in preview.columns]
            st.dataframe(preview.head(20), use_container_width=True, hide_index=True)
            if st.button("UPLOAD CSV TO SERVER", type="primary", use_container_width=True):
                ok, result = dvi.save_database(uploaded_file)
                if ok:
                    dvi.log_activity("CSV_UPLOAD", None, {"records": len(result)})
                    st.success(f"Database uploaded: {len(result)} records.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(result)
        except Exception as e:
            st.error(f"CSV error: {e}")

    st.divider()

    # ================================================================
    # DATABASE EDITOR  — admin can edit, delete, and add records
    # ================================================================
    st.subheader("Database Editor")

    if df is None:
        st.warning("No database loaded. Upload a CSV above to get started.")
    else:
        edit_tab, delete_tab, add_tab = st.tabs(["✏️ Edit Records", "🗑️ Delete Records", "➕ Add Record"])

        # --------------------------------------------------------
        # EDIT TAB — inline editable table via st.data_editor
        # --------------------------------------------------------
        with edit_tab:
            st.write("Edit any cell directly. `Body_ID` is locked (primary key). Click **Save Changes** when done.")
            # Build per-column config: lock Body_ID so it cannot be edited
            col_config = {}
            body_id_col_name = dvi.find_column(df, ["Body_ID"])
            if body_id_col_name:
                col_config[body_id_col_name] = st.column_config.TextColumn(
                    "Body_ID",
                    disabled=True,
                    help="Primary key — cannot be edited.",
                )
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config=col_config,
                key="admin_db_editor",
            )
            # Warn if duplicates are still present in loaded data
            body_id_col_chk = dvi.find_column(df, ["Body_ID"])
            if body_id_col_chk:
                dup_ids = df[body_id_col_chk].astype(str).str.strip()
                dup_ids = dup_ids[dup_ids.duplicated()].unique().tolist()
                if dup_ids:
                    st.warning(f"⚠️ Duplicate Body_ID(s) detected in database: **{', '.join(dup_ids)}**. Click **Fix Duplicates** to remove them.")
                    if st.button("FIX DUPLICATES", type="primary", use_container_width=True, key="fix_dupes"):
                        ok, result = dvi.save_database_df(df)  # load_database already deduped df
                        if ok:
                            dvi.log_activity("DB_FIX_DUPES", None, {"records": result})
                            st.success(f"✓ Duplicates removed. {result} unique records saved.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(result)

            if st.button("SAVE CHANGES", type="primary", use_container_width=True, key="save_edits"):
                ok, result = dvi.save_database_df(edited_df)
                if ok:
                    dvi.log_activity("DB_EDIT", None, {"records": result})
                    st.success(f"✓ Database saved — {result} records.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(result)

        # --------------------------------------------------------
        # DELETE TAB — two sub-sections: rows and columns
        # --------------------------------------------------------
        with delete_tab:
            del_row_sec, del_col_sec = st.tabs(["Delete Records (Rows)", "Delete Columns"])

            # ---- Delete rows by Body ID ----
            with del_row_sec:
                body_id_col = dvi.find_column(df, ["Body_ID"])
                if body_id_col:
                    all_ids = df[body_id_col].astype(str).tolist()
                    ids_to_delete = st.multiselect(
                        "Select Body ID(s) to delete",
                        options=all_ids,
                        placeholder="Choose one or more Body IDs…",
                        key="del_row_ids",
                    )
                    if ids_to_delete:
                        st.dataframe(
                            df[df[body_id_col].astype(str).isin(ids_to_delete)],
                            use_container_width=True,
                            hide_index=True,
                        )
                        if st.button("DELETE SELECTED RECORDS", type="primary", use_container_width=True, key="del_records"):
                            new_df = df[~df[body_id_col].astype(str).isin(ids_to_delete)].reset_index(drop=True)
                            ok, result = dvi.save_database_df(new_df)
                            if ok:
                                dvi.log_activity("DB_DELETE", None, {"deleted": ids_to_delete, "remaining": result})
                                st.success(f"✓ Deleted {len(ids_to_delete)} record(s). {result} remaining.")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(result)
                else:
                    st.error("Body_ID column not found in database.")

                st.divider()
                st.markdown("#### 🗑️ Clear Entire Database")
                st.error(f"This will permanently delete **all {len(df)} records** from the database. This cannot be undone.")
                confirm_clear = st.checkbox("I understand — delete all records permanently", key="confirm_clear_all")
                if confirm_clear:
                    if st.button("DELETE ALL RECORDS", type="primary", use_container_width=True, key="del_all_btn"):
                        ok, err = dvi.clear_database()
                        if ok:
                            dvi.log_activity("DB_CLEAR_ALL", None, {"deleted_count": len(df)})
                            st.success("✓ All records deleted. The database is now empty.")
                            st.session_state.pop("adm_next_body_id", None)
                            st.session_state.pop("inv_next_body_id", None)
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(err)

            # ---- Delete columns ----
            with del_col_sec:
                st.write("Select one or more columns to permanently remove from every record in the database.")
                st.warning("⚠️ Core columns (Body_ID, Sex, age, height ranges) cannot be deleted.")

                # Columns that must never be deletable
                protected = set(dvi.REQUIRED_DB_COLUMNS)
                deletable_cols = [c for c in df.columns if c not in protected]

                if not deletable_cols:
                    st.info("No deletable columns found. All current columns are core fields.")
                else:
                    cols_to_drop = st.multiselect(
                        "Select column(s) to delete",
                        options=deletable_cols,
                        placeholder="Choose one or more columns…",
                        key="del_col_names",
                    )
                    if cols_to_drop:
                        st.markdown("**Preview — columns that will be removed:**")
                        st.dataframe(
                            df[cols_to_drop].head(10),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.error(f"This will permanently delete the column(s): **{', '.join(cols_to_drop)}** from all {len(df)} records.")
                        confirm = st.checkbox("I understand this cannot be undone", key="del_col_confirm")
                        if confirm:
                            if st.button("DELETE SELECTED COLUMNS", type="primary", use_container_width=True, key="del_col_btn"):
                                new_df = df.drop(columns=cols_to_drop)
                                ok, result = dvi.save_database_df(new_df)
                                if ok:
                                    dvi.log_activity("DB_COL_DELETE", None, {"dropped_columns": cols_to_drop, "records": result})
                                    st.success(f"✓ Deleted column(s): {', '.join(cols_to_drop)}. Database saved ({result} records).")
                                    st.cache_data.clear()
                                    st.rerun()
                                else:
                                    st.error(result)

        # --------------------------------------------------------
        # ADD TAB — structured form to insert one new record
        # --------------------------------------------------------
        with add_tab:
            st.write("Fill in the fields below to add a new record directly to the database.")

            if "adm_next_body_id" not in st.session_state:
                st.session_state.adm_next_body_id = dvi.next_body_id()

            a_col1, a_col2 = st.columns(2)
            with a_col1:
                a_body_id       = st.text_input("Body ID *", value=st.session_state.adm_next_body_id,
                                                 key="a_body_id",
                                                 help="Auto-generated sequentially. Edit only if needed.")
                a_age_min       = st.number_input("Estimated Age Min *", min_value=0, max_value=120, value=0, key="a_age_min")
                a_age_max       = st.number_input("Estimated Age Max *", min_value=0, max_value=120, value=0, key="a_age_max")
                a_height_min    = st.number_input("Estimated Height Min (cm) *", min_value=0.0, max_value=250.0, value=0.0, key="a_hmin")
                a_height_max    = st.number_input("Estimated Height Max (cm) *", min_value=0.0, max_value=250.0, value=0.0, key="a_hmax")
                a_sex           = st.selectbox("Sex *", ["", "Male", "Female", "Unknown"], key="a_sex")
                a_build         = st.selectbox("Build", ["", "Slim", "Medium", "Heavy", "Athletic"], key="a_build")
                a_state         = st.text_input("State (Location Found)", placeholder="e.g. Maharashtra", key="a_state")
                a_city          = st.text_input("City (Location Found)", placeholder="e.g. Mumbai", key="a_city")
            with a_col2:
                a_hair          = st.text_input("Hair", placeholder="e.g. Black, Short", key="a_hair")
                a_physical_desc = st.text_area("Physical Description", height=90, placeholder="General appearance notes", key="a_pdesc")
                a_scars         = st.text_input("Scars", placeholder="e.g. Scar on left forearm", key="a_scars")
                a_birthmarks    = st.text_input("Birthmarks", placeholder="e.g. Birthmark on right shoulder", key="a_bmarks")
                a_clothing      = st.text_input("Clothing", placeholder="e.g. Blue shirt, jeans", key="a_clothing")
                a_dental        = st.text_input("Dental Observation", placeholder="e.g. Missing upper molar", key="a_dental")
                a_dna           = st.text_input("DNA Profile", placeholder="e.g. DNA-REF-023", key="a_dna")

            if st.button("ADD RECORD", type="primary", use_container_width=True, key="admin_add_record"):
                a_body_id_val = a_body_id.strip()
                errs = []
                if not a_body_id_val:
                    errs.append("Body ID is required.")
                if a_age_max < a_age_min:
                    errs.append("Age Max must be ≥ Age Min.")
                if a_height_max < a_height_min:
                    errs.append("Height Max must be ≥ Height Min.")
                if not a_sex:
                    errs.append("Sex is required.")

                # Explicit duplicate check
                if not errs and df is not None:
                    existing_col = dvi.find_column(df, ["Body_ID"])
                    if existing_col:
                        existing_ids = df[existing_col].astype(str).str.strip().tolist()
                        if a_body_id_val in existing_ids:
                            errs.append(f"Body ID **{a_body_id_val}** already exists. Use a different ID.")

                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    import io
                    new_row = {
                        "Body_ID":              a_body_id_val,
                        "Estimated_Age_Min":    a_age_min,
                        "Estimated_Age_Max":    a_age_max,
                        "Estimated_Height_Min": a_height_min,
                        "Estimated_Height_Max": a_height_max,
                        "Sex":                  a_sex,
                        "Build":                a_build,
                        "Hair":                 a_hair.strip(),
                        "Physical_Description": a_physical_desc.strip(),
                        "Scars":                a_scars.strip(),
                        "Birthmarks":           a_birthmarks.strip(),
                        "Clothing":             a_clothing.strip(),
                        "Dental_Observation":   a_dental.strip(),
                        "DNA_Profile":          a_dna.strip(),
                        "State":                a_state.strip(),
                        "City":                 a_city.strip(),
                    }
                    csv_buf = io.StringIO()
                    pd.DataFrame([new_row]).to_csv(csv_buf, index=False)
                    csv_bytes = io.BytesIO(csv_buf.getvalue().encode())
                    ok, result = dvi.append_database(csv_bytes)
                    if ok:
                        dvi.log_activity("DB_ADD", new_row["Body_ID"], {"body_id": new_row["Body_ID"]})
                        st.success(f"✓ Record **{new_row['Body_ID']}** added to the database.")
                        st.cache_data.clear()
                        # Advance session-state ID and reset form
                        st.session_state.adm_next_body_id = dvi.next_body_id()
                        for _k in ["a_body_id", "a_age_min", "a_age_max",
                                   "a_hmin", "a_hmax", "a_sex", "a_build",
                                   "a_state", "a_city", "a_hair", "a_pdesc",
                                   "a_scars", "a_bmarks", "a_clothing",
                                   "a_dental", "a_dna"]:
                            st.session_state.pop(_k, None)
                        st.rerun()
                    else:
                        st.error(result)

# =====================================================================
# INVESTIGATION  — investigator portal
# =====================================================================

elif st.session_state.page == "Investigation":

    # ---- compact status strip ----
    status1, status2, status3, status4 = st.columns(4)
    status1.metric("Body Records", len(df) if df is not None else 0)
    status2.metric("Matching Engine", "ACTIVE")
    status3.metric("Candidate Results", "TOP 3")
    status4.metric("Storage", "LOCAL CSV")

    st.divider()
    st.header("Investigation")

    if df is None:
        st.error("No unidentified-body database found.")
        st.info("Upload body records using the Upload Data tab first.")
        st.stop()

    st.write("Enter information about the missing person.")

    tab1, tab2 = st.tabs(["Natural Language", "Structured Input"])

    with tab1:
        description = st.text_area(
            "Family / Witness Description",
            height=180,
            placeholder=(
                "Example: My brother was a 32 year old male, 175 cm tall, "
                "medium build, black hair, wearing a blue shirt and jeans. "
                "He had a forehead scar and dental crown. "
                "DNA reference is DNA-REF-023."
            ),
        )
        if st.button("Extract Information", type="primary"):
            if not description.strip():
                st.warning("Please enter a description.")
            else:
                st.session_state.extracted_info = dvi.extract_info_from_text(description)
                st.session_state.last_results = None
                st.success("Information extracted successfully.")

    with tab2:
        left, right = st.columns(2)
        with left:
            form_age = st.number_input("Age", min_value=0, max_value=120, value=0)
            form_height = st.number_input("Height (cm)", min_value=0.0, max_value=250.0, value=0.0)
            form_sex = st.selectbox("Sex", ["Not specified", "Male", "Female"])
            form_build = st.selectbox("Build", ["Not specified", "Slim", "Medium", "Heavy", "Athletic"])
            form_hair = st.text_input("Hair")
        with right:
            form_scar = st.text_input("Scar")
            form_birthmark = st.text_input("Birthmark")
            form_clothing = st.text_input("Clothing")
            form_dental = st.text_input("Dental Observation")
            form_dna = st.text_input("DNA Reference ID", placeholder="DNA-REF-023")

        if st.button("Use Structured Information", type="primary"):
            st.session_state.extracted_info = {
                "Age": int(form_age) if form_age > 0 else None,
                "Height": float(form_height) if form_height > 0 else None,
                "Sex": None if form_sex == "Not specified" else form_sex,
                "Build": None if form_build == "Not specified" else form_build,
                "Hair": form_hair.strip() or None,
                "Scar": form_scar.strip() or None,
                "Birthmark": form_birthmark.strip() or None,
                "Clothing": form_clothing.strip() or None,
                "Dental": form_dental.strip() or None,
                "DNA": form_dna.strip().upper() or None,
            }
            st.session_state.last_results = None
            st.success("Structured information saved.")

    if st.session_state.extracted_info is not None:
        info = st.session_state.extracted_info

        st.divider()
        st.subheader("Evidence Information")

        evidence_rows = [
            {"Factor": factor, "Value": value}
            for factor, value in info.items()
            if value is not None and str(value).strip()
        ]
        if evidence_rows:
            st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)
        else:
            st.warning("No evidence was provided.")

        if st.button("Find Top 3 Potential Matches", type="primary", use_container_width=True):
            top_results = dvi.run_matching(df, info, top_n=3)

            if top_results is None:
                st.error("Body_ID column not found.")
                st.stop()

            case_id = dvi.next_case_id()
            top_body = top_results[0]["Body_ID"] if top_results else "None"
            top_score = top_results[0]["score"] if top_results else 0

            st.session_state.last_results = top_results
            st.session_state.last_case_id = case_id
            st.session_state.last_query_info = info

            dvi.log_activity(
                "INVESTIGATION",
                case_id,
                {"top_record": top_body, "score": top_score, "dna_provided": bool(info.get("DNA")), "query_info": info},
            )

        if st.session_state.last_results is not None:
            st.divider()
            st.subheader("Top 3 Potential Matches")

            for index, result in enumerate(st.session_state.last_results, start=1):
                row = result["row"]
                score = result["score"]
                tier_class = dvi.score_tier_class(score)

                with st.container(border=True):
                    st.markdown(
                        f'<div style="display:flex; align-items:center;">'
                        f'<span class="rank-badge rank-{index}">#{index}</span>'
                        f'<span style="font-size:1.3rem; font-weight:700;">{result["Body_ID"]}</span>'
                        f'&nbsp;&nbsp;<span class="{tier_class}" style="font-weight:700;">{dvi.score_tier(score)}</span>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.progress(min(int(score), 100))
                    st.metric("Similarity Score", f"{score:.2f}%")

                    left, right = st.columns(2)
                    with left:
                        st.markdown("#### Matching Factors")
                        if result["matches"]:
                            for match in result["matches"]:
                                st.success(match)
                        else:
                            st.write("No strong matches.")
                    with right:
                        st.markdown("#### Differences")
                        if result["conflicts"]:
                            for conflict in result["conflicts"]:
                                st.warning(conflict)
                        else:
                            st.write("No recorded conflicts.")

                    with st.expander("View Body Record"):
                        body_information = {
                            "Body ID": result["Body_ID"],
                            "Age Range": f"{row.get('Estimated_Age_Min', '')} - {row.get('Estimated_Age_Max', '')}",
                            "Height Range": f"{row.get('Estimated_Height_Min', '')} - {row.get('Estimated_Height_Max', '')} cm",
                            "Sex": dvi.clean_val(row.get("Sex", "")),
                            "Build": dvi.clean_val(row.get("Build", "")),
                            "Hair": dvi.clean_val(row.get("Hair", "")),
                            "Physical Description": dvi.clean_val(row.get("Physical_Description", "")),
                            "Scars": dvi.clean_val(row.get("Scars", "")),
                            "Birthmarks": dvi.clean_val(row.get("Birthmarks", "")),
                            "Clothing": dvi.clean_val(row.get("Clothing", "")),
                            "Dental": dvi.clean_val(row.get("Dental_Observation", "")),
                            "DNA Profile": dvi.clean_val(row.get("DNA_Profile", "")),
                            "State": dvi.clean_val(row.get("State", "")),
                            "City": dvi.clean_val(row.get("City", "")),
                        }
                        st.dataframe(
                            pd.DataFrame(list(body_information.items()), columns=["Field", "Value"]),
                            use_container_width=True,
                            hide_index=True,
                        )

            st.divider()
            case_id = st.session_state.get("last_case_id", "CASE-UNKNOWN")
            query_info = st.session_state.get("last_query_info", {})

            st.subheader("Reconciliation Report")
            st.write(
                f"Case reference **{case_id}** — export this shortlist "
                "for the forensic team to confirm via DNA / dental records."
            )

            report_col1, report_col2 = st.columns(2)
            with report_col1:
                pdf_bytes = dvi.build_reconciliation_pdf(query_info, st.session_state.last_results, case_id)
                st.download_button(
                    "Download PDF Report", data=pdf_bytes,
                    file_name=f"{case_id}_reconciliation_report.pdf", mime="application/pdf",
                    use_container_width=True,
                )
            with report_col2:
                csv_bytes = dvi.build_reconciliation_csv(query_info, st.session_state.last_results, case_id)
                st.download_button(
                    "Download CSV (for records/spreadsheet)", data=csv_bytes,
                    file_name=f"{case_id}_reconciliation_report.csv", mime="text/csv",
                    use_container_width=True,
                )

            st.warning(
                "These are potential matches from synthetic data. They are not "
                "forensic identification results. Final identification requires "
                "qualified forensic procedures."
            )

# =====================================================================
# UPLOAD DATA  — structured form entry OR bulk CSV upload
# =====================================================================

elif st.session_state.page == "Upload Data":

    st.header("Upload Unidentified Body Data")

    form_tab, csv_tab = st.tabs(["Structured Form", "CSV Upload"])

    # ------------------------------------------------------------------
    # TAB 1 — STRUCTURED FORM  (one record at a time)
    # ------------------------------------------------------------------
    with form_tab:
        st.write("Fill in the details below to add a single body record to the database.")

        # Keep the suggested ID in session state so it advances after
        # each successful save instead of recalculating from the old
        # cached database value on the same render cycle.
        if "inv_next_body_id" not in st.session_state:
            st.session_state.inv_next_body_id = dvi.next_body_id()

        col1, col2 = st.columns(2)
        with col1:
            f_body_id        = st.text_input("Body ID *", value=st.session_state.inv_next_body_id,
                                              key="inv_body_id_input",
                                              help="Auto-generated sequentially. Edit only if needed.")
            f_age_min        = st.number_input("Estimated Age Min *", min_value=0, max_value=120, value=0, key="inv_age_min")
            f_age_max        = st.number_input("Estimated Age Max *", min_value=0, max_value=120, value=0, key="inv_age_max")
            f_height_min     = st.number_input("Estimated Height Min (cm) *", min_value=0.0, max_value=250.0, value=0.0, key="inv_hmin")
            f_height_max     = st.number_input("Estimated Height Max (cm) *", min_value=0.0, max_value=250.0, value=0.0, key="inv_hmax")
            f_sex            = st.selectbox("Sex *", ["", "Male", "Female", "Unknown"], key="inv_sex")
            f_build          = st.selectbox("Build", ["", "Slim", "Medium", "Heavy", "Athletic"], key="inv_build")
            f_state          = st.text_input("State (Location Found)", placeholder="e.g. Maharashtra", key="inv_state")
            f_city           = st.text_input("City (Location Found)", placeholder="e.g. Mumbai", key="inv_city")
        with col2:
            f_hair           = st.text_input("Hair", placeholder="e.g. Black, Short", key="inv_hair")
            f_physical_desc  = st.text_area("Physical Description", height=90, placeholder="General appearance notes", key="inv_pdesc")
            f_scars          = st.text_input("Scars", placeholder="e.g. Scar on left forearm", key="inv_scars")
            f_birthmarks     = st.text_input("Birthmarks", placeholder="e.g. Birthmark on right shoulder", key="inv_bmarks")
            f_clothing       = st.text_input("Clothing", placeholder="e.g. Blue shirt, jeans", key="inv_clothing")
            f_dental         = st.text_input("Dental Observation", placeholder="e.g. Missing upper molar", key="inv_dental")
            f_dna            = st.text_input("DNA Profile", placeholder="e.g. DNA-REF-023", key="inv_dna")

        if st.button("ADD RECORD TO DATABASE", type="primary", use_container_width=True, key="inv_add_btn"):
            body_id_val = f_body_id.strip()
            errors = []
            if not body_id_val:
                errors.append("Body ID is required.")
            if f_age_max < f_age_min:
                errors.append("Age Max must be ≥ Age Min.")
            if f_height_max < f_height_min:
                errors.append("Height Max must be ≥ Height Min.")
            if not f_sex:
                errors.append("Sex is required.")

            # Explicit duplicate check before attempting save
            if not errors and df is not None:
                existing_col = dvi.find_column(df, ["Body_ID"])
                if existing_col:
                    existing_ids = df[existing_col].astype(str).str.strip().tolist()
                    if body_id_val in existing_ids:
                        errors.append(f"Body ID **{body_id_val}** already exists in the database. Use a different ID.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                import io
                new_row = {
                    "Body_ID":               body_id_val,
                    "Estimated_Age_Min":     f_age_min,
                    "Estimated_Age_Max":     f_age_max,
                    "Estimated_Height_Min":  f_height_min,
                    "Estimated_Height_Max":  f_height_max,
                    "Sex":                   f_sex,
                    "Build":                 f_build,
                    "Hair":                  f_hair.strip(),
                    "Physical_Description":  f_physical_desc.strip(),
                    "Scars":                 f_scars.strip(),
                    "Birthmarks":            f_birthmarks.strip(),
                    "Clothing":              f_clothing.strip(),
                    "Dental_Observation":    f_dental.strip(),
                    "DNA_Profile":           f_dna.strip(),
                    "State":                 f_state.strip(),
                    "City":                  f_city.strip(),
                }
                csv_buf = io.StringIO()
                pd.DataFrame([new_row]).to_csv(csv_buf, index=False)
                csv_bytes = io.BytesIO(csv_buf.getvalue().encode())
                ok, result = dvi.append_database(csv_bytes)
                if ok:
                    dvi.log_activity("BODY_DATA_UPLOAD", None, {"records_added": result, "body_id": new_row["Body_ID"]})
                    st.success(f"✓ Record **{new_row['Body_ID']}** added to the database.")
                    st.cache_data.clear()
                    # Advance the session-state ID to the next sequential value
                    st.session_state.inv_next_body_id = dvi.next_body_id()
                    # Clear widget keys so the form resets cleanly
                    for _k in ["inv_body_id_input", "inv_age_min", "inv_age_max",
                                "inv_hmin", "inv_hmax", "inv_sex", "inv_build",
                                "inv_state", "inv_city", "inv_hair", "inv_pdesc",
                                "inv_scars", "inv_bmarks", "inv_clothing",
                                "inv_dental", "inv_dna"]:
                        st.session_state.pop(_k, None)
                    st.rerun()
                else:
                    st.error(result)

    # ------------------------------------------------------------------
    # TAB 2 — CSV UPLOAD  (bulk)
    # ------------------------------------------------------------------
    with csv_tab:
        st.write(
            "Upload a CSV file to add multiple records at once. "
            "Existing `Body_ID` entries are skipped automatically."
        )
        with st.expander("Required CSV columns"):
            st.code(", ".join(dvi.REQUIRED_DB_COLUMNS))

        uploaded_file = st.file_uploader("Choose CSV file", type=["csv"], key="inv_upload")
        if uploaded_file is not None:
            try:
                uploaded_file.seek(0)
                preview = pd.read_csv(uploaded_file)
                preview.columns = [str(c).strip() for c in preview.columns]
                st.markdown("**Preview (first 20 rows)**")
                st.dataframe(preview.head(20), use_container_width=True, hide_index=True)

                if st.button("UPLOAD CSV TO DATABASE", type="primary", use_container_width=True):
                    ok, result = dvi.append_database(uploaded_file)
                    if ok:
                        dvi.log_activity("BODY_DATA_UPLOAD", None, {"records_added": result})
                        st.success(f"✓ {result} new record(s) added to the database.")
                        st.cache_data.clear()
                    else:
                        st.error(result)
            except Exception as e:
                st.error(f"CSV error: {e}")

    # ------------------------------------------------------------------
    # CURRENT DATABASE PREVIEW
    # ------------------------------------------------------------------
    current_db = dvi.load_database()
    if current_db is not None:
        st.divider()
        st.subheader(f"Current Database — {len(current_db)} records")
        st.dataframe(current_db, use_container_width=True, hide_index=True)
    else:
        st.info("No body records in the database yet.")

# =====================================================================
# HISTORY  — admin sees all investigator activity
#            investigator sees only their own cases
# =====================================================================

elif st.session_state.page == "History":

    if is_admin:
        st.header("Activity History")
        st.subheader("All Investigator Activity")
        all_activity = dvi.load_activity(1000)
        investigator_activity = (
            all_activity[all_activity["role"] == "investigator"]
            if not all_activity.empty and "role" in all_activity.columns
            else all_activity
        )
        if investigator_activity.empty:
            st.info("No investigator activity recorded yet.")
        else:
            st.metric("Investigator Activity Records", len(investigator_activity))
            st.dataframe(investigator_activity, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Investigator Activity CSV",
                investigator_activity.to_csv(index=False).encode(),
                "dvi_investigator_activity.csv",
                "text/csv",
                use_container_width=True,
            )

    else:
        st.header("Investigator History")
        history_df = dvi.load_activity(500, st.session_state.username)
        if history_df.empty:
            st.info("No investigations recorded yet.")
        else:
            st.dataframe(history_df, use_container_width=True, hide_index=True)

# =====================================================================
# FOOTER
# =====================================================================

dvi.render_footer()
