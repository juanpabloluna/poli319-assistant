"""
Student chat interface for the POLI 319 Research Assistant.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from loguru import logger

from src.config.settings import settings
from src.chat.engine import ChatEngine
from src.rag.retriever import Retriever
import src.logging.db as db
from src.logging.disclosure import draft_disclosure

st.set_page_config(
    page_title="Chat — POLI 319",
    page_icon="💬",
    layout="wide",
)

# ── Guard: must be logged in ─────────────────────────────────────────────────
if not st.session_state.get("logged_in"):
    st.warning("Please log in first.")
    st.page_link("app.py", label="Go to login", icon="🔑")
    st.stop()

# ── Initialize chat engine (cached) ─────────────────────────────────────────
@st.cache_resource
def get_engine():
    retriever = Retriever()
    return ChatEngine(retriever=retriever)

engine = get_engine()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"**Student:** {st.session_state.student_name}")
    st.markdown(f"**Group:** {st.session_state.group_name}")
    st.markdown(f"**Format:** {st.session_state.get('format_choice', 'Not decided yet')}")
    st.divider()

    st.markdown("### Assignment quick reference")
    with st.expander("5 formats"):
        st.markdown("""
        1. **Table Update** — 1,500–2,000 words
        2. **Graph Update** — 1,500–2,000 words
        3. **New Boxes** — ~3,000 words total
        4. **New Case Study** — 3,000 words
        5. **Case Updates** — ~3,000 words total
        """)
    with st.expander("Rubric"):
        st.markdown("""
        - Content & Analysis: **40 pts**
        - Evidence & Sources: **25 pts**
        - Writing & Organization: **20 pts**
        - AI Use & Disclosure: **15 pts**
        """)
    with st.expander("Key dates"):
        st.markdown("""
        - **March 10**: Q&A in class
        - **March 12**: Written pitch due
        - **April 20**: Final submission
        """)

    st.divider()

    n_messages = len(st.session_state.get("conversation", []))

    st.divider()
    st.markdown("### AI Use Statement")
    st.caption("Required for submission — worth 15 pts.")
    with st.expander("Generate my AI Use Statement", expanded=st.session_state.get("disclosure_generated", False)):
        with st.form("ai_disclosure_form"):
            confirmed = st.checkbox(
                "I used the POLI 319 Research Assistant as part of my research process.",
            )
            st.markdown("**How did you use it?**")
            used_for_topic    = st.checkbox("Scoping my topic / research question")
            used_for_sources  = st.checkbox("Finding or evaluating data sources")
            used_for_textbook = st.checkbox("Understanding the textbook's argument")
            used_for_structure = st.checkbox("Planning the structure of my output")
            used_for_analysis = st.checkbox("Interpreting data or evidence")
            extra_context = st.text_area(
                "Other / additional context (optional)",
                placeholder="E.g. 'I used it to find data on homicide trends for Chapter 11.'",
                max_chars=400,
            )
            if st.form_submit_button("Generate draft statement", type="primary", use_container_width=True):
                if not confirmed:
                    st.warning("Please tick the confirmation checkbox first.")
                else:
                    uses = []
                    if used_for_topic:    uses.append("scoping the research topic and research question")
                    if used_for_sources:  uses.append("finding and evaluating data sources")
                    if used_for_textbook: uses.append("understanding the textbook's argument")
                    if used_for_structure: uses.append("planning the structure of the output")
                    if used_for_analysis: uses.append("interpreting data or evidence")
                    if extra_context.strip(): uses.append(extra_context.strip())

                    augmented = list(st.session_state.get("conversation", []))
                    if uses:
                        augmented = [{"role": "user", "content": "The student used the AI for: " + "; ".join(uses) + "."}] + augmented

                    with st.spinner("Drafting..."):
                        draft = draft_disclosure(augmented, st.session_state.student_name, st.session_state.group_name)

                    st.session_state.disclosure_text = draft
                    st.session_state.disclosure_generated = True
                    try:
                        db.end_session(settings.db_path, st.session_state.session_id, draft)
                    except Exception as e:
                        logger.error(f"Failed to save disclosure: {e}")
                    st.rerun()

        if st.session_state.get("disclosure_generated") and "disclosure_text" in st.session_state:
            st.success("Draft ready — review and edit before submitting.")
            edited = st.text_area(
                "Your draft (edit as needed):",
                value=st.session_state.disclosure_text,
                height=200,
            )
            st.download_button(
                "Download (.txt)",
                data=edited,
                file_name=f"AI_use_{st.session_state.group_name.replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    st.divider()
    if st.button("End session", use_container_width=True):
        try:
            db.end_session(settings.db_path, st.session_state.session_id)
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
        st.info(f"Session ended. Total messages: {n_messages // 2}")

    st.divider()
    with st.expander("Leave feedback on this tool"):
        with st.form("feedback_form"):
            rating = st.select_slider(
                "How useful was this tool?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: {1: "1 — Not useful", 2: "2 — Slightly useful",
                                        3: "3 — Somewhat useful", 4: "4 — Useful",
                                        5: "5 — Very useful"}[x],
            )
            comment = st.text_area(
                "Any comments? (optional)",
                placeholder="What worked well? What could be improved?",
                max_chars=500,
            )
            if st.form_submit_button("Submit feedback", use_container_width=True):
                try:
                    db.save_feedback(
                        settings.db_path,
                        st.session_state.session_id,
                        rating,
                        comment.strip(),
                    )
                    st.success("Thank you for your feedback!")
                except Exception as e:
                    logger.error(f"Failed to save feedback: {e}")
                    st.error("Could not save feedback — please try again.")

# ── Chat area ────────────────────────────────────────────────────────────────
st.title("💬 Research Chat")
st.caption(
    "Ask me about your topic, which data sources to use, how to read the textbook's argument, "
    "or how to structure your output. I won't write the assignment for you — but I'll help you think it through."
)

# Display conversation history
for msg in st.session_state.get("conversation", []):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Ask a research question...")

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.conversation.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response_text, source_titles = engine.chat(
                    user_message=user_input,
                    conversation_history=st.session_state.conversation[:-1],
                )
            except Exception as e:
                response_text = f"Sorry, I encountered an error: {e}. Please try again."
                source_titles = []
                logger.error(f"Chat error: {e}", exc_info=True)

        st.markdown(response_text)

        if source_titles:
            with st.expander(f"Sources consulted ({len(source_titles)})", expanded=False):
                for t in source_titles:
                    st.markdown(f"- {t}")

    st.session_state.conversation.append({"role": "assistant", "content": response_text})

    try:
        db.log_message(settings.db_path, st.session_state.session_id, "user", user_input, [])
        db.log_message(settings.db_path, st.session_state.session_id, "assistant", response_text, source_titles)
    except Exception as e:
        logger.error(f"DB log failed: {e}")

