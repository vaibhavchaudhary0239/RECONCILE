"""
dvi_common.py
=====================================================================
Shared code for the RECONCILE.

Both dvi_admin_app.py and dvi_investigator_app.py import everything
they need from this one module: page theme/CSS, the brand mark, the
login gate, the Supabase backend, the NLP extraction + matching
engine, and the PDF/CSV report builders.

WHY THIS FILE EXISTS
---------------------
The previous version of this project had the same ~1,400 lines of
backend code (styling, auth, Supabase calls, extraction, matching,
report generation) copy-pasted into every .py file. That meant any
bug fix or tweak had to be repeated five times and easily drifted
out of sync between files. Everything that is identical across the
two portals now lives here, exactly once.
=====================================================================
"""

import base64
import hashlib
import hmac
import io
import json
import os
import re
import time
from datetime import datetime
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# =====================================================================
# PATHS / CONFIG
# =====================================================================

ASSETS_DIR = "assets"
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "unidentified_bodies.csv")
os.makedirs(DATA_DIR, exist_ok=True)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
SESSION_TIMEOUT_SECONDS = 15 * 60

# Columns that MUST be present in every uploaded CSV.
REQUIRED_DB_COLUMNS = [
    "Body_ID", "Estimated_Age_Min", "Estimated_Age_Max",
    "Estimated_Height_Min", "Estimated_Height_Max", "Sex", "Build",
    "Hair", "Physical_Description", "Scars", "Birthmarks", "Clothing",
    "Dental_Observation", "DNA_Profile",
]

# Columns that are desirable but added automatically as empty if absent.
OPTIONAL_DB_COLUMNS = ["State", "City"]

# =====================================================================
# BRAND MARK (inline SVG — matches the uploaded logo.svg/logo.png)
# =====================================================================

LOGO_SVG = """
<svg width="46" height="46" viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;">
  <defs>
    <linearGradient id="hexFill" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#16233d"/>
      <stop offset="100%" stop-color="#0f1c33"/>
    </linearGradient>
    <linearGradient id="ringAccent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#e0a13a"/>
      <stop offset="100%" stop-color="#b3313c"/>
    </linearGradient>
  </defs>
  <g stroke="#5b6f95" stroke-width="2" fill="none" stroke-linecap="square">
    <path d="M6,26 L6,6 L26,6"/>
    <path d="M134,6 L154,6 L154,26"/>
    <path d="M154,134 L154,154 L134,154"/>
    <path d="M26,154 L6,154 L6,134"/>
  </g>
  <polygon points="80,16 137,48 137,112 80,144 23,112 23,48"
           fill="url(#hexFill)" stroke="#4d6389" stroke-width="2.5"/>
  <polygon points="80,26 129,53 129,107 80,134 31,107 31,53"
           fill="none" stroke="#7c8bab" stroke-width="1" opacity="0.5"/>
  <g fill="none" stroke="#c9d3de" stroke-width="2.6" stroke-linecap="round">
    <path d="M80,54 a26,26 0 1 1 -25.5,31"/>
    <path d="M80,64 a16,16 0 1 1 -15.7,19"/>
    <path d="M80,74 a6,6 0 1 1 -5.9,7"/>
  </g>
  <line x1="42" y1="100" x2="118" y2="100" stroke="url(#ringAccent)" stroke-width="3" stroke-linecap="round"/>
  <circle cx="80" cy="100" r="4.2" fill="url(#ringAccent)"/>
  <g stroke="url(#ringAccent)" stroke-width="2.4" stroke-linecap="round">
    <line x1="80" y1="90" x2="80" y2="96"/>
    <line x1="80" y1="104" x2="80" y2="110"/>
  </g>
</svg>
"""

# =====================================================================
# PAGE CONFIG + THEME
# =====================================================================


