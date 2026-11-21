"""
nAI Core Answerer Service
Answer generation: LLM when available, extractive fallback otherwise.
"""

import os
from functools import lru_cache

from ..config import Settings, get_settings
from ..models.schemas import AskResponse, ChatMessage, Citation
from ..utils.logging import get_logger
from .llm import LLMService, get_llm_service

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions based on the provided context documents.

Instructions:
1. Answer ONLY based on the provided context. If the context doesn't contain enough information, say so.
2. Be concise and accurate.
3. When referencing information, mention which source document it comes from.
4. If you're uncertain, express that uncertainty.
5. Format your response clearly with proper structure when appropriate.

Context documents will be provided in the following format:
[Source: filename, Chunk #N]
<content>
"""

QA_PROMPT_TEMPLATE = """Based on the following context documents, please answer the question.

{context}

Question: {question}

Provide a clear, accurate answer based only on the information in the context above. If the context doesn't contain enough information to answer the question fully, say so and provide what information is available."""

CHAT_SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions based on provided documents and conversation history.

When relevant context is provided, use it to answer accurately. If the context doesn't contain enough information, say so clearly.

Be conversational and helpful. Reference previous parts of the conversation when relevant."""


def _source_name(citation: Citation) -> str:
    return citation.metadata.get("original_filename") or os.path.basename(citation.doc_path)


class AnswererService:
    """Generates answers from retrieved citations."""

    def __init__(self, settings: Settings, llm: LLMService):
        self.settings = settings
        self.llm = llm

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_llm_available(self) -> bool:
        return self.llm.is_available()

    @staticmethod
    def _format_context(citations: list[Citation], max_chars: int | None = None) -> str:
        parts = []
        for citation in citations:
            text = citation.text if max_chars is None else citation.text[:max_chars]
            parts.append(f"[Source: {_source_name(citation)}, Chunk #{citation.chunk_id}]\n{text}\n")
        return "\n---\n".join(parts)

    @staticmethod
    def _sources_footer(citations: list[Citation]) -> str:
        if not citations:
            return ""
        lines = [f"- [{i}] {_source_name(c)} (chunk {c.chunk_id})" for i, c in enumerate(citations[:5], 1)]
        return "\n\n**Sources:**\n" + "\n".join(lines) + "\n"

    def compose_extractive_answer(
        self,
        question: str,
        citations: list[Citation],
        max_excerpt_length: int = 500,
    ) -> str:
        """Answer by quoting the most relevant passages (no LLM required)."""
        if not citations:
            return "I couldn't find any relevant information in the indexed documents for your question."

        excerpts = []
        for i, cit in enumerate(citations[:3], 1):
            text = cit.text[:max_excerpt_length]
            if len(cit.text) > max_excerpt_length:
                last_period = text.rfind(".")
                if last_period > max_excerpt_length // 2:
                    text = text[: last_period + 1]
                else:
                    text = text + "..."
            excerpts.append(f"**[{i}] From: {_source_name(cit)}** (relevance: {cit.score:.2f})\n> {text}")

        joined = "\n\n".join(excerpts)
        hint = ""
        if not self.settings.llm_enabled:
            hint = (
                "\n\n---\n*This is an extractive answer. For generated answers, enable an LLM "
                "with `NAI_LLM_ENABLED=true`.*"
            )
        return f"Based on your indexed documents, here are the most relevant excerpts:\n\n{joined}{hint}"

    # ------------------------------------------------------------------
    # Single question
    # ------------------------------------------------------------------

    async def answer(self, question: str, citations: list[Citation], use_llm: bool = True) -> AskResponse:
        """Answer a question from retrieved citations."""
        if use_llm and citations and self.llm.is_available():
            prompt = QA_PROMPT_TEMPLATE.format(context=self._format_context(citations), question=question)
            try:
                text, tokens = await self.llm.complete(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ]
                )
                return AskResponse(
                    answer=text + self._sources_footer(citations),
                    citations=citations,
                    method="llm",
                    model=self.llm.display_name,
                    tokens_used=tokens,
                )
            except Exception as e:
                logger.warning(f"LLM failed, falling back to extractive: {e}")

        return AskResponse(
            answer=self.compose_extractive_answer(question, citations),
            citations=citations,
            method="extractive",
            model=None,
        )

    # ------------------------------------------------------------------
    # Multi-turn chat
    # ------------------------------------------------------------------

    async def chat(self, history: list[ChatMessage], citations: list[Citation]) -> tuple[str, str]:
        """
        Reply to a conversation. ``history`` ends with the latest user message.
        Returns (reply, method) where method is ``llm`` or ``extractive``.
        """
        latest_question = next((m.content for m in reversed(history) if m.role == "user"), "")

        if self.llm.is_available():
            system = CHAT_SYSTEM_PROMPT
            if citations:
                system += "\n\nRelevant document context:\n" + self._format_context(citations[:5], 500)
            messages = [{"role": "system", "content": system}]
            messages += [{"role": m.role, "content": m.content} for m in history if m.role != "system"]
            try:
                text, _ = await self.llm.complete(messages)
                return text, "llm"
            except Exception as e:
                logger.warning(f"Chat LLM failed, falling back to extractive: {e}")

        return self.compose_extractive_answer(latest_question, citations), "extractive"


@lru_cache(maxsize=1)
def get_answerer() -> AnswererService:
    """Get the answerer service singleton."""
    return AnswererService(get_settings(), get_llm_service())
