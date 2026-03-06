"""SQLite logging for POLI 319 chat sessions."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


def init_db(db_path: Path) -> None:
    """Create tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id      TEXT PRIMARY KEY,
            student_name    TEXT NOT NULL,
            student_id      TEXT NOT NULL,
            group_name      TEXT NOT NULL,
            start_time      TEXT NOT NULL,
            end_time        TEXT,
            n_messages      INTEGER DEFAULT 0,
            disclosure_draft TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id       TEXT PRIMARY KEY,
            session_id       TEXT NOT NULL REFERENCES sessions(session_id),
            timestamp        TEXT NOT NULL,
            role             TEXT NOT NULL,
            content          TEXT NOT NULL,
            retrieved_sources TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id  TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL REFERENCES sessions(session_id),
            timestamp    TEXT NOT NULL,
            rating       INTEGER NOT NULL,
            comment      TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.debug(f"Database initialized at {db_path}")


def start_session(
    db_path: Path,
    session_id: str,
    student_name: str,
    student_id: str,
    group_name: str,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO sessions (session_id, student_name, student_id, group_name, start_time) VALUES (?,?,?,?,?)",
        (session_id, student_name, student_id, group_name, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    logger.info(f"Session started: {session_id} ({student_name}, group: {group_name})")


def log_message(
    db_path: Path,
    session_id: str,
    role: str,
    content: str,
    retrieved_sources: list[str],
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO messages (message_id, session_id, timestamp, role, content, retrieved_sources) VALUES (?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            session_id,
            datetime.now().isoformat(),
            role,
            content,
            json.dumps(retrieved_sources),
        ),
    )
    conn.execute(
        "UPDATE sessions SET n_messages = n_messages + 1 WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()


def end_session(db_path: Path, session_id: str, disclosure_draft: Optional[str] = None) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE sessions SET end_time = ?, disclosure_draft = ? WHERE session_id = ?",
        (datetime.now().isoformat(), disclosure_draft, session_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Session ended: {session_id}")


def get_all_sessions(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        "SELECT session_id, student_name, student_id, group_name, start_time, end_time, n_messages FROM sessions ORDER BY start_time DESC",
        conn,
    )
    conn.close()
    return df


def get_session_messages(db_path: Path, session_id: str) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        "SELECT timestamp, role, content, retrieved_sources FROM messages WHERE session_id = ? ORDER BY timestamp",
        conn,
        params=(session_id,),
    )
    conn.close()
    return df


def get_group_summaries(db_path: Path) -> pd.DataFrame:
    """Aggregate sessions by group."""
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        """
        SELECT
            group_name,
            COUNT(DISTINCT student_id) AS n_students,
            COUNT(session_id) AS n_sessions,
            SUM(n_messages) AS total_messages,
            MAX(start_time) AS last_active
        FROM sessions
        GROUP BY group_name
        ORDER BY last_active DESC
        """,
        conn,
    )
    conn.close()
    return df


def get_all_disclosures(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        "SELECT session_id, student_name, group_name, start_time, disclosure_draft FROM sessions WHERE disclosure_draft IS NOT NULL ORDER BY start_time DESC",
        conn,
    )
    conn.close()
    return df


def save_feedback(db_path: Path, session_id: str, rating: int, comment: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO feedback (feedback_id, session_id, timestamp, rating, comment) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), session_id, datetime.now().isoformat(), rating, comment),
    )
    conn.commit()
    conn.close()
    logger.info(f"Feedback saved for session {session_id}: rating={rating}")


def get_all_feedback(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        """
        SELECT f.timestamp, s.student_name, s.group_name, f.rating, f.comment
        FROM feedback f
        JOIN sessions s ON f.session_id = s.session_id
        ORDER BY f.timestamp DESC
        """,
        conn,
    )
    conn.close()
    return df
