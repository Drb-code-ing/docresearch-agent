"""Offline learning walkthrough using the real project objects, not an API."""

import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from docresearch.models import Search
from docresearch.provider import DemoModel
from docresearch.retrieval import Retriever, normalized, tokenize
from docresearch.runtime import ResearchRun
from docresearch.workspace import Corpus


def show(label, value):
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2))


async def main():
    corpus = Corpus(Path("examples/corpus"))
    source = next(source for source in corpus.sources.values() if source.path == "pgvector.md")
    show("1. File becomes a Source snapshot", source.payload())

    query = "PostgreSQL 全文检索"
    retriever = Retriever(corpus)
    await retriever.prepare()
    hits = await retriever.search(query, limit=2)
    show(
        "2. Query tokens and actual BM25 results",
        {
            "query": query,
            "tokens": tokenize(query),
            "hits": [{"id": hit.id, "path": hit.path} for hit in hits],
        },
    )

    vectors = normalized([[1, 0], [0.9, 0.1], [0.2, 0.8]], 3)
    show(
        "3. Toy vectors, NOT provider embeddings",
        {
            "cosine_q_pg": round(float(vectors[0] @ vectors[1]), 3),
            "cosine_q_milvus": round(float(vectors[0] @ vectors[2]), 3),
            "rrf_two_rankings": 1 / 61 + 1 / 63,
            "rrf_one_ranking": 1 / 61,
        },
    )

    raw_arguments = '{"query":"Milvus","limit":2}'
    show(
        "4. Tool JSON becomes validated arguments",
        Search.model_validate_json(raw_arguments).model_dump(),
    )
    try:
        Search.model_validate_json('{"query":"Milvus","limit":"2","path":"../secret"}')
    except ValidationError:
        show("4b. Wrong type and extra field", "ValidationError (expected)")

    run = ResearchRun(corpus, Path("reports"), DemoModel(), mode="deterministic-demo")
    outcome = await run.run("比较 pgvector 与 Milvus 的小型知识库适用性")
    show("5. Real runtime with deterministic model", outcome.metadata)
    show(
        "5b. Follow the control flow",
        [
            event
            for event in run.trace
            if event["event"] in {"child_start", "tool_start", "finalized"}
        ],
    )
    show("5c. Inspect these four files", str(outcome.directory))


if __name__ == "__main__":
    asyncio.run(main())
