"""
Instructor dashboard for the POLI 319 Research Assistant.
Password-protected. Shows session logs, usage stats, group summaries, and AI disclosures.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import io
import zipfile
import datetime
import streamlit as st
import pandas as pd
from loguru import logger
from anthropic import Anthropic

from src.config.settings import settings
import src.logging.db as db

st.set_page_config(
    page_title="Instructor Dashboard — POLI 319",
    page_icon="🔒",
    layout="wide",
)

# ── Password gate ────────────────────────────────────────────────────────────
if "instructor_auth" not in st.session_state:
    st.session_state.instructor_auth = False

if not st.session_state.instructor_auth:
    st.title("🔒 Instructor Dashboard")
    pwd = st.text_input("Instructor password", type="password")
    if st.button("Login"):
        expected = settings.instructor_password
        if pwd == expected:
            st.session_state.instructor_auth = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

# ── Ensure DB exists ─────────────────────────────────────────────────────────
db.init_db(settings.db_path)

# ── Load data ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)  # refresh every 60 seconds
def load_sessions():
    return db.get_all_sessions(settings.db_path)

@st.cache_data(ttl=60)
def load_group_summaries():
    return db.get_group_summaries(settings.db_path)

@st.cache_data(ttl=60)
def load_disclosures():
    return db.get_all_disclosures(settings.db_path)

@st.cache_data(ttl=60)
def load_feedback():
    return db.get_all_feedback(settings.db_path)

sessions_df = load_sessions()
groups_df = load_group_summaries()
disclosures_df = load_disclosures()
feedback_df = load_feedback()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("📊 Instructor Dashboard — POLI 319")
st.caption("Conversation logs and usage statistics for the Textbook Addendum Research Assistant.")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total sessions", len(sessions_df))
with col2:
    n_students = sessions_df["student_id"].nunique() if not sessions_df.empty else 0
    st.metric("Unique students", n_students)
with col3:
    n_groups = sessions_df["group_name"].nunique() if not sessions_df.empty else 0
    st.metric("Unique groups", n_groups)
with col4:
    total_msgs = int(sessions_df["n_messages"].sum()) if not sessions_df.empty else 0
    st.metric("Total messages", total_msgs)

st.divider()

# ── Sidebar: backup ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Data Backup")
    st.caption(
        "HF Spaces storage may reset on restart. "
        "Download a full backup regularly to avoid losing logs."
    )

    def build_backup_zip() -> bytes:
        """Package all log data as a ZIP with CSV exports."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Sessions
            sessions = db.get_all_sessions(settings.db_path)
            zf.writestr("sessions.csv", sessions.to_csv(index=False))

            # All messages (one file per session)
            if not sessions.empty:
                all_msgs = []
                for sid in sessions["session_id"]:
                    msgs = db.get_session_messages(settings.db_path, sid)
                    if not msgs.empty:
                        msgs.insert(0, "session_id", sid)
                        all_msgs.append(msgs)
                if all_msgs:
                    zf.writestr("all_messages.csv", pd.concat(all_msgs, ignore_index=True).to_csv(index=False))

            # Disclosures
            disclosures = db.get_all_disclosures(settings.db_path)
            zf.writestr("disclosures.csv", disclosures.to_csv(index=False))

            # Feedback
            feedback = db.get_all_feedback(settings.db_path)
            zf.writestr("feedback.csv", feedback.to_csv(index=False))

            # Group summaries
            groups = db.get_group_summaries(settings.db_path)
            zf.writestr("group_summaries.csv", groups.to_csv(index=False))

        return buf.getvalue()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    st.download_button(
        label="⬇ Download full backup (ZIP)",
        data=build_backup_zip(),
        file_name=f"poli319_logs_{timestamp}.zip",
        mime="application/zip",
        use_container_width=True,
        type="primary",
    )
    st.caption(f"Last refreshed: {timestamp}")

    st.divider()
    st.markdown("### GitHub Backup")
    st.caption(
        "Pushes all CSVs to your backup repo. "
        "Requires `GITHUB_TOKEN` and `BACKUP_REPO` in Streamlit secrets."
    )
    if st.button("Push logs to GitHub now", use_container_width=True):
        from src.logging.backup import push_logs_to_github, get_github_config
        token, repo = get_github_config()
        if not token or not repo:
            st.error("GITHUB_TOKEN or BACKUP_REPO not set in Streamlit secrets.")
        else:
            with st.spinner(f"Pushing to {repo}..."):
                ok, err = push_logs_to_github(settings.db_path, token, repo)
            if ok:
                st.success(f"Logs pushed to github.com/{repo}/logs/")
            else:
                st.error(f"Push failed: {err}")

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Sessions", "Conversations", "Group Summaries", "AI Disclosures", "Feedback"])

