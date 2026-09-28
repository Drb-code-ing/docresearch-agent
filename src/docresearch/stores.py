"""Persistent Elasticsearch BM25 and Milvus HNSW retrieval over immutable snapshots."""

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass, field

from elasticsearch import AsyncElasticsearch, NotFoundError
from pymilvus import AsyncMilvusClient, DataType, MilvusClient

from .retrieval import Embed, normalized, reciprocal_ranks
from .workspace import Corpus, Source


class IndexNotReady(Exception):
    """Run ingest for this corpus/model/analyzer snapshot before researching it."""


class IndexMismatch(Exception):
    """The stored snapshot is incomplete, incompatible, or has unexpected content."""


@dataclass(frozen=True)
class StoreSettings:
    es_url: str = "http://localhost:9200"
    milvus_uri: str = "http://localhost:19530"
    namespace: str = "docs"
    analyzer: str = "ik_max_word"
    search_analyzer: str = "ik_smart"
    embedding_revision: str = "1"
    es_api_key: str = field(default="", repr=False)
    milvus_token: str = field(default="", repr=False)

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", self.namespace):
            raise ValueError("Use a lowercase namespace with at most 24 characters")
        if (self.analyzer, self.search_analyzer) not in {
            ("ik_max_word", "ik_smart"),
            ("standard", "standard"),
            ("cjk", "cjk"),
        }:
            raise ValueError("Use an IK pair, standard pair or cjk pair")

    @classmethod
    def from_env(cls):
        names = {
            "es_url": "ES_URL",
            "milvus_uri": "MILVUS_URI",
            "namespace": "NAMESPACE",
            "analyzer": "ES_ANALYZER",
            "search_analyzer": "ES_SEARCH_ANALYZER",
            "embedding_revision": "EMBEDDING_REVISION",
            "es_api_key": "ES_API_KEY",
            "milvus_token": "MILVUS_TOKEN",
        }
        return cls(
            **{
                key: os.environ["DOCRESEARCH_" + value]
                for key, value in names.items()
                if "DOCRESEARCH_" + value in os.environ
            }
        )


def embedding_identity(base_url: str, model: str, revision: str) -> str:
    # Hash identity, never credentials or endpoint details, into public metadata.
    return hashlib.sha256(json.dumps([base_url.rstrip("/"), model, revision]).encode()).hexdigest()


