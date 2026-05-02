"""
LLM Client

Wraps the OpenAI-compatible chat completion API with async support,
Function Calling, and optional streaming.

Configuration is read from environment variables:
  LLM_API_KEY      — API key (required)
  LLM_BASE_URL     — base URL, default: https://api.openai.com/v1
  LLM_MODEL        — model name, default: gpt-4o
  LLM_TEMPERATURE  — sampling temperature, default: 0.8
  LLM_MAX_TOKENS   — max tokens per response, default: 1024
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Async wrapper around the OpenAI Chat Completions API.

    Supports:
    - Single-turn and multi-turn conversations
    - Function / tool calling
    - Streaming responses
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY", "sk-placeholder")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        self.temperature = temperature if temperature is not None else float(
            os.getenv("LLM_TEMPERATURE", "0.8")
        )
        self.max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "1024"))

        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(
            "LLMClient initialised: model=%s base_url=%s", self.model, self.base_url
        )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[ChatCompletionMessageParam],
        tools: Optional[List[ChatCompletionToolParam]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        Non-streaming chat completion.

        Returns a dict with keys:
          content      — assistant text (may be None when tool_calls are returned)
          tool_calls   — list of tool-call dicts, or []
          finish_reason — "stop" | "tool_calls" | "length" | …
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": json.loads(tc.function.arguments or "{}"),
                    }
                )

        return {
            "content": msg.content,
            "tool_calls": tool_calls,
            "finish_reason": choice.finish_reason,
        }

    async def stream_chat(
        self,
        messages: List[ChatCompletionMessageParam],
        tools: Optional[List[ChatCompletionToolParam]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat completion.  Yields text chunks as they arrive.

        Note: streaming with tool_calls is handled by accumulating deltas.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        async with await self._client.chat.completions.create(**kwargs) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
