"""
nAI Core Answerer Service
Answer generation: LLM when available, extractive fallback otherwise.
Every entry point has a streaming variant that yields events for SSE.
"""

import os
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

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
5. Answer in the language of the question.

Context documents will be provided in the following format:
[Source: path, page N]
<content>
"""

QA_PROMPT_TEMPLATE = """Based on the following context documents, please answer the question.

{context}

Question: {question}

Provide a clear, accurate answer based only on the information in the context above. If the context doesn't contain enough information to answer the question fully, say so and provide what information is available."""

CHAT_SYSTEM_PROMPT = """You are a helpful AI assistant that answers questions based on provided documents and conversation history.

When relevant context is provided, use it to answer accurately. If the context doesn't contain enough information, say so clearly.

Be conversational and helpful. Reference previous parts of the conversation when relevant. Answer in the user's language."""


def source_label(citation: Citation) -> str:
    """Human-readable location, e.g. 'Documents/Insurance/car.pdf, page 3'."""
    if citation.source_name:
        name = f"{citation.source_name}/{citation.doc_path}"
    else:
        name = (
            citation.filename
            or citation.metadata.get("original_filename")
            or os.path.basename(citation.doc_path)
        )
    if citation.page is not None:
        name += f", page {citation.page}"
    return name


class AnswererService:
    """Generates answers from retrieved citations."""

    def __init__(self, settings: Settings, llm: LLMService):
        self.settings = settings
        self.llm = llm

    def is_llm_available(self) -> bool:
        return self.llm.is_available()

    # ------------------------------------------------------------------
    # Prompt helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_context(citations: list[Citation], max_chars: int | None = None) -> str:
        parts = []
        for citation in citations:
            text = citation.text if max_chars is None else citation.text[:max_chars]
            parts.append(f"[Source: {source_label(citation)}]\n{text}\n")
        return "\n---\n".join(parts)

    @staticmethod
    def _sources_footer(citations: list[Citation]) -> str:
        if not citations:
            return ""
        lines = [f"- [{i}] {source_label(c)}" for i, c in enumerate(citations[:5], 1)]
        return "\n\n**Sources:**\n" + "\n".join(lines) + "\n"

    def _qa_messages(self, question: str, citations: list[Citation]) -> list[dict[str, str]]:
        prompt = QA_PROMPT_TEMPLATE.format(context=self._format_context(citations), question=question)
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

    def _chat_messages(self, history: list[ChatMessage], citations: list[Citation]) -> list[dict[str, str]]:
        system = CHAT_SYSTEM_PROMPT
        if citations:
            system += "\n\nRelevant document context:\n" + self._format_context(citations[:5], 500)
        messages = [{"role": "system", "content": system}]
        messages += [{"role": m.role, "content": m.content} for m in history if m.role != "system"]
        return messages

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
            excerpts.append(f"**[{i}] {source_label(cit)}**\n> {text}")

        joined = "\n\n".join(excerpts)
        hint = ""
        if not self.settings.llm_enabled:
            hint = (
                "\n\n---\n*This is an extractive answer. For generated answers, enable an LLM "
                "with `NAI_LLM_ENABLED=true`.*"
            )
        return f"Based on your indexed documents, here are the most relevant excerpts:\n\n{joined}{hint}"

    # ------------------------------------------------------------------
    # Non-streaming
    # ------------------------------------------------------------------

    async def answer(self, question: str, citations: list[Citation], use_llm: bool = True) -> AskResponse:
        if use_llm and citations and self.llm.is_available():
            try:
                text, tokens = await self.llm.complete(self._qa_messages(question, citations))
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
        )

    async def chat(self, history: list[ChatMessage], citations: list[Citation]) -> tuple[str, str]:
        """Reply to a conversation (history ends with the user message). Returns (reply, method)."""
        latest_question = next((m.content for m in reversed(history) if m.role == "user"), "")
        if self.llm.is_available():
            try:
                text, _ = await self.llm.complete(self._chat_messages(history, citations))
                return text, "llm"
            except Exception as e:
                logger.warning(f"Chat LLM failed, falling back to extractive: {e}")
        return self.compose_extractive_answer(latest_question, citations), "extractive"

    # ------------------------------------------------------------------
    # Streaming: yields {"type": "token", "text"}, optionally {"type": "error", "message"},
    # and finally {"type": "done", "method", "model", "answer"}.
    # ------------------------------------------------------------------

    async def _stream_llm(self, messages: list[dict[str, str]], footer: str) -> AsyncIterator[dict[str, Any]]:
        parts: list[str] = []
        try:
            async for delta in self.llm.stream(messages):
                parts.append(delta)
                yield {"type": "token", "text": delta}
        except Exception as e:
            if not parts:
                raise  # nothing sent yet: the caller falls back to extractive
            yield {"type": "error", "message": f"The model stopped unexpectedly: {e}"}
        if footer:
            parts.append(footer)
            yield {"type": "token", "text": footer}
        yield {"type": "done", "method": "llm", "model": self.llm.display_name, "answer": "".join(parts)}

    async def _stream_extractive(
        self, question: str, citations: list[Citation]
    ) -> AsyncIterator[dict[str, Any]]:
        text = self.compose_extractive_answer(question, citations)
        yield {"type": "token", "text": text}
        yield {"type": "done", "method": "extractive", "model": None, "answer": text}

    async def stream_answer(
        self, question: str, citations: list[Citation], use_llm: bool = True
    ) -> AsyncIterator[dict[str, Any]]:
        if use_llm and citations and self.llm.is_available():
            try:
                async for event in self._stream_llm(
                    self._qa_messages(question, citations), self._sources_footer(citations)
                ):
                    yield event
                return
            except Exception as e:
                logger.warning(f"LLM streaming failed, falling back to extractive: {e}")
        async for event in self._stream_extractive(question, citations):
            yield event

    async def stream_chat(
        self, history: list[ChatMessage], citations: list[Citation]
    ) -> AsyncIterator[dict[str, Any]]:
        latest_question = next((m.content for m in reversed(history) if m.role == "user"), "")
        if self.llm.is_available():
            try:
                async for event in self._stream_llm(self._chat_messages(history, citations), ""):
                    yield event
                return
            except Exception as e:
                logger.warning(f"Chat LLM streaming failed, falling back to extractive: {e}")
        async for event in self._stream_extractive(latest_question, citations):
            yield event


@lru_cache(maxsize=1)
def get_answerer() -> AnswererService:
    return AnswererService(get_settings(), get_llm_service())
