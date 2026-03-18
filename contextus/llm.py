from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import os


@dataclass
class LLMResponse:
    content: str
    raw: object = None  # original provider response, kept for debugging


class LLMClient(ABC):
    """
    Provider-agnostic interface for LLM calls.
    Swap implementations to change providers so runtime code stays decoupled.
    """

    @abstractmethod
    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        """Single-turn completion. Temperature 0 by default so behavior stays deterministic."""
        ...


class CerebrasClient(LLMClient):
    """
    Cerebras inference client using cerebras-cloud-sdk.

    The primary model may be overridden with ``CEREBRAS_MODEL``.
    Optional comma-separated fallbacks may be provided via
    ``CEREBRAS_MODEL_FALLBACKS``. If the primary model is unavailable for the
    current account, the client will try the fallback list before surfacing the
    error.
    """

    MODEL = "gpt-oss-120b"
    FALLBACK_MODELS = ("llama3.1-8b",)

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        fallback_models: tuple[str, ...] | list[str] | None = None,
    ):
        try:
            from cerebras.cloud.sdk import Cerebras
        except ImportError:
            raise ImportError(
                "cerebras_cloud_sdk is not installed. "
                "Run: pip install cerebras_cloud_sdk"
            )

        configured_model = model or os.environ.get("CEREBRAS_MODEL") or self.MODEL
        env_fallbacks = tuple(
            candidate.strip()
            for candidate in os.environ.get("CEREBRAS_MODEL_FALLBACKS", "").split(",")
            if candidate.strip()
        )
        candidates = tuple(fallback_models) if fallback_models is not None else (env_fallbacks or self.FALLBACK_MODELS)
        self._model = configured_model
        self._fallback_models = tuple(candidate for candidate in candidates if candidate and candidate != configured_model)
        self._client = Cerebras(api_key=api_key or os.environ.get("CEREBRAS_API_KEY"))

    def complete(self, system: str, user: str, temperature: float = 0.0) -> LLMResponse:
        last_error: Exception | None = None
        candidates = self._candidate_models()
        for index, model_name in enumerate(candidates):
            try:
                response = self._client.chat.completions.create(
                    model=model_name,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                self._model = model_name
                return LLMResponse(
                    content=response.choices[0].message.content,
                    raw=response,
                )
            except Exception as exc:  # pragma: no cover - provider exceptions vary by SDK version
                last_error = exc
                has_more_candidates = index + 1 < len(candidates)
                if not has_more_candidates or not self._should_try_fallback(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("No Cerebras model candidates were configured.")

    def _candidate_models(self) -> tuple[str, ...]:
        return (self._model, *self._fallback_models)

    def _should_try_fallback(self, exc: Exception) -> bool:
        message = f"{type(exc).__name__}: {exc}".lower()
        fallback_markers = (
            "model_not_found",
            "not_found",
            "does not exist",
            "do not have access",
            "not have access",
            "404",
        )
        return any(marker in message for marker in fallback_markers)