# ── Tab 1: Sessions table ────────────────────────────────────────────────────
with tab1:
    st.subheader("All Sessions")
    if sessions_df.empty:
        st.info("No sessions yet.")
    else:
        st.dataframe(
            sessions_df,
            use_container_width=True,
            column_config={
                "session_id": st.column_config.TextColumn("Session ID", width="small"),
                "student_name": st.column_config.TextColumn("Student"),
                "student_id": st.column_config.TextColumn("Student ID"),
                "group_name": st.column_config.TextColumn("Group"),
                "start_time": st.column_config.TextColumn("Started"),
                "end_time": st.column_config.TextColumn("Ended"),
                "n_messages": st.column_config.NumberColumn("Messages"),
            },
        )
        csv = sessions_df.to_csv(index=False)
        st.download_button("Download sessions CSV", csv, "sessions.csv", "text/csv")

# ── Tab 2: Full conversation logs ────────────────────────────────────────────
with tab2:
    st.subheader("Conversation Logs")
    if sessions_df.empty:
        st.info("No sessions yet.")
    else:
        # Filter by group or student
        filter_by = st.radio("Filter by", ["Group", "Student"], horizontal=True)
        if filter_by == "Group":
            options = sorted(sessions_df["group_name"].unique().tolist())
            selected = st.selectbox("Select group", options)
            filtered = sessions_df[sessions_df["group_name"] == selected]
        else:
            options = sorted(sessions_df["student_name"].unique().tolist())
            selected = st.selectbox("Select student", options)
            filtered = sessions_df[sessions_df["student_name"] == selected]

        if not filtered.empty:
            st.markdown(f"**{len(filtered)} session(s)** for {selected}")
            for _, row in filtered.iterrows():
                with st.expander(f"Session {row['session_id'][:8]}... | {row['start_time'][:16]} | {row['n_messages']} messages"):
                    msgs = db.get_session_messages(settings.db_path, row["session_id"])
                    if msgs.empty:
                        st.write("No messages recorded.")
                    else:
                        for _, msg in msgs.iterrows():
                            role_label = "🧑 Student" if msg["role"] == "user" else "🤖 Assistant"
                            st.markdown(f"**{role_label}** _{msg['timestamp'][:16]}_")
                            st.markdown(msg["content"])
                            st.divider()
                        csv_msgs = msgs.to_csv(index=False)
                        st.download_button(
                            f"Download this session",
                            csv_msgs,
                            f"session_{row['session_id'][:8]}.csv",
                            "text/csv",
                            key=row["session_id"],
                        )