class PersistentRetriever:
    mode = "es-milvus-rrf"

    def __init__(
        self,
        corpus: Corpus,
        embed: Embed,
        identity: str,
        settings: StoreSettings,
        *,
        es=None,
        milvus=None,
    ):
        self.corpus, self.embed, self.settings = corpus, embed, settings
        content = json.dumps(
            [
                "docresearch-v1",
                sorted(corpus.sources),
                identity,
                settings.analyzer,
                settings.search_analyzer,
            ]
        )
        self.fingerprint = hashlib.sha256(content.encode()).hexdigest()
        self.name = f"docresearch_{settings.namespace}_{self.fingerprint[:24]}"
        self.owner = {"owner": "docresearch", "schema": 1, "fingerprint": self.fingerprint}
        self.es = es or AsyncElasticsearch(
            settings.es_url, api_key=settings.es_api_key or None, request_timeout=15, max_retries=0
        )
        self.milvus = milvus or AsyncMilvusClient(
            uri=settings.milvus_uri, token=settings.milvus_token, timeout=15
        )
        self.dimension: int | None = None

    def mapping(self):
        return {
            "dynamic": "strict",
            "_meta": self.owner,
            "properties": {
                "kind": {"type": "keyword"},
                "id": {"type": "keyword"},
                "path": {"type": "keyword"},
                "version": {"type": "keyword"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "text": {
                    "type": "text",
                    "analyzer": self.settings.analyzer,
                    "search_analyzer": self.settings.search_analyzer,
                    "similarity": "BM25",
                },
                "fingerprint": {"type": "keyword"},
                "dimension": {"type": "integer"},
                "source_count": {"type": "integer"},
            },
        }

    async def manifest(self):
        try:
            return (await self.es.get(index=self.name, id="manifest"))["_source"]
        except NotFoundError:
            return None

    async def verify_owner(self):
        mapping = await self.es.indices.get_mapping(index=self.name)
        if mapping[self.name]["mappings"].get("_meta") != self.owner:
            raise IndexMismatch("Unexpected Elasticsearch index owner")

    async def verify_rows(self, dimension: int):
        await self.verify_owner()
        description = await self.milvus.describe_collection(self.name)
        vector = next((f for f in description["fields"] if f["name"] == "vector"), {})
        if (
            description.get("description") != self.fingerprint
            or int(vector.get("params", {}).get("dim", 0)) != dimension
        ):
            raise IndexMismatch("Unexpected Milvus schema")
        await self.milvus.load_collection(self.name, timeout=30)
        es_rows = await self.es.search(
            index=self.name, size=len(self.corpus.sources) + 1, query={"term": {"kind": "source"}}
        )
        stored = {hit["_id"]: hit["_source"] for hit in es_rows["hits"]["hits"]}
        expected = {
            key: {"kind": "source", **source.payload()}
            for key, source in self.corpus.sources.items()
        }
        milvus_rows = await self.milvus.query(
            self.name,
            filter="",
            output_fields=["id"],
            limit=len(expected) + 1,
            consistency_level="Strong",
        )
        if stored != expected or {row["id"] for row in milvus_rows} != set(expected):
            raise IndexMismatch("Stored source identities do not match the corpus")

    async def prepare(self):
        manifest = await self.manifest()
        if manifest is None or not await self.milvus.has_collection(self.name):
            raise IndexNotReady("Run docresearch ingest for this snapshot first")
        if (
            manifest.get("fingerprint") != self.fingerprint
            or manifest.get("source_count") != len(self.corpus.sources)
            or not isinstance(manifest.get("dimension"), int)
            or manifest["dimension"] <= 0
        ):
            raise IndexMismatch("Invalid ready manifest")
        await self.verify_rows(manifest["dimension"])
        self.dimension = manifest["dimension"]

    async def ingest(self):
        if await self.manifest() is not None:
            await self.prepare()
            return self.summary(reused=True)
        if await self.es.indices.exists(index=self.name):
            await self.verify_owner()
        else:
            # These probes fail early when IK is missing, before paying for embeddings.
            for analyzer in {self.settings.analyzer, self.settings.search_analyzer}:
                await self.es.indices.analyze(analyzer=analyzer, text="文档检索")
            await self.es.indices.create(
                index=self.name,
                mappings=self.mapping(),
                settings={"number_of_shards": 1, "number_of_replicas": 0},
            )
        items = list(self.corpus.sources.values())
        vectors = []
        for offset in range(0, len(items), 32):
            batch = items[offset : offset + 32]
            values = normalized(
                await self.embed([source.text for source in batch]),
                len(batch),
                len(vectors[0]) if vectors else None,
            )
            vectors.extend(values.tolist())
        dimension = len(vectors[0])
        if not await self.milvus.has_collection(self.name):
            schema = MilvusClient.create_schema(
                auto_id=False, enable_dynamic_field=False, description=self.fingerprint
            )
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=16)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dimension)
            indexes = MilvusClient.prepare_index_params()
            indexes.add_index(
                field_name="vector",
                index_type="HNSW",
                metric_type="COSINE",
                params={"M": 16, "efConstruction": 128},
            )
            await self.milvus.create_collection(
                self.name,
                schema=schema,
                index_params=indexes,
                consistency_level="Strong",
                timeout=60,
            )
        else:
            description = await self.milvus.describe_collection(self.name)
            if description.get("description") != self.fingerprint:
                raise IndexMismatch("Unexpected Milvus collection owner")
        operations = []
        for source in items:
            operations.extend(
                [{"index": {"_id": source.id}}, {"kind": "source", **source.payload()}]
            )
        bulk = await self.es.bulk(index=self.name, operations=operations, refresh="wait_for")
        if bulk["errors"]:
            raise IndexMismatch("Elasticsearch bulk write was incomplete")
        for offset in range(0, len(items), 32):
            await self.milvus.upsert(
                self.name,
                data=[
                    {"id": items[i].id, "vector": vectors[i]}
                    for i in range(offset, min(offset + 32, len(items)))
                ],
            )
        await self.milvus.flush(self.name, timeout=60)
        await self.verify_rows(dimension)
        # Publish readiness only after both stores have the same complete source set.
        await self.es.index(
            index=self.name,
            id="manifest",
            refresh="wait_for",
            document={
                "kind": "manifest",
                "fingerprint": self.fingerprint,
                "dimension": dimension,
                "source_count": len(items),
            },
        )
        self.dimension = dimension
        return self.summary(reused=False)

    def summary(self, reused: bool):
        return {
            "retrieval": self.mode,
            "snapshot": self.name,
            "dimension": self.dimension,
            "sources": len(self.corpus.sources),
            "reused": reused,
        }

    async def search(self, query: str, limit: int = 5) -> list[Source]:
        if self.dimension is None:
            raise IndexNotReady("Call prepare first")
        if not query.strip():
            return []

        async def lexical():
            response = await self.es.search(
                index=self.name,
                size=20,
                query={
                    "bool": {
                        "filter": [{"term": {"kind": "source"}}],
                        "must": [{"match": {"text": {"query": query}}}],
                    }
                },
                sort=[{"_score": "desc"}, {"id": "asc"}],
                source=False,
            )
            return [hit["_id"] for hit in response["hits"]["hits"]]

        async def dense():
            vector = normalized(await self.embed([query]), 1, self.dimension)[0].tolist()
            response = await self.milvus.search(
                self.name,
                data=[vector],
                anns_field="vector",
                limit=20,
                search_params={"metric_type": "COSINE", "params": {"ef": 64}},
                consistency_level="Strong",
            )
            return [str(hit["id"]) for hit in response[0] if hit["distance"] > 0]

        tasks = [asyncio.create_task(lexical()), asyncio.create_task(dense())]
        try:
            rankings = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if any(key not in self.corpus.sources for ranking in rankings for key in ranking):
            raise IndexMismatch("Search returned an unknown source")
        return [self.corpus.read(key) for key in reciprocal_ranks(rankings, limit)]

    async def close(self):
        try:
            await self.es.close()
        finally:
            await self.milvus.close()
