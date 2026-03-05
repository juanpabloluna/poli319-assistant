"""Chat engine for the POLI 319 Research Assistant."""

import time
from typing import Optional

from anthropic import Anthropic
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import settings
from src.rag.retriever import Retriever
from src.chat.prompts import SYSTEM_PROMPT


class ChatEngine:
    """Conversation engine with RAG retrieval. Logging is handled by the calling page."""

    def __init__(self, retriever: Optional[Retriever] = None):
        self.retriever = retriever or Retriever()
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.llm_model
        logger.info(f"ChatEngine initialized with model: {self.model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    def _call_claude(self, messages: list) -> str:
        """Call Claude API with multi-turn message history."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return response.content[0].text

    def chat(
        self,
        user_message: str,
        conversation_history: list,
    ) -> tuple[str, list[str]]:
        """
        Process a user message and return (response_text, source_titles).

        Logging is handled by the calling page, not here.

        Args:
            user_message: The student's current message
            conversation_history: List of {"role": ..., "content": ...} dicts
                (should NOT include the current user_message turn)

        Returns:
            (response_text, list of source document titles cited)
        """
        start = time.time()

        # Retrieve relevant context from the knowledge base
        results, context = self.retriever.retrieve_with_context(
            query=user_message,
            n_results=settings.top_k,
        )

        # Extract source titles for logging
        source_titles = list({r.chunk.title for r in results}) if results else []

        # Build the user turn: prepend retrieved context to student message
        if context:
            user_turn_content = (
                f"[Relevant course material retrieved for this question]\n\n"
                f"{context}\n\n"
                f"[Student's message]\n{user_message}"
            )
        else:
            user_turn_content = user_message

        # Build full message list: last 6 history turns + new user turn
        messages = [
            *[{"role": m["role"], "content": m["content"]}
              for m in conversation_history[-6:]],
            {"role": "user", "content": user_turn_content},
        ]

        # Generate response
        response_text = self._call_claude(messages)

        elapsed = time.time() - start
        logger.info(
            f"Response in {elapsed:.2f}s | {len(results)} chunks | sources: {source_titles}"
        )

        return response_text, source_titles
