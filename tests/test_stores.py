import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from elasticsearch import NotFoundError

from docresearch.stores import (
    IndexMismatch,
    IndexNotReady,
    PersistentRetriever,
    StoreSettings,
    embedding_identity,
)
from docresearch.workspace import Corpus


def missing():
    return NotFoundError("missing", meta=SimpleNamespace(status=404), body={})


def store_fixture(corpus, ready=True):
    es = SimpleNamespace(
        get=AsyncMock(),
        search=AsyncMock(),
        index=AsyncMock(),
        bulk=AsyncMock(),
        close=AsyncMock(),
        indices=SimpleNamespace(
            get_mapping=AsyncMock(),
            exists=AsyncMock(return_value=True),
            analyze=AsyncMock(),
            create=AsyncMock(),
        ),
    )
    milvus = SimpleNamespace(
        has_collection=AsyncMock(return_value=True),
        describe_collection=AsyncMock(),
        load_collection=AsyncMock(),
        query=AsyncMock(),
        search=AsyncMock(),
        upsert=AsyncMock(),
        flush=AsyncMock(),
        create_collection=AsyncMock(),
        close=AsyncMock(),
    )
    embed = AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
    store = PersistentRetriever(corpus, embed, "test-model", StoreSettings(), es=es, milvus=milvus)
    es.indices.get_mapping.return_value = {store.name: {"mappings": {"_meta": store.owner}}}
    es.get.return_value = {
        "_source": {
            "kind": "manifest",
            "fingerprint": store.fingerprint,
            "source_count": len(corpus.sources),
            "dimension": 2,
        }
    }
    if not ready:
        es.get.side_effect = missing()
    es.search.return_value = {
        "hits": {
            "hits": [
                {"_id": s.id, "_source": {"kind": "source", **s.payload()}}
                for s in corpus.sources.values()
            ]
        }
    }
    milvus.describe_collection.return_value = {
        "description": store.fingerprint,
        "fields": [{"name": "vector", "params": {"dim": 2}}],
    }
    milvus.query.return_value = [{"id": key} for key in corpus.sources]
    es.bulk.return_value = {"errors": False}
    return store


def test_existing_snapshot_reuses_without_embedding_or_writes(corpus):
    store = store_fixture(corpus)
    result = asyncio.run(store.ingest())
    assert result["reused"] is True
    assert store.dimension == 2
    store.embed.assert_not_awaited()
    store.es.bulk.assert_not_awaited()
    store.milvus.upsert.assert_not_awaited()
    store.es.index.assert_not_awaited()


def test_prepare_requires_both_stores_and_ready_marker(corpus):
    store = store_fixture(corpus, ready=False)
    with pytest.raises(IndexNotReady):
        asyncio.run(store.prepare())
    store.embed.assert_not_awaited()
    store = store_fixture(corpus)
    store.milvus.has_collection.return_value = False
    with pytest.raises(IndexNotReady):
        asyncio.run(store.prepare())


@pytest.mark.parametrize("broken", ["es_source", "milvus_ids", "dimension", "owner"])
def test_prepare_rejects_inconsistent_stores(corpus, broken):
    store = store_fixture(corpus)
    if broken == "es_source":
        store.es.search.return_value["hits"]["hits"][0]["_source"]["text"] = "changed"
    elif broken == "milvus_ids":
        store.milvus.query.return_value.pop()
    elif broken == "dimension":
        store.milvus.describe_collection.return_value["fields"][0]["params"]["dim"] = 9
    else:
        store.es.indices.get_mapping.return_value[store.name]["mappings"]["_meta"] = {}
    with pytest.raises(IndexMismatch):
        asyncio.run(store.prepare())


def test_failed_dual_write_never_publishes_ready_marker(corpus):
    store = store_fixture(corpus, ready=False)
    store.milvus.upsert.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        asyncio.run(store.ingest())
    store.es.bulk.assert_awaited_once()
    store.es.index.assert_not_awaited()


def test_partial_bulk_never_writes_vectors_or_publishes(corpus):
    store = store_fixture(corpus, ready=False)
    store.es.bulk.return_value = {"errors": True}
    with pytest.raises(IndexMismatch):
        asyncio.run(store.ingest())
    store.milvus.upsert.assert_not_awaited()
    store.es.index.assert_not_awaited()


def test_ingest_order_is_write_verify_publish(corpus):
    store = store_fixture(corpus, ready=False)
    order = []

    async def flush(*args, **kwargs):
        order.append("flush")

    async def verify(*args):
        order.append("verify")

    async def publish(*args, **kwargs):
        order.append("publish")

    store.milvus.flush.side_effect = flush
    store.verify_rows = verify
    store.es.index.side_effect = publish
    result = asyncio.run(store.ingest())
    assert order == ["flush", "verify", "publish"]
    assert result["reused"] is False


def test_corpus_model_and_analyzer_changes_select_new_snapshot(corpus):
    store = store_fixture(corpus)
    settings = StoreSettings(analyzer="standard", search_analyzer="standard")
    changed_analyzer = PersistentRetriever(
        corpus, store.embed, "test-model", settings, es=store.es, milvus=store.milvus
    )
    changed_model = PersistentRetriever(
        corpus, store.embed, "new-model", StoreSettings(), es=store.es, milvus=store.milvus
    )
    (corpus.root / "postgres.md").unlink()
    changed_corpus = store_fixture(Corpus(corpus.root))
    assert len({store.name, changed_analyzer.name, changed_model.name, changed_corpus.name}) == 4
    assert embedding_identity("http://test/v1", "e", "1") != embedding_identity(
        "http://test/v1", "e", "2"
    )


def test_search_uses_both_services_rrf_and_original_sources(corpus):
    store = store_fixture(corpus)
    store.dimension = 2
    a, b, c = list(corpus.sources)
    store.es.search.return_value = {"hits": {"hits": [{"_id": a}, {"_id": b}]}}
    store.milvus.search.return_value = [[{"id": b, "distance": 0.8}, {"id": c, "distance": 0.7}]]
    sources = asyncio.run(store.search("semantic question", 2))
    assert sources == [corpus.read(b), corpus.read(a)]
    assert store.es.search.call_args.kwargs["query"]["bool"]["must"][0] == {
        "match": {"text": {"query": "semantic question"}}
    }
    assert store.milvus.search.call_args.kwargs["search_params"]["metric_type"] == "COSINE"


def test_search_rejects_foreign_ids(corpus):
    store = store_fixture(corpus)
    store.dimension = 2
    store.es.search.return_value = {"hits": {"hits": [{"_id": "foreign"}]}}
    store.milvus.search.return_value = [[]]
    with pytest.raises(IndexMismatch):
        asyncio.run(store.search("question"))


def test_failed_channel_cancels_sibling_instead_of_silent_fallback(corpus):
    store = store_fixture(corpus)
    store.dimension = 2
    cancelled = []

    async def slow_embed(texts):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.append(True)

    async def fail_search(**kwargs):
        await asyncio.sleep(0.01)
        raise ConnectionError("unavailable")

    store.embed = slow_embed
    store.es.search.side_effect = fail_search
    with pytest.raises(ConnectionError):
        asyncio.run(store.search("question"))
    assert cancelled == [True]


def test_close_cleans_both_clients(corpus):
    store = store_fixture(corpus)
    store.es.close.side_effect = RuntimeError("close error")
    with pytest.raises(RuntimeError):
        asyncio.run(store.close())
    store.milvus.close.assert_awaited_once()
