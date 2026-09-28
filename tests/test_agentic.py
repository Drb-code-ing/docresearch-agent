import asyncio
import json

import httpx
import pytest

from docresearch.agentic import AgenticSearch
from docresearch.models import Reply, ToolCall
from docresearch.provider import ProviderProtocolError
from docresearch.rerank import DashScopeReranker


def test_rewrite_rerank_and_single_retry(corpus):
    sources = list(corpus.sources.values())
    queries, events, calls = [], [], []

    class Backend:
        async def search(self, query, limit):
            queries.append(query)
            return sources[:2]

    async def ask(messages, tools, agent, purpose):
        calls.append(purpose)
        if purpose == "rewrite_queries":
            payload = {"queries": ["alternative", "alternative"]}
        else:
            second = calls.count("grade_evidence") == 2
            payload = {
                "ordered_ids": [sources[0].id],
                "sufficient": second,
                "missing": "" if second else "deployment missing",
                "retry_query": "deployment",
            }
        return Reply(calls=[ToolCall(id="1", name=purpose, arguments=json.dumps(payload))])

    search = AgenticSearch(Backend(), ask, lambda kind, agent, **data: events.append((kind, data)))
    result = asyncio.run(search.search("original", 1, "worker"))
    assert queries == ["original", "alternative", "deployment"]
    assert result["attempts"] == 2 and result["sufficient"]
    assert result["sources"][0]["id"] == sources[0].id
    assert calls == ["rewrite_queries", "grade_evidence", "grade_evidence"]


def test_unknown_grade_id_rejected(corpus):
    class Backend:
        async def search(self, query, limit):
            return []

    async def ask(messages, tools, agent, purpose):
        payload = (
            {"queries": ["q"]}
            if purpose == "rewrite_queries"
            else {"ordered_ids": ["f" * 16], "sufficient": True, "missing": "", "retry_query": ""}
        )
        return Reply(calls=[ToolCall(id="1", name=purpose, arguments=json.dumps(payload))])

    with pytest.raises(ValueError):
        asyncio.run(AgenticSearch(Backend(), ask, lambda *a, **kw: None).search("q", 1, "w"))


def test_rerank_adapter_protocol_and_independent_credentials(corpus):
    sources = list(corpus.sources.values())[:2]

    async def scenario():
        adapter = DashScopeReranker("https://rerank.example/rank", "rerank-only", "qwen3-rerank")
        await adapter.client.aclose()

        def handler(request):
            body = json.loads(request.content)
            assert request.headers["Authorization"] == "Bearer rerank-only"
            assert body["input"]["documents"] == [s.text for s in sources]
            assert body["parameters"]["top_n"] == len(sources)
            return httpx.Response(
                200,
                json={
                    "output": {
                        "results": [
                            {"index": i, "relevance_score": float(i)} for i in range(len(sources))
                        ]
                    }
                },
            )

        adapter.client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer rerank-only"}
        )
        try:
            assert await adapter.rank("q", sources) == [s.id for s in reversed(sources)]
        finally:
            await adapter.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "rows", [[{"index": 8, "relevance_score": 0.8}], [{"index": 0, "relevance_score": "NaN"}], []]
)
def test_bad_rerank_response_rejected(corpus, rows):
    async def scenario():
        adapter = DashScopeReranker("https://rerank.example/rank", "key", "model")
        await adapter.client.aclose()
        adapter.client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"output": {"results": rows}})
            )
        )
        try:
            with pytest.raises(ProviderProtocolError):
                await adapter.rank("q", list(corpus.sources.values())[:1])
        finally:
            await adapter.close()

    asyncio.run(scenario())
