"""
POLI 319 Research Assistant — Main entry point.

Handles login gate, then routes to the chat interface.
Run with: streamlit run app.py
"""

import sys
import uuid
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import os

import streamlit as st

# Streamlit Cloud exposes secrets via st.secrets, not os.environ.
# Inject them so pydantic_settings can find them.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k.upper(), _v)
except Exception:
    pass

from loguru import logger

from src.config.settings import settings
import src.logging.db as db

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="POLI 319 Research Assistant",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database on first run
@st.cache_resource
def setup_db():
    db.init_db(settings.db_path)
    return True

setup_db()

# Auto-build ChromaDB index if missing (runs in background thread so app stays responsive)
@st.cache_resource
def setup_index():
    import threading
    import subprocess

    chromadb_path = settings.chromadb_path
    sqlite_path = chromadb_path / "chroma.sqlite3"
    if sqlite_path.exists():
        return True

    def run_ingest():
        logger.info("ChromaDB index not found — running ingestion in background...")
        try:
            result = subprocess.run(
                ["python", "scripts/ingest.py"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info("Ingestion complete.")
            else:
                logger.error(f"Ingestion failed: {result.stderr}")
        except Exception as e:
            logger.error(f"Failed to run ingestion: {e}")

    thread = threading.Thread(target=run_ingest, daemon=True)
    thread.start()
    return True

setup_index()

# ── Login gate ───────────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("📚 POLI 319 — Latin American Politics and Society")
    st.subheader("Textbook Addendum Research Assistant")
    st.markdown(
        "This tool helps you complete the Textbook Addendum assignment. "
        "It can help you scope your topic, find data sources, understand the textbook's argument, "
        "and structure your output. **It will not write your assignment for you.**"
    )
    st.divider()

    with st.form("login_form"):
        st.markdown("#### Enter your information to begin")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full name")
            student_id = st.text_input("McGill student ID")
        with col2:
            group_name = st.text_input(
                "Group name / number",
                help="Use the same group name all team members use (e.g. 'Group 7' or your MyCourses registration name)"
            )
            format_choice = st.selectbox(
                "Assignment format (if you've decided)",
                ["Not decided yet", "Format 1 — Table Update", "Format 2 — Graph Update",
                 "Format 3 — New Boxes", "Format 4 — New Case Study", "Format 5 — Case Updates"]
            )
        access_code = st.text_input("Course access code", help="Posted on MyCourses")
        submitted = st.form_submit_button("Start research session", type="primary")

    if submitted:
        name = name.strip()
        student_id = student_id.strip()
        group_name = group_name.strip()
        access_code = access_code.strip()

        if not name:
            st.error("Please enter your full name.")
        elif len(student_id) < 6 or not student_id.replace("-", "").isdigit():
            st.error("Please enter a valid McGill student ID (9 digits).")
        elif not group_name:
            st.error("Please enter your group name or number.")
        elif access_code != settings.course_code:
            st.error("Incorrect access code. Check MyCourses for the code.")
        else:
            session_id = str(uuid.uuid4())
            st.session_state.logged_in = True
            st.session_state.student_name = name
            st.session_state.student_id = student_id
            st.session_state.group_name = group_name
            st.session_state.format_choice = format_choice
            st.session_state.session_id = session_id
            st.session_state.conversation = []  # list of {"role", "content"}
            st.session_state.disclosure_generated = False

            try:
                db.start_session(settings.db_path, session_id, name, student_id, group_name)
            except Exception as e:
                logger.error(f"Failed to start session in DB: {e}")

            st.rerun()

    st.divider()
    st.caption(
        "Assignment due: **April 20, 2026** via MyCourses · "
        "Pitch due: **March 12** · "
        "Q&A in class: **March 10**"
    )
    st.stop()

# ── If logged in, show chat (redirect to pages/1_Chat.py logic inline) ───────
# Streamlit multipage: logged-in users see the sidebar with pages.
# The main app.py just confirms login and lets navigation take over.

st.title("📚 POLI 319 Research Assistant")
st.info(
    f"Welcome, **{st.session_state.student_name}** (Group: {st.session_state.group_name}). "
    f"Use the **Chat** page in the sidebar to start your research session.",
    icon="👋"
)

st.markdown("""
### Quick reference

| Format | What you produce | Word count |
|--------|-----------------|------------|
| 1 — Table Update | Update 2 tables + analytical text | 1,500–2,000 |
| 2 — Graph Update | Update 2 figures + analytical text | 1,500–2,000 |
| 3 — New Boxes | 2 new thematic boxes | ~3,000 total |
| 4 — New Case Study | 1 new case for Ch. 5–15 | 3,000 |
| 5 — Case Updates | 2 updates on existing cases | ~3,000 total |

**Grading**: Content & Analysis (40) · Evidence & Sources (25) · Writing (20) · AI Use & Disclosure (15)

**Key dates**: Pitch due March 12 · Final submission April 20
""")
