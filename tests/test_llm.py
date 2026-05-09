from types import SimpleNamespace
import time

import pytest

from contextus.llm import CerebrasClient, LLMClient, LLMResponse, OpenAIResponsesClient


class SlowLLM(LLMClient):
    def __init__(self, delay: float = 0.15) -> None:
        self.delay = delay

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        time.sleep(self.delay)
        return LLMResponse(content=user)


class FakeFallbackLLM(LLMClient):
    def __init__(self, content: str = "openai worked") -> None:
        self.content = content
        self.calls = []

    def complete(self, system: str, user: str, temperature: float = 0.0, **kwargs):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "temperature": temperature,
                **kwargs,
            }
        )
        return LLMResponse(content=self.content, raw={"provider": "fake_openai"})


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def make_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_llm_client_submit_runs_independent_calls_concurrently():
    llm = SlowLLM(delay=0.2)

    started = time.perf_counter()
    futures = [
        llm.submit(system="sys", user="first"),
        llm.submit(system="sys", user="second"),
    ]
    responses = [future.result(timeout=2) for future in futures]
    elapsed = time.perf_counter() - started

    assert [response.content for response in responses] == ["first", "second"]
    assert elapsed < 0.35


def make_client(
    responses,
    *,
    model="gpt-oss-120b",
    fallback_models=("llama3.1-8b",),
    openai_fallback=None,
    enable_openai_fallback=False,
):
    client = object.__new__(CerebrasClient)
    client._client = FakeClient(responses)
    client._model = model
    client._fallback_models = tuple(fallback_models)
    client._openai_fallback = openai_fallback
    client._enable_openai_fallback = enable_openai_fallback
    return client


def test_cerebras_client_falls_back_when_primary_model_is_unavailable():
    client = make_client(
        [
            Exception("404 model_not_found: gpt-oss-120b does not exist or you do not have access to it."),
            make_response("fallback worked"),
        ]
    )

    response = client.complete(system="sys", user="user")

    assert isinstance(response, LLMResponse)
    assert response.content == "fallback worked"
    assert client._model == "llama3.1-8b"
    assert [call["model"] for call in client._client.chat.completions.calls] == ["gpt-oss-120b", "llama3.1-8b"]


def test_cerebras_client_does_not_fallback_on_non_model_error():
    client = make_client([Exception("Connection error")])

    with pytest.raises(Exception, match="Connection error"):
        client.complete(system="sys", user="user")

    assert [call["model"] for call in client._client.chat.completions.calls] == ["gpt-oss-120b"]


def test_cerebras_client_auto_falls_back_to_openai_on_provider_quota_error():
    fallback = FakeFallbackLLM(content="openai backup")
    client = make_client(
        [
            Exception(
                "429 token_quota_exceeded: Tokens per day limit exceeded - too many tokens processed."
            )
        ],
        openai_fallback=fallback,
        enable_openai_fallback=True,
    )
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }

    response = client.complete(system="sys", user="user", response_format=schema)

    assert response.content == "openai backup"
    assert response.raw["provider"] == "openai_fallback"
    assert "token_quota_exceeded" in response.raw["original_error"]
    assert fallback.calls == [
        {
            "system": "sys",
            "user": "user",
            "temperature": 0.0,
            "response_format": schema,
        }
    ]
    assert [call["model"] for call in client._client.chat.completions.calls] == ["gpt-oss-120b"]


def test_candidate_models_preserve_primary_then_fallbacks():
    client = make_client([make_response("ok")], model="custom-model", fallback_models=("llama3.1-8b", "qwen-3-32b"))

    assert client._candidate_models() == ("custom-model", "llama3.1-8b", "qwen-3-32b")


def test_cerebras_client_passes_structured_response_format():
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": ["continue", "split"]}},
        "required": ["decision"],
        "additionalProperties": False,
    }
    client = make_client([make_response('{"decision":"continue"}')])

    client.complete(
        system="sys",
        user="user",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "boundary_decision",
                "strict": True,
                "schema": schema,
            },
        },
    )

    assert client._client.chat.completions.calls[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "boundary_decision",
            "strict": True,
            "schema": schema,
        },
    }


def test_cerebras_client_wraps_raw_json_schema_response_format():
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    client = make_client([make_response('{"ok":true}')])

    client.complete(system="sys", user="user", response_format=schema)

    assert client._client.chat.completions.calls[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "response_schema",
            "strict": True,
            "schema": schema,
        },
    }


def test_openai_responses_client_extracts_output_text():
    client = object.__new__(OpenAIResponsesClient)

    text = client._extract_text({"output_text": "vision worked"})

    assert text == "vision worked"


def test_openai_responses_client_extracts_message_content_text():
    client = object.__new__(OpenAIResponsesClient)

    text = client._extract_text(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "json result"}],
                }
            ]
        }
    )

    assert text == "json result"


class FakeOpenAIResponse:
    def __init__(self, payload):
        self._payload = payload
        self.output_text = payload.get("output_text")

    def model_dump(self):
        return self._payload


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


def make_openai_client(response):
    client = object.__new__(OpenAIResponsesClient)
    client._client = FakeOpenAIClient(response)
    client._model = "gpt-5-nano"
    client._reasoning_effort = "minimal"
    client._verbosity = "low"
    client._max_output_tokens = 800
    return client


def test_openai_responses_client_passes_structured_text_format():
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
        "additionalProperties": False,
    }
    client = make_openai_client({"output_text": '{"decision":"split"}'})

    response = client.complete(
        system="sys",
        user="user",
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "boundary_decision",
                "strict": True,
                "schema": schema,
            },
        },
    )

    assert response.content == '{"decision":"split"}'
    assert client._client.responses.calls[0]["reasoning"] == {"effort": "minimal"}
    assert client._client.responses.calls[0]["max_output_tokens"] == 800
    assert client._client.responses.calls[0]["text"] == {
        "verbosity": "low",
        "format": {
            "type": "json_schema",
            "name": "boundary_decision",
            "strict": True,
            "schema": schema,
        }
    }


def test_openai_responses_client_extracts_sdk_like_response_objects():
    client = object.__new__(OpenAIResponsesClient)

    text = client._extract_text(
        FakeOpenAIResponse(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "sdk result"}],
                    }
                ]
            }
        )
    )

    assert text == "sdk result"
