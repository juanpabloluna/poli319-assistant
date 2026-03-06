"""Push log exports to a GitHub repository for persistent backup."""

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from loguru import logger


def _github_put(token: str, repo: str, path: str, content_bytes: bytes, message: str) -> bool:
    """Create or update a file in a GitHub repo via the REST API."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Get current SHA if file exists (required for updates)
    existing = requests.get(url, headers=headers, timeout=10)
    sha = existing.json().get("sha") if existing.status_code == 200 else None

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload, timeout=15)
    if r.status_code in (200, 201):
        return True
    logger.error(f"GitHub backup failed for {path}: {r.status_code} {r.text[:200]}")
    return False


def push_logs_to_github(db_path: Path, token: str, repo: str) -> bool:
    """
    Export all log tables as CSVs and push them to a GitHub repo.

    Args:
        db_path: Path to the SQLite database
        token: GitHub Personal Access Token (repo scope)
        repo: Target repo in "owner/name" format (e.g. "juanpabloluna/poli319-logs")

    Returns:
        True if all files pushed successfully
    """
    import src.logging.db as db  # avoid circular import at module level

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    commit_msg = f"Auto-backup: {timestamp}"

    exports = {
        "logs/sessions.csv": db.get_all_sessions(db_path).to_csv(index=False).encode(),
        "logs/group_summaries.csv": db.get_group_summaries(db_path).to_csv(index=False).encode(),
        "logs/disclosures.csv": db.get_all_disclosures(db_path).to_csv(index=False).encode(),
        "logs/feedback.csv": db.get_all_feedback(db_path).to_csv(index=False).encode(),
    }

    # Full messages export
    import pandas as pd
    sessions = db.get_all_sessions(db_path)
    if not sessions.empty:
        all_msgs = []
        for sid in sessions["session_id"]:
            msgs = db.get_session_messages(db_path, sid)
            if not msgs.empty:
                msgs.insert(0, "session_id", sid)
                all_msgs.append(msgs)
        if all_msgs:
            exports["logs/all_messages.csv"] = pd.concat(all_msgs, ignore_index=True).to_csv(index=False).encode()

    success = True
    for path, content in exports.items():
        ok = _github_put(token, repo, path, content, commit_msg)
        if ok:
            logger.info(f"Backed up {path} to github:{repo}")
        else:
            success = False

    return success


def get_github_config() -> tuple[Optional[str], Optional[str]]:
    """Read GitHub token and backup repo from Streamlit secrets."""
    try:
        import streamlit as st
        token = st.secrets.get("GITHUB_TOKEN")
        repo = st.secrets.get("BACKUP_REPO")
        return token, repo
    except Exception:
        return None, None
