from types import SimpleNamespace

import pytest

from contextus.llm import CerebrasClient, LLMResponse


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, *, model, temperature, messages):
        self.calls.append({"model": model, "temperature": temperature, "messages": messages})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def make_response(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def make_client(responses, *, model="gpt-oss-120b", fallback_models=("llama3.1-8b",)):
    client = object.__new__(CerebrasClient)
    client._client = FakeClient(responses)
    client._model = model
    client._fallback_models = tuple(fallback_models)
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


def test_candidate_models_preserve_primary_then_fallbacks():
    client = make_client([make_response("ok")], model="custom-model", fallback_models=("llama3.1-8b", "qwen-3-32b"))

    assert client._candidate_models() == ("custom-model", "llama3.1-8b", "qwen-3-32b")
