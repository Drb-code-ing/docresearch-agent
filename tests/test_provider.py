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
