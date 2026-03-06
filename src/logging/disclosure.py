"""Auto-draft AI Use Statement from conversation history."""

from anthropic import Anthropic
from loguru import logger

from src.config.settings import settings

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = settings.anthropic_api_key
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets["ANTHROPIC_API_KEY"]
            except Exception:
                pass
        _client = Anthropic(api_key=api_key)
    return _client


def draft_disclosure(conversation_history: list, student_name: str, group_name: str) -> str:
    """
    Generate a draft AI Use Statement from the conversation log.

    Args:
        conversation_history: List of {"role": ..., "content": ...} dicts
        student_name: Student's name
        group_name: Group name

    Returns:
        Draft disclosure text (student must review and edit before submitting)
    """
    if not conversation_history:
        return _fallback_disclosure(student_name, group_name)

    # Summarize user messages only (to keep prompt short)
    user_turns = [
        m["content"][:300]
        for m in conversation_history
        if m["role"] == "user"
    ]
    topic_summary = "\n".join(f"- {t}" for t in user_turns[:10])

    prompt = (
        f"A student named {student_name} (group: {group_name}) used an AI research assistant "
        f"while working on a university assignment. Based on the topics they asked about, "
        f"write a 2–4 sentence AI Use Statement suitable for an academic assignment. "
        f"The statement should describe concretely what the AI was used for "
        f"(e.g., identifying data sources, understanding the textbook's argument, "
        f"outlining the structure) without overstating the AI's contribution. "
        f"Do not claim the AI wrote any part of the submission.\n\n"
        f"Topics discussed with the AI:\n{topic_summary}\n\n"
        f"Write only the statement, in first person plural ('We used...' or 'The AI assisted us...'). "
        f"Do not add a title or any other text."
    )

    try:
        client = _get_client()
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=300,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = response.content[0].text.strip()
        logger.info(f"Disclosure drafted for {student_name} / {group_name}")
    except Exception as e:
        logger.error(f"Disclosure generation failed: {e}")
        draft = _fallback_disclosure(student_name, group_name)

    return (
        "DRAFT — REVIEW AND EDIT BEFORE SUBMITTING\n"
        "─────────────────────────────────────────\n"
        + draft
        + "\n─────────────────────────────────────────"
    )


def _fallback_disclosure(student_name: str, group_name: str) -> str:
    return (
        "DRAFT — REVIEW AND EDIT BEFORE SUBMITTING\n"
        "─────────────────────────────────────────\n"
        "We used the POLI 319 Research Assistant (powered by Claude, Anthropic) to support "
        "our research process. The AI helped us identify relevant data sources and understand "
        "how the textbook's argument relates to our chosen topic. All analysis, writing, and "
        "editorial decisions were made by the group members.\n"
        "─────────────────────────────────────────"
    )
