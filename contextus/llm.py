from __future__ import annotations
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping
import base64
import os
import threading


@dataclass
class LLMResponse:
    content: str
    raw: object = None  # original provider response, kept for debugging


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    temperature: float = 0.0
    response_format: Mapping[str, Any] | None = None


_EXECUTOR_LOCK = threading.Lock()
_EXECUTOR: ThreadPoolExecutor | None = None


def _llm_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _EXECUTOR is None:
                max_workers = int(os.environ.get("CONTEXTUS_LLM_CONCURRENCY", "4"))
                _EXECUTOR = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="contextus-llm")
    return _EXECUTOR


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


class LLMClient(ABC):
    """
    Provider-agnostic interface for LLM calls.
    Swap implementations to change providers so runtime code stays decoupled.
    """

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        """Single-turn completion. Temperature 0 by default so behavior stays deterministic."""
        ...

    def complete_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        *,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> LLMResponse:
        raise NotImplementedError(f"{type(self).__name__} does not support image input.")

    def submit(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> Future[LLMResponse]:
        """Submit one completion request without blocking the caller."""
        return _llm_executor().submit(
            self.complete,
            system,
            user,
            temperature,
            response_format=response_format,
        )

    def complete_many(self, requests: list[LLMRequest]) -> list[LLMResponse]:
        """Run independent completion requests concurrently and preserve order."""
        futures = [
            self.submit(
                system=request.system,
                user=request.user,
                temperature=request.temperature,
                response_format=request.response_format,
            )
            for request in requests
        ]
        return [future.result() for future in futures]


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
        openai_fallback: LLMClient | None = None,
        enable_openai_fallback: bool | None = None,
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
        self._model_lock = threading.Lock()
        self._openai_fallback = openai_fallback
        self._openai_fallback_lock = threading.Lock()
        self._enable_openai_fallback = (
            _env_flag("CONTEXTUS_OPENAI_FALLBACK", default=True)
            if enable_openai_fallback is None
            else bool(enable_openai_fallback)
        )
        self._client = Cerebras(api_key=api_key or os.environ.get("CEREBRAS_API_KEY"))

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        last_error: Exception | None = None
        candidates = self._candidate_models()
        request_format = _normalize_response_format(response_format)
        for index, model_name in enumerate(candidates):
            try:
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "temperature": temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if request_format is not None:
                    kwargs["response_format"] = request_format
                response = self._client.chat.completions.create(**kwargs)
                self._set_model(model_name)
                return LLMResponse(
                    content=response.choices[0].message.content,
                    raw=response,
                )
            except Exception as exc:  # pragma: no cover - provider exceptions vary by SDK version
                last_error = exc
                if self._should_try_openai_fallback(exc):
                    fallback_response = self._complete_with_openai_fallback(
                        system=system,
                        user=user,
                        temperature=temperature,
                        response_format=response_format,
                        original_error=exc,
                    )
                    if fallback_response is not None:
                        return fallback_response
                has_more_candidates = index + 1 < len(candidates)
                if not has_more_candidates or not self._should_try_fallback(exc):
                    fallback_response = self._complete_with_openai_fallback(
                        system=system,
                        user=user,
                        temperature=temperature,
                        response_format=response_format,
                        original_error=exc,
                    )
                    if fallback_response is not None:
                        return fallback_response
                    raise
        if last_error is not None:
            fallback_response = self._complete_with_openai_fallback(
                system=system,
                user=user,
                temperature=temperature,
                response_format=response_format,
                original_error=last_error,
            )
            if fallback_response is not None:
                return fallback_response
            raise last_error
        raise RuntimeError("No Cerebras model candidates were configured.")

    def _candidate_models(self) -> tuple[str, ...]:
        lock = getattr(self, "_model_lock", None)
        if lock is None:
            return (self._model, *self._fallback_models)
        with lock:
            return (self._model, *self._fallback_models)

    def _set_model(self, model_name: str) -> None:
        lock = getattr(self, "_model_lock", None)
        if lock is None:
            self._model = model_name
            return
        with lock:
            self._model = model_name

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

    def _should_try_openai_fallback(self, exc: Exception) -> bool:
        if not getattr(self, "_enable_openai_fallback", False):
            return False
        message = f"{type(exc).__name__}: {exc}".lower()
        provider_markers = (
            "token_quota_exceeded",
            "tokens per day",
            "too many tokens processed",
            "rate limit",
            "ratelimit",
            "429",
            "quota",
            "temporarily unavailable",
            "service unavailable",
            "503",
        )
        return any(marker in message for marker in provider_markers)

    def _complete_with_openai_fallback(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        response_format: Mapping[str, Any] | None,
        original_error: Exception,
    ) -> LLMResponse | None:
        fallback = self._get_openai_fallback()
        if fallback is None:
            return None
        try:
            response = fallback.complete(
                system=system,
                user=user,
                temperature=temperature,
                response_format=response_format,
            )
        except Exception:
            return None
        return LLMResponse(
            content=response.content,
            raw={
                "provider": "openai_fallback",
                "fallback_response": response.raw,
                "original_error": f"{type(original_error).__name__}: {original_error}",
            },
        )

    def _get_openai_fallback(self) -> LLMClient | None:
        if not getattr(self, "_enable_openai_fallback", False):
            return None
        fallback = getattr(self, "_openai_fallback", None)
        if fallback is not None:
            return fallback
        if not os.environ.get("OPENAI_API_KEY"):
            return None

        lock = getattr(self, "_openai_fallback_lock", None)
        if lock is None:
            self._openai_fallback = OpenAIResponsesClient()
            return self._openai_fallback
        with lock:
            if self._openai_fallback is None:
                self._openai_fallback = OpenAIResponsesClient()
            return self._openai_fallback


class OpenAIResponsesClient(LLMClient):
    """OpenAI Responses API client with optional image input support."""

    MODEL = "gpt-5-nano"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIResponsesClient. "
                "Run: pip install openai"
            ) from exc

        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIResponsesClient.")
        self._model = model or os.environ.get("OPENAI_MODEL") or self.MODEL
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self._reasoning_effort = reasoning_effort or os.environ.get("OPENAI_REASONING_EFFORT") or "minimal"
        self._verbosity = verbosity or os.environ.get("OPENAI_VERBOSITY") or "low"
        self._max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "800"))
        )
        self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        *,
        response_format: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "instructions": system,
            "input": user,
        }
        if self._reasoning_effort:
            kwargs["reasoning"] = {"effort": self._reasoning_effort}
        if self._max_output_tokens > 0:
            kwargs["max_output_tokens"] = self._max_output_tokens
        text_config = _openai_text_config(response_format)
        if self._verbosity:
            text_config = dict(text_config or {})
            text_config["verbosity"] = self._verbosity
        if text_config is not None:
            kwargs["text"] = text_config
        response = self._client.responses.create(**kwargs)
        return LLMResponse(content=self._extract_text(response), raw=response)

    def complete_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        *,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> LLMResponse:
        image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        response = self._client.responses.create(
            model=self._model,
            instructions=system,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
        )
        return LLMResponse(content=self._extract_text(response), raw=response)

    def _extract_text(self, response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        if isinstance(response, dict):
            return self._extract_text_from_dict(response)

        dumped = self._response_as_dict(response)
        if isinstance(dumped, dict):
            return self._extract_text_from_dict(dumped)
        return ""

    def _extract_text_from_dict(self, response: dict[str, object]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        pieces: list[str] = []
        for item in response.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    pieces.append(text)
        return "\n".join(piece for piece in pieces if piece).strip()

    def _response_as_dict(self, response: object) -> dict[str, object] | None:
        if isinstance(response, dict):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            dumped = to_dict()
            if isinstance(dumped, dict):
                return dumped
        return None


def _normalize_response_format(response_format: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Normalize caller-supplied JSON format hints to Cerebras chat-completion shape."""
    if response_format is None:
        return None
    if not isinstance(response_format, Mapping):
        raise TypeError("response_format must be a mapping.")

    candidate = deepcopy(dict(response_format))
    if "format" in candidate and "type" not in candidate:
        return _normalize_response_format(candidate["format"])

    format_type = candidate.get("type")
    if format_type == "json_object":
        return {"type": "json_object"}

    if format_type == "json_schema":
        if isinstance(candidate.get("json_schema"), Mapping):
            json_schema = deepcopy(dict(candidate["json_schema"]))
            schema = json_schema.get("schema")
            if not isinstance(schema, Mapping):
                raise ValueError("response_format.json_schema.schema must be a JSON schema object.")
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": str(json_schema.get("name") or "response_schema"),
                    "strict": bool(json_schema.get("strict", True)),
                    "schema": deepcopy(dict(schema)),
                    **(
                        {"description": str(json_schema["description"])}
                        if json_schema.get("description") is not None
                        else {}
                    ),
                },
            }
        if isinstance(candidate.get("schema"), Mapping):
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": str(candidate.get("name") or "response_schema"),
                    "strict": bool(candidate.get("strict", True)),
                    "schema": deepcopy(dict(candidate["schema"])),
                    **(
                        {"description": str(candidate["description"])}
                        if candidate.get("description") is not None
                        else {}
                    ),
                },
            }
        raise ValueError("json_schema response_format must include a schema object.")

    if format_type == "object" and isinstance(candidate.get("properties"), Mapping):
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response_schema",
                "strict": True,
                "schema": candidate,
            },
        }

    raise ValueError(
        "response_format must be json_object, json_schema, an OpenAI text format, "
        "or a raw JSON object schema."
    )


def _openai_text_config(response_format: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Convert caller-supplied format hints to OpenAI Responses text config."""
    normalized = _normalize_response_format(response_format)
    if normalized is None:
        return None
    if normalized["type"] == "json_object":
        return {"format": {"type": "json_object"}}

    json_schema = normalized["json_schema"]
    format_config: dict[str, Any] = {
        "type": "json_schema",
        "name": json_schema["name"],
        "schema": json_schema["schema"],
        "strict": json_schema["strict"],
    }
    if "description" in json_schema:
        format_config["description"] = json_schema["description"]
    return {"format": format_config}
