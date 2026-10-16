"""LLM and embedding wrappers. Every model call in Lore goes through here: results are
cached on disk (data/cache/llm) and uncached calls stop at LLM_DAILY_CALL_CAP."""

from lore.llm.cache import CallCapExceeded, calls_today
from lore.llm.chat import LLMError, chat_json
from lore.llm.embed import embed

__all__ = ["CallCapExceeded", "LLMError", "calls_today", "chat_json", "embed"]
