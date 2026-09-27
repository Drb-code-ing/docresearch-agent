import asyncio
import json

import httpx
import pytest

from docresearch.provider import CompatibleModel, ProviderProtocolError


def request_result(body, embedding=False, status=200):
    async def run():
        model = CompatibleModel(
            "https://example.test/v1", "test-key-not-real", "test-model", "embed"
        )
        await model.client.aclose()

        def handler(request):
            assert request.headers["Authorization"] == "Bearer test-key-not-real"
            data = json.loads(request.content)
            assert data["model"] in {"test-model", "embed"}
            return httpx.Response(status, json=body)

        model.client = httpx.AsyncClient(
            base_url="https://example.test/v1/",
            headers={"Authorization": "Bearer test-key-not-real"},
            transport=httpx.MockTransport(handler),
        )
        try:
            return await model.embed(["text"]) if embedding else await model.chat([], [])
        finally:
            await model.close()

    return asyncio.run(run())


def test_chat_transport_contract():
    reply = request_result(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "1",
                                "function": {"name": "search", "arguments": '{"query":"SQL"}'},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        }
    )
    assert reply.calls[0].name == "search"
    assert reply.prompt_tokens == 8


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{"message": None}]},
        {"choices": [{"message": {"tool_calls": [{}]}}]},
    ],
)
def test_malformed_chat_has_protocol_error(body):
    with pytest.raises(ProviderProtocolError):
        request_result(body)


@pytest.mark.parametrize(
    "body", [{}, {"data": None}, {"data": []}, {"data": [{"index": 2, "embedding": [1.0]}]}]
)
def test_malformed_embedding_has_protocol_error(body):
    with pytest.raises(ProviderProtocolError):
        request_result(body, embedding=True)


def test_http_error_not_protocol_error():
    with pytest.raises(httpx.HTTPStatusError):
        request_result({"error": "denied"}, status=401)


def test_embedding_transport():
    assert request_result({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}, True) == [[1.0, 0.0]]


def test_separate_embedding_config_routes_credentials_and_closes_clients(monkeypatch):
    settings = {
        "BASE_URL": "https://chat.test/v1",
        "API_KEY": "chat-test-key",
        "MODEL": "chat-model",
        "EMBEDDING_MODEL": "embed-model",
        "EMBEDDING_BASE_URL": "https://vectors.test/compatible/v1",
        "EMBEDDING_API_KEY": "embed-test-key",
        "TRUST_ENV": "false",
    }
    for key, value in settings.items():
        monkeypatch.setenv("DOCRESEARCH_" + key, value)
    clients = []
    client_options = []
    requests = []
    original_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        if request.url.host == "chat.test":
            assert request.headers["Authorization"] == "Bearer chat-test-key"
            assert request.url.path == "/v1/chat/completions"
            assert json.loads(request.content)["model"] == "chat-model"
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        assert request.url.host == "vectors.test"
        assert request.headers["Authorization"] == "Bearer embed-test-key"
        assert request.url.path == "/compatible/v1/embeddings"
        assert json.loads(request.content)["model"] == "embed-model"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    def client_factory(**kwargs):
        client_options.append(kwargs.copy())
        client = original_client(**kwargs, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    async def run():
        model = CompatibleModel.from_env()
        try:
            assert (await model.chat([], [])).content == "ok"
            assert await model.embed(["sample"]) == [[1.0, 0.0]]
        finally:
            await model.close()

    asyncio.run(run())
    assert len(requests) == len(clients) == 2
    assert all(options["trust_env"] is False for options in client_options)
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(
    "options",
    [
        {"embedding_base_url": "https://vectors.test/v1"},
        {"embedding_api_key": "embed-test-key"},
    ],
)
def test_separate_embedding_endpoint_requires_paired_credentials(options):
    with pytest.raises(ValueError, match="together"):
        CompatibleModel("https://chat.test/v1", "chat-test-key", "chat", "embed", **options)


def test_invalid_trust_env_rejected(monkeypatch):
    monkeypatch.setenv("DOCRESEARCH_TRUST_ENV", "maybe")
    with pytest.raises(ValueError, match="true or false"):
        CompatibleModel.from_env()
