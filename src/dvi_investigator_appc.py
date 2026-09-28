"""
dvi_investigator_app.py
=====================================================================
RECONCILE — UNIFIED PORTAL (same login, both roles)

This file is an alternative entry point that also uses the unified
login page. It accepts both Admin and Investigator credentials on the
same form and renders the correct portal experience for each role.

For the canonical unified entry point see dvi_admin_appc.py.
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
    pages = ["DASHBOARD", "INVESTIGATION", "HISTORY"]
    page_names = {"DASHBOARD": "Dashboard", "INVESTIGATION": "Investigation", "HISTORY": "History"}
    default_page = "Dashboard"
else:
    console_subtitle = "Disaster Victim Identification &nbsp;•&nbsp; Investigator Console"
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
# DASHBOARD  — admin only
# =====================================================================

if st.session_state.page == "Dashboard" and is_admin:
    st.header("DVI Command Dashboard")
    st.info(
        "DVI decision-support console. Review potential record matches "
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
    st.subheader("DVI System Status")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Matching Engine", "ACTIVE")
    s2.metric("DNA Matching", "ENABLED")
    s3.metric("Candidate Results", "TOP 3")
    s4.metric("Storage", "LOCAL CSV")
    st.divider()
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
    if df is not None:
        st.metric("Body Records", len(df))
        st.dataframe(df.head(50), use_container_width=True, hide_index=True)
    else:
        st.warning("No unidentified-body database is available. Upload the CSV above to get started.")

# =====================================================================
# INVESTIGATION  (status strip + case workspace, combined)
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
        st.info("Ask an administrator to upload unidentified_bodies.csv from the Admin portal.")
        st.stop()

    st.write("Enter information about the missing person.")

    tab1, tab2 = st.tabs(["Natural Language", "Structured Input"])

    # -----------------------------------------------------
    # NATURAL LANGUAGE
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # STRUCTURED INPUT
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # EVIDENCE + MATCHING
    # -----------------------------------------------------
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

            # Logged right here, exactly once per search — this was
            # previously mis-indented outside the button block and
            # silently never ran (see module docstring above).
            dvi.log_activity(
                "INVESTIGATION",
                case_id,
                {"top_record": top_body, "score": top_score, "dna_provided": bool(info.get("DNA")), "query_info": info},
            )

        # -----------------------------------------------------
        # RESULTS
        # -----------------------------------------------------
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
# UPLOAD DATA  — investigator appends new body records to the database
# =====================================================================

elif st.session_state.page == "Upload Data":

    st.header("Upload Unidentified Body Data")
    st.write(
        "Upload a CSV file containing new unidentified body records. "
        "Records are **appended** to the existing database — existing entries are not overwritten. "
        "Rows whose `Body_ID` already exists in the database are skipped automatically."
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

            if st.button("UPLOAD TO DATABASE", type="primary", use_container_width=True):
                ok, result = dvi.append_database(uploaded_file)
                if ok:
                    dvi.log_activity("BODY_DATA_UPLOAD", None, {"records_added": result})
                    st.success(f"✓ {result} new record(s) added to the database.")
                    st.cache_data.clear()
                else:
                    st.error(result)
        except Exception as e:
            st.error(f"CSV error: {e}")

    current_db = dvi.load_database()
    if current_db is not None:
        st.divider()
        st.subheader(f"Current Database — {len(current_db)} records")
        st.dataframe(current_db.head(50), use_container_width=True, hide_index=True)
    else:
        st.info("No body records in the database yet. Upload a CSV above to get started.")

# =====================================================================
# HISTORY  — admin sees own + all investigator activity (two tabs)
#            investigator sees only their own cases
# =====================================================================

elif st.session_state.page == "History":

    if is_admin:
        st.header("Activity History")
        tab1, tab2 = st.tabs(["MY ACTIVITY", "ALL INVESTIGATOR ACTIVITY"])

        with tab1:
            st.subheader("My Activity")
            my_activity = dvi.load_activity(500, st.session_state.username)
            if my_activity.empty:
                st.info("No activity recorded yet for your account.")
            else:
                st.metric("My Activity Records", len(my_activity))
                st.dataframe(my_activity, use_container_width=True, hide_index=True)

        with tab2:
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
