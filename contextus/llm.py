from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    raw: object = None  # original provider response, kept for debugging


class LLMClient(ABC):
    """
    Provider-agnostic interface for LLM calls.
    Swap implementations to change providers — traversal engine never touches
    provider-specific code directly.
    """

    @abstractmethod
    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        """Single-turn completion. Temperature 0 by default — we want determinism."""
        ...


class CerebrasClient(LLMClient):
    """
    Cerebras inference client using cerebras-cloud-sdk.
    Install: pip install cerebras_cloud_sdk
    Key:     set CEREBRAS_API_KEY environment variable.
    """

    MODEL = "gpt-oss-120b"

    def __init__(self, api_key: str | None = None):
        try:
            from cerebras.cloud.sdk import Cerebras
        except ImportError:
            raise ImportError(
                "cerebras_cloud_sdk is not installed. "
                "Run: pip install cerebras_cloud_sdk"
            )
        import os
        self._client = Cerebras(
            api_key=api_key or os.environ.get("CEREBRAS_API_KEY")
        )

    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self.MODEL,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return LLMResponse(
            content=response.choices[0].message.content,
            raw=response,
        )