def configure_page(title="RECONCILE"):
    """Must be the first Streamlit call in the entrypoint script."""
    st.set_page_config(
        page_title=title,
        page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "◆",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


def inject_theme():
    """Injects the shared dark/blueprint theme used by both portals."""
    st.markdown(
        """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; font-size: 17px; }

    .stApp {
        background:
            linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px) 0 0 / 42px 42px,
            linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px) 0 0 / 42px 42px,
            radial-gradient(circle at 15% 0%, rgba(30,64,110,0.30), transparent 45%),
            radial-gradient(circle at 100% 10%, rgba(120,40,40,0.15), transparent 40%),
            #0b0f19;
    }

    .dvi-header {
        position: relative;
        background: linear-gradient(135deg, #0f1c33 0%, #16233d 55%, #241419 100%);
        border: 1px solid rgba(120,150,200,0.25);
        border-radius: 10px;
        padding: 1.5rem 2rem;
        box-shadow: 0 8px 30px rgba(0,0,0,0.45);
        overflow: hidden;
    }
    .dvi-header::before {
        content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
        background: repeating-linear-gradient(135deg, #e0a13a 0px, #e0a13a 14px, #1a1f2b 14px, #1a1f2b 28px);
    }
    .dvi-brand-row { display: flex; align-items: center; gap: 0.9rem; }
    .dvi-title { font-size: 2rem !important; font-weight: 800; letter-spacing: -0.01em; color: #f3f6fb; margin: 0; line-height: 1.15; }
    .dvi-title-accent { color: #e0a13a; }
    .dvi-subtitle { color: #93a4c3; font-size: 1rem !important; margin-top: 0.2rem; }
    .dvi-badge {
        display: inline-flex; align-items: center; gap: 0.4rem;
        background: rgba(220,60,60,0.12); border: 1px solid rgba(220,90,90,0.45); color: #ff9d9d;
        font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700;
        letter-spacing: 0.08em; text-transform: uppercase; padding: 0.3rem 0.7rem; border-radius: 4px;
    }
    .dvi-badge-dot { width: 7px; height: 7px; border-radius: 50%; background: #ff5c5c; box-shadow: 0 0 6px rgba(255,92,92,0.9); }
    .dvi-badge-safe { background: rgba(120,150,200,0.10); border: 1px solid rgba(150,175,210,0.35); color: #a9b8d4; margin-top: 0.5rem; }
    .dvi-badge-safe .dvi-badge-dot { background: #6f9bd6; box-shadow: 0 0 6px rgba(111,155,214,0.9); }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 8px !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-left: 3px solid #3a5a8f;
        border-radius: 6px; padding: 0.9rem 1rem 0.6rem 1rem;
    }
    div[data-testid="stMetricValue"] { font-family: 'JetBrains Mono', monospace; color: #f3f6fb; font-size: 1.7rem !important; }
    div[data-testid="stMetricLabel"] { color: #93a4c3; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.9rem !important; }

    .stButton > button { border-radius: 6px; font-weight: 600; border: 1px solid rgba(255,255,255,0.12); transition: all 0.15s ease; font-size: 1.05rem !important; min-height: 2.7rem; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, #b3313c, #7a1f2b); border: none; }
    .stButton > button[kind="primary"]:hover { filter: brightness(1.12); box-shadow: 0 4px 18px rgba(179,49,60,0.45); }

    div[data-testid="stProgress"] > div > div { background: linear-gradient(90deg, #b3313c, #e0a13a, #2f9e6e); }

    .rank-badge {
        display: inline-flex; align-items: center; justify-content: center; width: 2.1rem; height: 2.1rem;
        border-radius: 6px; font-weight: 800; font-family: 'JetBrains Mono', monospace; font-size: 0.95rem; margin-right: 0.6rem;
    }
    .rank-1 { background: rgba(224,161,58,0.18); color: #f3c465; border: 1px solid rgba(224,161,58,0.5); }
    .rank-2 { background: rgba(180,190,200,0.15); color: #c9d3de; border: 1px solid rgba(180,190,200,0.4); }
    .rank-3 { background: rgba(180,120,70,0.18); color: #d4a373; border: 1px solid rgba(180,120,70,0.45); }

    .score-tier-high { color: #3ecf8e !important; }
    .score-tier-mid  { color: #e0a13a !important; }
    .score-tier-low  { color: #e05c5c !important; }

    .dvi-caption {
        display: flex; align-items: center; gap: 0.5rem; color: #7c8bab; font-size: 0.95rem !important;
        text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; font-family: 'JetBrains Mono', monospace; margin: 0.2rem 0 0.6rem 0;
    }
    .dvi-caption::before { content: ""; width: 18px; height: 2px; background: #e0a13a; display: inline-block; }

    .dvi-tag-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    .dvi-tag {
        background: rgba(63,158,142,0.12); border: 1px solid rgba(63,158,142,0.4); border-left: 3px solid #3ecf8e;
        color: #bfe8d8; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 600;
        letter-spacing: 0.02em; padding: 0.4rem 0.8rem; border-radius: 4px;
    }

    h1, h2, h3 { letter-spacing: -0.01em; }
    h1 { font-size: 2.2rem !important; }
    h2 { font-size: 1.7rem !important; }
    h3 { font-size: 1.35rem !important; }
    div[data-testid="stHeader"] { background: transparent; }
    footer { visibility: hidden; }
    .stMarkdown, .stText, .stWrite { font-size: 1.05rem; }
    div[data-baseweb="tab"] { font-size: 1.05rem !important; }

    .dvi-login-shell { max-width: 1150px; margin: 2rem auto 0 auto; padding: 0.5rem; }
    .dvi-login-card { background: #111827 !important; border: 1px solid #475569 !important; border-radius: 16px; padding: 2rem; box-shadow: 0 18px 50px rgba(0,0,0,0.45); }
    .dvi-login-title { color: #ffffff !important; font-size: 2rem; font-weight: 800; margin: 0 0 0.35rem 0; }
    .dvi-login-text { color: #cbd5e1 !important; font-size: 1rem; line-height: 1.6; }
    .dvi-login-label { color: #f8fafc !important; font-weight: 700; }
    div[data-testid="stRadio"] label, div[data-testid="stTextInput"] label { color: #f8fafc !important; }
    div[data-testid="stTextInput"] input { background: #0f172a !important; color: #ffffff !important; border: 1px solid #64748b !important; }
    div[data-testid="stTextInput"] input::placeholder { color: #94a3b8 !important; }
    .dvi-role-help { background: #172033; border-left: 4px solid #e0a13a; padding: 0.9rem 1rem; border-radius: 6px; color: #dbeafe !important; margin-top: 1rem; }
    section.main > div { background: transparent; }
</style>
""",
        unsafe_allow_html=True,
    )


def render_header(console_subtitle):
    """Shared page header/brand card. `console_subtitle` differentiates Admin vs Investigator."""
    st.markdown(
        f"""
        <div class="dvi-header">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.75rem;">
                <div class="dvi-brand-row">
                    {LOGO_SVG.strip()}
                    <div>
                        <p class="dvi-title">RECON<span class="dvi-title-accent">CILE</span></p>
                        <p class="dvi-subtitle">{console_subtitle}</p>
                    </div>
                </div>
                <div style="text-align:right;">
                    <span class="dvi-badge"><span class="dvi-badge-dot"></span>Decision Support Only</span><br/>
                    <span class="dvi-badge dvi-badge-safe"><span class="dvi-badge-dot"></span>Forensic Confirmation Required</span>
                </div>
            </div>
        </div>
        """.strip(),
        unsafe_allow_html=True,
    )
    st.write("")


def render_footer():
    st.divider()
    st.markdown(
        """
        <p class="dvi-subtitle" style="font-family:'JetBrains Mono', monospace;
           font-size:0.75rem; letter-spacing:0.03em;">
            RECONCILE&nbsp;&nbsp;·&nbsp;&nbsp;
            Synthetic-data prototype&nbsp;&nbsp;·&nbsp;&nbsp;
            Decision-support only — forensic confirmation required
        </p>
        """.strip(),
        unsafe_allow_html=True,
    )


# =====================================================================
# SECRETS / SUPABASE
# =====================================================================


def secret_value(section, key, default):
    try:
        return st.secrets.get(section, {}).get(key, default)
    except Exception:
        return default


# =====================================================================
# AUTH
# =====================================================================


def verify_login(username, password, expected_username, expected_password):
    return hmac.compare_digest(username.strip(), expected_username) and hmac.compare_digest(
        password, expected_password
    )


def init_session_state():
    """One place that defines every session_state key used by either app."""
    defaults = {
        "page": "Home",
        "admin": False,
        "authenticated": False,
        "role": None,
        "username": None,
        "login_attempts": 0,
        "lockout_until": 0.0,
        "last_activity": time.time(),
        "history": [],
        "extracted_info": None,
        "last_results": None,
        "last_case_id": None,
        "last_query_info": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def require_login(role, expected_username, expected_password, console_label, role_help, landing_page):
    """Kept for backward compatibility — delegates to require_unified_login."""
    require_unified_login(
        admin_username=expected_username if role == "admin" else "",
        admin_password=expected_password if role == "admin" else "",
        investigator_username=expected_username if role == "investigator" else "",
        investigator_password=expected_password if role == "investigator" else "",
        admin_landing_page=landing_page if role == "admin" else "Dashboard",
        investigator_landing_page=landing_page if role == "investigator" else "Investigation",
    )


def require_unified_login(
    admin_username,
    admin_password,
    investigator_username,
    investigator_password,
    admin_landing_page="Dashboard",
    investigator_landing_page="Investigation",
):
    """
    Single login page that accepts credentials for both Admin and
    Investigator roles. Tries admin credentials first, then investigator.
    Sets st.session_state.role to 'admin' or 'investigator' accordingly
    and routes each role to its own landing page.

    Call this right after init_session_state(). Stops script execution
    until the user is authenticated.
    """
    if not st.session_state.authenticated:
        remaining = max(0, int(st.session_state.lockout_until - time.time()))

        st.markdown("<div class='dvi-login-shell'>", unsafe_allow_html=True)
        left, right = st.columns([1.05, 1], gap="large")

        with left:
            st.markdown(
                f"""
                <div class="dvi-login-card">
                    <div class="dvi-brand-row">
                        {LOGO_SVG.strip()}
                        <div>
                            <p class="dvi-login-title">RECONCILE</p>
                            <p class="dvi-login-text">Disaster Victim Identification</p>
                        </div>
                    </div>
                    <div class="dvi-role-help" style="margin-top:1rem;">
                        <b>ADMIN</b> — manage the master database, investigate cases,
                        and review all activity.<br/><br/>
                        <b>INVESTIGATOR</b> — investigate cases, run matching,
                        and view your own history.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with right:
            st.markdown(
                "<div class='dvi-login-title'>Sign in</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div class='dvi-login-text'>Use your Admin or Investigator credentials.</div>",
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                if remaining > 0:
                    st.error(f"Too many failed attempts. Try again in {remaining} seconds.")
                else:
                    username = st.text_input("Username", autocomplete="username")
                    password = st.text_input("Password", type="password", autocomplete="current-password")

                    if st.button("LOGIN", type="primary", use_container_width=True):
                        matched_role = None
                        landing_page = None

                        if verify_login(username, password, admin_username, admin_password):
                            matched_role = "admin"
                            landing_page = admin_landing_page
                        elif verify_login(username, password, investigator_username, investigator_password):
                            matched_role = "investigator"
                            landing_page = investigator_landing_page

                        if matched_role:
                            st.session_state.authenticated = True
                            st.session_state.admin = matched_role == "admin"
                            st.session_state.role = matched_role
                            st.session_state.username = username.strip()
                            st.session_state.login_attempts = 0
                            st.session_state.lockout_until = 0.0
                            st.session_state.last_activity = time.time()
                            st.session_state.page = landing_page
                            st.rerun()
                        else:
                            st.session_state.login_attempts += 1
                            if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
                                st.session_state.lockout_until = time.time() + LOCKOUT_SECONDS
                                st.session_state.login_attempts = 0
                                st.error(f"Too many failed attempts. Locked for {LOCKOUT_SECONDS} seconds.")
                            else:
                                left_attempts = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
                                st.error(f"Invalid credentials. {left_attempts} attempt(s) remaining.")

                st.caption("Admin or Investigator access · session timeout · logout")

        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    if time.time() - st.session_state.last_activity > SESSION_TIMEOUT_SECONDS:
        st.session_state.authenticated = False
        st.session_state.admin = False
        st.session_state.role = None
        st.session_state.username = None
        st.session_state.last_activity = time.time()
        st.rerun()
    st.session_state.last_activity = time.time()


def logout_and_reset(landing_page):
    st.session_state.authenticated = False
    st.session_state.admin = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.page = landing_page


# =====================================================================
# DATABASE (SUPABASE-BACKED, LOCAL CSV FALLBACK)
# =====================================================================


ACTIVITY_FILE = os.path.join(DATA_DIR, "activity_log.json")
CASE_ID_FILE  = os.path.join(DATA_DIR, "case_id_counter.json")


def next_case_id():
    """
    Returns the next unique sequential Case ID (e.g. 'CASE-00001').
    The counter is persisted in data/case_id_counter.json so it survives
    server restarts and is never reused.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        if os.path.exists(CASE_ID_FILE):
            with open(CASE_ID_FILE, "r") as f:
                counter = json.load(f).get("last", 0)
        else:
            # Seed from any existing case IDs in the activity log
            counter = 0
            if os.path.exists(ACTIVITY_FILE):
                with open(ACTIVITY_FILE, "r") as f:
                    entries = json.load(f)
                for e in entries:
                    cid = str(e.get("case_id") or "")
                    m = re.search(r"(\d+)$", cid)
                    if m:
                        counter = max(counter, int(m.group(1)))
        counter += 1
        with open(CASE_ID_FILE, "w") as f:
            json.dump({"last": counter}, f)
        return f"CASE-{counter:05d}"
    except Exception:
        # Fallback: timestamp-based (non-sequential but collision-resistant)
        return "CASE-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")


@st.cache_data(ttl=30)
def load_database():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        df = pd.read_csv(DATA_FILE)
        df.columns = [str(c).strip() for c in df.columns]
        body_id_col = find_column(df, ["Body_ID"])
        if body_id_col and not df.empty:
            df = df.drop_duplicates(subset=[body_id_col], keep="first").reset_index(drop=True)
        return df
    except Exception:
        return None


def clear_database():
    """Deletes the local CSV. Returns (True, None) or (False, error)."""
    try:
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        load_database.clear()
        return True, None
    except Exception as e:
        return False, f"Clear error: {e}"


def save_database(uploaded_file):
    """Replace the entire database with the uploaded CSV file."""
    try:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)
        df.columns = [str(c).strip() for c in df.columns]
        missing = [c for c in REQUIRED_DB_COLUMNS if c not in df.columns]
        if missing:
            return False, "Missing columns: " + ", ".join(missing)
        if df.empty:
            return False, "The uploaded CSV contains no records."
        df.to_csv(DATA_FILE, index=False)
        load_database.clear()
        return True, df
    except Exception as e:
        return False, f"CSV upload error: {e}"


def save_database_df(df):
    """Save a DataFrame directly as the master database."""
    try:
        missing = [c for c in REQUIRED_DB_COLUMNS if c not in df.columns]
        if missing:
            return False, "Missing columns: " + ", ".join(missing)
        for col in OPTIONAL_DB_COLUMNS:
            if col not in df.columns:
                df = df.copy()
                df[col] = ""
        if df.empty:
            return False, "Cannot save an empty database."
        body_id_col = find_column(df, ["Body_ID"])
        if body_id_col:
            ids = df[body_id_col].astype(str).str.strip()
            dupes = ids[ids.duplicated()].unique().tolist()
            if dupes:
                return False, "Duplicate Body_ID(s) found — each must be unique: " + ", ".join(dupes)
        df.to_csv(DATA_FILE, index=False)
        load_database.clear()
        return True, len(df)
    except Exception as e:
        return False, f"Save error: {e}"


def next_body_id():
    """
    Returns the next sequential Body ID string (e.g. 'BODY-042') based
    on the highest numeric suffix already present in the database.
    Falls back to 'BODY-001' if the database is empty or has no
    BODY-NNN pattern IDs.
    """
    df = load_database()
    if df is None or df.empty:
        return "BODY-001"
    col = find_column(df, ["Body_ID"])
    if not col:
        return "BODY-001"
    max_num = 0
    for val in df[col].astype(str):
        m = re.search(r"(\d+)$", val.strip())
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"BODY-{max_num + 1:03d}"


def append_database(uploaded_file):
    """Append rows from uploaded_file to the existing CSV database."""
    try:
        uploaded_file.seek(0)
        new_df = pd.read_csv(uploaded_file)
        new_df.columns = [str(c).strip() for c in new_df.columns]
        missing = [c for c in REQUIRED_DB_COLUMNS if c not in new_df.columns]
        if missing:
            return False, "Missing columns: " + ", ".join(missing)
        for col in OPTIONAL_DB_COLUMNS:
            if col not in new_df.columns:
                new_df[col] = ""
        if new_df.empty:
            return False, "The uploaded CSV contains no records."
        new_id_col = find_column(new_df, ["Body_ID"])
        if new_id_col:
            self_ids = new_df[new_id_col].astype(str).str.strip()
            self_dupes = self_ids[self_ids.duplicated()].unique().tolist()
            if self_dupes:
                return False, "Duplicate Body_ID(s) within the uploaded file: " + ", ".join(self_dupes)
        existing_df = load_database()
        if existing_df is not None and not existing_df.empty:
            body_id_col = find_column(existing_df, ["Body_ID"])
            if body_id_col and new_id_col:
                existing_ids = set(existing_df[body_id_col].astype(str).str.strip())
                clash = new_df[new_id_col].astype(str).str.strip()
                clashing = clash[clash.isin(existing_ids)].unique().tolist()
                if clashing:
                    return False, "Body_ID(s) already exist in the database: " + ", ".join(clashing)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        combined_df.to_csv(DATA_FILE, index=False)
        load_database.clear()
        return True, len(new_df)
    except Exception as e:
        return False, f"CSV upload error: {e}"


def log_activity(event_type, case_id=None, details=None):
    """Append one activity entry to the local JSON log file."""
    entry = {
        "username": st.session_state.get("username") or "unknown",
        "role": st.session_state.get("role") or "unknown",
        "event_type": event_type,
        "case_id": case_id,
        "details": details or {},
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        existing = []
        if os.path.exists(ACTIVITY_FILE):
            with open(ACTIVITY_FILE, "r") as f:
                existing = json.load(f)
        existing.append(entry)
        with open(ACTIVITY_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        st.session_state.history.append(entry)


def load_activity(limit=500, username=None):
    """Load activity log from the local JSON file."""
    try:
        if os.path.exists(ACTIVITY_FILE):
            with open(ACTIVITY_FILE, "r") as f:
                entries = json.load(f)
        else:
            entries = st.session_state.get("history", [])
        if username:
            entries = [e for e in entries if e.get("username") == username]
        entries = list(reversed(entries))[:limit]
        return pd.DataFrame(entries)
    except Exception:
        return pd.DataFrame(st.session_state.get("history", []))


# =====================================================================
# GENERAL HELPERS
# =====================================================================


def normalize(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip().lower()


def find_column(df, names):
    for name in names:
        for column in df.columns:
            if normalize(column) == normalize(name):
                return column
    return None


def similarity(value1, value2):
    value1, value2 = normalize(value1), normalize(value2)
    if not value1 or not value2:
        return 0
    if value1 == value2:
        return 1.0
    if value1 in value2 or value2 in value1:
        return 0.85
    return SequenceMatcher(None, value1, value2).ratio()


# =====================================================================
# NLP EXTRACTION (ante-mortem description -> structured fields)
# =====================================================================


def extract_age(text):
    patterns = [
        r"(\d{1,3})\s*(?:years?|yrs?)\s*old",
        r"age\s*(?:is|of)?\s*(\d{1,3})",
        r"aged\s*(\d{1,3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def extract_height(text):
    match = re.search(r"(\d{2,3}(?:\.\d+)?)\s*(?:cm|centimeters?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+)\s*(?:feet|foot|ft)\s*(\d+)?", text, re.IGNORECASE)
    if match:
        feet = int(match.group(1))
        inches = int(match.group(2) or 0)
        return round(feet * 30.48 + inches * 2.54, 1)
    return None


def extract_sex(text):
    text = text.lower()

    def has_word(word):
        # Word-boundary match so "male" does NOT match inside "female",
        # and "man" does NOT match inside "woman".
        return re.search(rf"\b{re.escape(word)}\b", text) is not None

    # Explicit sex words are checked first, and "female" before "male",
    # so "she was Female" is never misread via the substring "male".
    if has_word("female"):
        return "Female"
    if has_word("male"):
        return "Male"

    female_words = ["sister", "daughter", "mother", "wife", "woman", "girl", "she", "her"]
    male_words = ["brother", "son", "father", "husband", "man", "boy", "he", "his"]

    if any(has_word(w) for w in female_words):
        return "Female"
    if any(has_word(w) for w in male_words):
        return "Male"
    return None


def extract_build(text):
    text = text.lower()
    if any(w in text for w in ["slim", "thin", "lean"]):
        return "Slim"
    if any(w in text for w in ["medium build", "average build", "medium-built"]):
        return "Medium"
    if any(w in text for w in ["heavy", "stocky", "broad", "large build"]):
        return "Heavy"
    if "athletic" in text:
        return "Athletic"
    return None


def extract_hair(text):
    text = text.lower()
    if "hair" not in text:
        return None
    colors_list = ["black", "brown", "dark brown", "blonde", "blond", "grey", "gray", "white", "red"]
    for color in colors_list:
        if color in text:
            return color.title()
    return None


def extract_feature(text, feature):
    stop_pattern = r"[^.,;]+?(?=\s+and\s|\s*[.,;]|$)"
    patterns = [
        rf"{feature}\s+(?:on|near|at)\s+(?:the\s+)?({stop_pattern})",
        rf"{feature}\s+(?:on\s+)?(?:his|her)\s+({stop_pattern})",
        rf"has\s+(?:a\s+)?{feature}\s+(?:on\s+)?({stop_pattern})",
        rf"(?:a|an)?\s*([a-z][a-z\s]{{2,25}}?)\s+{feature}s?\b",
    ]
    stopwords = {"he", "she", "they", "had", "has", "have", "and", "with", "a", "an", "the", "also"}
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            captured = match.group(1).strip()
            words = [w for w in captured.split() if w.lower() not in stopwords]
            if words:
                return " ".join(words)
    return None


def extract_clothing(text):
    words = [
        "shirt", "t-shirt", "tshirt", "jeans", "pants", "trousers", "shorts",
        "jacket", "coat", "kurta", "saree", "dress", "shoes", "sandals", "slippers",
    ]
    text = text.lower()
    found = [w for w in words if w in text]
    return ", ".join(found) if found else None


def extract_dental(text):
    words = [
        "missing tooth", "missing teeth", "molar", "premolar", "tooth", "teeth",
        "dental", "crown", "bridge", "braces", "implant", "filling", "chipped",
    ]
    text = text.lower()
    found = [w for w in words if w in text]
    return ", ".join(found) if found else None


def extract_dna(text):
    match = re.search(r"DNA[-\s]?REF[-\s]?(\d+)", text, re.IGNORECASE)
    if match:
        return f"DNA-REF-{int(match.group(1)):03d}"
    return None


def extract_info_from_text(description):
    """Runs every extractor over one free-text description."""
    return {
        "Age": extract_age(description),
        "Height": extract_height(description),
        "Sex": extract_sex(description),
        "Build": extract_build(description),
        "Hair": extract_hair(description),
        "Scar": extract_feature(description, "scar"),
        "Birthmark": extract_feature(description, "birthmark"),
        "Clothing": extract_clothing(description),
        "Dental": extract_dental(description),
        "DNA": extract_dna(description),
    }


# =====================================================================
# MATCHING ENGINE
# =====================================================================

WEIGHTS = {
    "Age": 15, "Height": 10, "Sex": 15, "Build": 5, "Hair": 5,
    "Scar": 10, "Birthmark": 10, "Clothing": 5, "Dental": 10, "DNA": 25,
}


def calculate_match(info, row):
    score = 0
    available_weight = 0
    matches = []
    conflicts = []
    row_df = row.to_frame().T

    # ---- Age ----
    if info.get("Age") is not None:
        min_col = find_column(row_df, ["Estimated_Age_Min"])
        max_col = find_column(row_df, ["Estimated_Age_Max"])
        if min_col and max_col:
            try:
                minimum, maximum = float(row[min_col]), float(row[max_col])
                weight = WEIGHTS["Age"]
                available_weight += weight
                if minimum <= info["Age"] <= maximum:
                    score += weight
                    matches.append(f"Age fits range ({minimum:.0f}-{maximum:.0f})")
                else:
                    conflicts.append(f"Age outside range ({minimum:.0f}-{maximum:.0f})")
            except Exception:
                pass

    # ---- Height ----
    if info.get("Height") is not None:
        min_col = find_column(row_df, ["Estimated_Height_Min"])
        max_col = find_column(row_df, ["Estimated_Height_Max"])
        if min_col and max_col:
            try:
                minimum, maximum = float(row[min_col]), float(row[max_col])
                weight = WEIGHTS["Height"]
                available_weight += weight
                if minimum <= info["Height"] <= maximum:
                    score += weight
                    matches.append(f"Height fits range ({minimum:.0f}-{maximum:.0f} cm)")
                else:
                    conflicts.append(f"Height outside range ({minimum:.0f}-{maximum:.0f} cm)")
            except Exception:
                pass

    # ---- Sex ----
    if info.get("Sex"):
        column = find_column(row_df, ["Sex"])
        if column:
            weight = WEIGHTS["Sex"]
            available_weight += weight
            if normalize(info["Sex"]) == normalize(row[column]):
                score += weight
                matches.append("Sex matches")
            else:
                conflicts.append("Sex does not match")

    # ---- Fuzzy text factors ----
    text_attributes = {
        "Build": ("Build", WEIGHTS["Build"]),
        "Hair": ("Hair", WEIGHTS["Hair"]),
        "Scar": ("Scars", WEIGHTS["Scar"]),
        "Birthmark": ("Birthmarks", WEIGHTS["Birthmark"]),
        "Clothing": ("Clothing", WEIGHTS["Clothing"]),
        "Dental": ("Dental_Observation", WEIGHTS["Dental"]),
    }
    for factor, (column_name, weight) in text_attributes.items():
        if info.get(factor):
            column = find_column(row_df, [column_name])
            if not column:
                continue
            available_weight += weight
            sim = similarity(info[factor], row[column])
            if sim >= 0.60:
                score += weight * sim
                matches.append(f"{factor} shows similarity")
            else:
                conflicts.append(f"{factor} has weak similarity")

    # ---- DNA ----
    if info.get("DNA"):
        dna_column = find_column(row_df, ["DNA_Profile", "DNA Profile", "DNA"])
        if dna_column:
            weight = WEIGHTS["DNA"]
            available_weight += weight
            family_dna, body_dna = normalize(info["DNA"]), normalize(row[dna_column])
            if family_dna and body_dna and family_dna == body_dna:
                score += weight
                matches.append("DNA reference matches")
            else:
                conflicts.append("DNA reference does not match")

    final_score = (score / available_weight) * 100 if available_weight > 0 else 0
    return {"score": round(final_score, 2), "matches": matches, "conflicts": conflicts}


def run_matching(df, info, top_n=3):
    """Scores every record in `df` against `info` and returns the top N."""
    body_id_column = find_column(df, ["Body_ID"])
    if not body_id_column:
        return None  # caller should show an error: Body_ID column not found

    results = []
    for _, row in df.iterrows():
        result = calculate_match(info, row)
        results.append(
            {
                "Body_ID": row[body_id_column],
                "score": result["score"],
                "matches": result["matches"],
                "conflicts": result["conflicts"],
                "row": row,
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_n]


def score_tier(score):
    if score >= 75:
        return "Strong candidate"
    if score >= 45:
        return "Possible candidate"
    return "Weak candidate"


def score_tier_class(score):
    if score >= 75:
        return "score-tier-high"
    if score >= 45:
        return "score-tier-mid"
    return "score-tier-low"


# =====================================================================
# RECONCILIATION REPORT GENERATION (CSV + PDF)
# =====================================================================


def clean_val(value, empty_text="None recorded"):
    """Turns pandas NaN / None / empty string into a readable placeholder."""
    if value is None:
        return empty_text
    try:
        if pd.isna(value):
            return empty_text
    except Exception:
        pass
    text = str(value).strip()
    return text if text and text.lower() != "nan" else empty_text


def build_reconciliation_csv(info, top_results, case_id):
    rows = []
    for rank, result in enumerate(top_results, start=1):
        row = result["row"]
        rows.append(
            {
                "Case_ID": case_id,
                "Rank": rank,
                "Body_ID": result["Body_ID"],
                "Match_Score_%": result["score"],
                "Assessment": score_tier(result["score"]),
                "Matching_Factors": "; ".join(result["matches"]) or "None",
                "Conflicting_Factors": "; ".join(result["conflicts"]) or "None",
                "Body_Sex": clean_val(row.get("Sex", "")),
                "Body_Age_Range": f"{row.get('Estimated_Age_Min','')}-{row.get('Estimated_Age_Max','')}",
                "Body_Height_Range_cm": f"{row.get('Estimated_Height_Min','')}-{row.get('Estimated_Height_Max','')}",
                "Body_Build": clean_val(row.get("Build", "")),
                "Body_Hair": clean_val(row.get("Hair", "")),
                "Body_Scars": clean_val(row.get("Scars", "")),
                "Body_Birthmarks": clean_val(row.get("Birthmarks", "")),
                "Body_Clothing": clean_val(row.get("Clothing", "")),
                "Body_Dental": clean_val(row.get("Dental_Observation", "")),
                "Body_DNA_Profile": clean_val(row.get("DNA_Profile", "")),
                "Family_Reported_Age": info.get("Age", ""),
                "Family_Reported_Height_cm": info.get("Height", ""),
                "Family_Reported_Sex": info.get("Sex", ""),
                "Family_Reported_Build": info.get("Build", ""),
                "Family_Reported_Hair": info.get("Hair", ""),
                "Family_Reported_Scar": info.get("Scar", ""),
                "Family_Reported_Birthmark": info.get("Birthmark", ""),
                "Family_Reported_Clothing": info.get("Clothing", ""),
                "Family_Reported_Dental": info.get("Dental", ""),
                "Family_Reported_DNA_Ref": info.get("DNA", ""),
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def build_reconciliation_pdf(info, top_results, case_id):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DVITitle", parent=styles["Title"], fontSize=17, textColor=colors.HexColor("#16233d"), spaceAfter=4)
    sub_style = ParagraphStyle("DVISub", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#555555"), spaceAfter=14)
    h2_style = ParagraphStyle("DVIh2", parent=styles["Heading2"], fontSize=12.5, textColor=colors.HexColor("#7a1f2b"), spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle("DVIBody", parent=styles["Normal"], fontSize=9.5, leading=13)
    small_style = ParagraphStyle("DVISmall", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#666666"))

    elements = [
        Paragraph("RECONCILE — Reconciliation Report", title_style),
        Paragraph(
            f"Case reference: <b>{case_id}</b> &nbsp;|&nbsp; "
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; "
            f"Status: Pending forensic confirmation",
            sub_style,
        ),
        Paragraph(
            "This report is an automated decision-support output based on ante-mortem "
            "(family/witness-reported) information cross-referenced against post-mortem "
            "body records. It is <b>not</b> a forensic identification. Final confirmation "
            "must be performed by qualified forensic personnel using DNA, dental and/or "
            "fingerprint evidence in accordance with INTERPOL DVI protocol.",
            body_style,
        ),
        Paragraph("Ante-Mortem Information Provided", h2_style),
    ]

    am_labels = [
        ("Age", "Age"), ("Height", "Height (cm)"), ("Sex", "Sex"), ("Build", "Build"),
        ("Hair", "Hair"), ("Scar", "Scar"), ("Birthmark", "Birthmark"), ("Clothing", "Clothing"),
        ("Dental", "Dental"), ("DNA", "DNA Reference"),
    ]
    am_rows = [["Factor", "Family-Reported Value"]]
    for key, label in am_labels:
        value = info.get(key)
        am_rows.append([label, str(value) if value not in (None, "") else "Not provided"])

    am_table = Table(am_rows, colWidths=[5 * cm, 10.5 * cm])
    am_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16233d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(am_table)
    elements.append(Paragraph("Top Candidate Post-Mortem Records", h2_style))

    for rank, result in enumerate(top_results, start=1):
        row, score = result["row"], result["score"]
        elements.append(Paragraph(
            f"#{rank} — {result['Body_ID']} &nbsp;&nbsp; <b>Score: {score:.2f}%</b> &nbsp;&nbsp; ({score_tier(score)})",
            ParagraphStyle("CandTitle", parent=styles["Heading3"], fontSize=10.5, textColor=colors.HexColor("#16233d"), spaceBefore=10, spaceAfter=3),
        ))
        detail_rows = [
            ["Sex", clean_val(row.get("Sex", ""))],
            ["Age range", f"{row.get('Estimated_Age_Min','')}-{row.get('Estimated_Age_Max','')}"],
            ["Height range (cm)", f"{row.get('Estimated_Height_Min','')}-{row.get('Estimated_Height_Max','')}"],
            ["Build / Hair", f"{clean_val(row.get('Build',''))} / {clean_val(row.get('Hair',''))}"],
            ["Scars", clean_val(row.get("Scars", ""))],
            ["Birthmarks", clean_val(row.get("Birthmarks", ""))],
            ["Clothing", clean_val(row.get("Clothing", ""))],
            ["Dental", clean_val(row.get("Dental_Observation", ""))],
            ["DNA profile", clean_val(row.get("DNA_Profile", ""))],
        ]
        detail_table = Table(detail_rows, colWidths=[4 * cm, 11.5 * cm])
        detail_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(detail_table)

        matches_text = "; ".join(result["matches"]) or "None recorded"
        conflicts_text = "; ".join(result["conflicts"]) or "None recorded"
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>Matching factors:</b> {matches_text}", small_style))
        elements.append(Paragraph(f"<b>Conflicting factors:</b> {conflicts_text}", small_style))
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph(
        "Prepared by the RECONCILE (synthetic-data prototype). "
        "This document is a lead sheet for forensic teams and does not constitute a legal identification.",
        small_style,
    ))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