# ── Tab 3: Group summaries ────────────────────────────────────────────────────
with tab3:
    st.subheader("Group Engagement Summary")
    if groups_df.empty:
        st.info("No sessions yet.")
    else:
        st.dataframe(groups_df, use_container_width=True)

        st.markdown("#### Auto-generate topic summaries")
        st.caption(
            "For each group, this calls Claude to summarize what topics they discussed. "
            "This may take a minute."
        )
        if st.button("Generate topic summaries for all groups"):
            client = Anthropic(api_key=settings.anthropic_api_key)
            summaries = []
            groups = sessions_df["group_name"].unique()
            progress = st.progress(0)
            for i, group in enumerate(groups):
                group_sessions = sessions_df[sessions_df["group_name"] == group]["session_id"].tolist()
                all_user_msgs = []
                for sid in group_sessions:
                    msgs = db.get_session_messages(settings.db_path, sid)
                    user_msgs = msgs[msgs["role"] == "user"]["content"].tolist() if not msgs.empty else []
                    all_user_msgs.extend(user_msgs[:5])  # cap per session

                if all_user_msgs:
                    topic_text = "\n".join(f"- {m[:200]}" for m in all_user_msgs[:15])
                    try:
                        resp = client.messages.create(
                            model=settings.llm_model,
                            max_tokens=200,
                            temperature=0.3,
                            messages=[{
                                "role": "user",
                                "content": (
                                    f"Based on these student questions, summarize in 2-3 sentences "
                                    f"what research topics group '{group}' is working on:\n\n{topic_text}"
                                )
                            }]
                        )
                        summary = resp.content[0].text.strip()
                    except Exception as e:
                        summary = f"[Error: {e}]"
                else:
                    summary = "No messages recorded yet."

                summaries.append({"group": group, "topic_summary": summary})
                progress.progress((i + 1) / len(groups))

            summary_df = pd.DataFrame(summaries)
            st.dataframe(summary_df, use_container_width=True)
            csv = summary_df.to_csv(index=False)
            st.download_button("Download group summaries CSV", csv, "group_summaries.csv", "text/csv")

# ── Tab 4: AI disclosures ─────────────────────────────────────────────────────
with tab4:
    st.subheader("AI Use Statement Drafts")
    st.caption("These are auto-generated drafts. Students are expected to review and edit before submitting.")
    if disclosures_df.empty:
        st.info("No disclosures generated yet.")
    else:
        st.dataframe(disclosures_df[["student_name", "group_name", "start_time"]], use_container_width=True)
        csv = disclosures_df.to_csv(index=False)
        st.download_button("Download all disclosures CSV", csv, "disclosures.csv", "text/csv")

        st.markdown("#### Individual disclosures")
        for _, row in disclosures_df.iterrows():
            with st.expander(f"{row['student_name']} | {row['group_name']} | {row['start_time'][:16]}"):
                st.text(row["disclosure_draft"])

# ── Tab 5: Student feedback ───────────────────────────────────────────────────
with tab5:
    st.subheader("Student Feedback")
    st.caption("Ratings and comments submitted by students via the feedback form in the chat interface.")

    if feedback_df.empty:
        st.info("No feedback submitted yet.")
    else:
        # Summary metrics
        avg_rating = feedback_df["rating"].mean()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Responses", len(feedback_df))
        with col2:
            st.metric("Average rating", f"{avg_rating:.1f} / 5")
        with col3:
            pct_positive = (feedback_df["rating"] >= 4).mean() * 100
            st.metric("Rated 4–5 ★", f"{pct_positive:.0f}%")

        # Rating distribution
        st.markdown("#### Rating distribution")
        rating_counts = feedback_df["rating"].value_counts().sort_index()
        st.bar_chart(rating_counts)

        # Full table
        st.markdown("#### All responses")
        display_df = feedback_df.copy()
        display_df["rating"] = display_df["rating"].apply(lambda r: "★" * r + "☆" * (5 - r))
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "timestamp": st.column_config.TextColumn("When", width="small"),
                "student_name": st.column_config.TextColumn("Student"),
                "group_name": st.column_config.TextColumn("Group"),
                "rating": st.column_config.TextColumn("Rating"),
                "comment": st.column_config.TextColumn("Comment", width="large"),
            },
        )
        csv = feedback_df.to_csv(index=False)
        st.download_button("Download feedback CSV", csv, "feedback.csv", "text/csv")
