"""Opt-in real services, synthetic vectors; no external LLM and no existing data changes."""

import asyncio
import os
import uuid

import pytest

from docresearch.stores import IndexMismatch, IndexNotReady, PersistentRetriever, StoreSettings
from docresearch.workspace import Corpus

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCRESEARCH_TEST_SERVICES") != "1",
    reason="Set DOCRESEARCH_TEST_SERVICES=1 for local ES/Milvus integration",
)


def test_real_services_persistence_snapshot_change_and_corruption(corpus):
    async def run():
        settings = StoreSettings(
            namespace="test_" + uuid.uuid4().hex[:12],
            analyzer="standard",
            search_analyzer="standard",
        )
        calls = []

        async def embed(texts):
            calls.append(len(texts))
            return [[1.0, 0.1] if "SQL" in text else [0.1, 1.0] for text in texts]

        first = PersistentRetriever(corpus, embed, "synthetic-v1", settings)
        second = None
        changed = None
        try:
            result = await first.ingest()
            assert result["reused"] is False
            assert calls == [3]
            await first.close()
            # New clients after closing the writer; vectors remain in the service.
            second = PersistentRetriever(corpus, embed, "synthetic-v1", settings)
            assert (await second.ingest())["reused"] is True
            assert calls == [3]
            hits = await second.search("SQL", 2)
            assert hits[0].path == "postgres.md"
            assert calls == [3, 1]
            (corpus.root / "postgres.md").unlink()
            changed = PersistentRetriever(Corpus(corpus.root), embed, "synthetic-v1", settings)
            assert changed.name != second.name
            with pytest.raises(IndexNotReady):
                await changed.prepare()
            assert calls == [3, 1]
            # Damage only this test's own index to prove that readiness alone is insufficient.
            await second.es.delete(index=second.name, id=next(iter(corpus.sources)), refresh=True)
            with pytest.raises(IndexMismatch):
                await second.prepare()
        finally:
            cleanup = second or first
            try:
                if await cleanup.es.indices.exists(index=cleanup.name):
                    await cleanup.verify_owner()
                    await cleanup.es.indices.delete(index=cleanup.name)
                if await cleanup.milvus.has_collection(cleanup.name):
                    info = await cleanup.milvus.describe_collection(cleanup.name)
                    assert info["description"] == cleanup.fingerprint
                    await cleanup.milvus.drop_collection(cleanup.name)
            finally:
                if changed:
                    await changed.close()
                await cleanup.close()

    asyncio.run(run())
