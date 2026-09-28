"""Small labelled retrieval check; it does not call a chat model or grade answers."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from pydantic import Field, TypeAdapter

from .models import Contract, ShortText
from .provider import CompatibleModel
from .retrieval import Retriever
from .stores import PersistentRetriever, StoreSettings, embedding_identity
from .workspace import Corpus, json_text


class Case(Contract):
    query: ShortText
    expected_documents: list[str] = Field(max_length=8)


def summarize(rows: list[dict]) -> dict:
    answerable = [row for row in rows if row["expected_documents"]]
    missing = [row for row in rows if not row["expected_documents"]]
    recalls = [
        len(set(row["returned_documents"]) & set(row["expected_documents"]))
        / len(set(row["expected_documents"]))
        for row in answerable
    ]
    hits = [
        bool(row["returned_documents"])
        and row["returned_documents"][0] in row["expected_documents"]
        for row in answerable
    ]
    return {
        "answerable_cases": len(answerable),
        "mean_document_recall_at_2": sum(recalls) / len(recalls) if recalls else None,
        "top_1_document_hit_rate": sum(hits) / len(hits) if hits else None,
        "no_answer_cases": len(missing),
        "no_answer_empty_result_rate": (
            sum(not row["returned_documents"] for row in missing) / len(missing)
            if missing
            else None
        ),
    }


async def evaluate(
    corpus: Corpus, cases: list[Case], embed=None, retriever_factory=Retriever
) -> dict:
    if not 1 <= len(cases) <= 40:
        raise ValueError("Use between 1 and 40 evaluation cases")
    paths = {document["path"] for document in corpus.documents}
    if any(set(case.expected_documents) - paths for case in cases):
        raise ValueError("Evaluation label refers to an unknown document")
    calls = 0

    async def measured_embed(texts):
        nonlocal calls
        calls += 1
        async with asyncio.timeout(30):
            return await embed(texts)

    retriever = retriever_factory(corpus, measured_embed if embed else None)
    started = time.monotonic()
    rows = []
    async with asyncio.timeout(180):
        await retriever.prepare()
        for case in cases:
            sources = await retriever.search(case.query, limit=2)
            rows.append(
                {
                    **case.model_dump(),
                    "returned_documents": list(dict.fromkeys(source.path for source in sources)),
                    "returned_source_ids": [source.id for source in sources],
                }
            )
    return {
        "mode": retriever.mode,
        "top_k_chunks": 2,
        "document_count": len(corpus.documents),
        "chunk_count": len(corpus.sources),
        "embedding_requests": calls,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "metrics": summarize(rows),
        "cases": rows,
    }


async def execute(args):
    cases = TypeAdapter(list[Case]).validate_python(
        json.loads(args.cases.read_text(encoding="utf-8"))
    )
    corpus = Corpus(args.corpus)
    model = CompatibleModel.from_env() if args.hybrid or args.backend == "es-milvus" else None
    store = None
    try:
        if model and not model.embedding_model:
            raise ValueError("Hybrid evaluation requires an embedding model")
        factory = Retriever
        if args.backend == "es-milvus":
            settings = StoreSettings.from_env()
            identity = embedding_identity(
                model.embedding_base_url, model.embedding_model, settings.embedding_revision
            )

            def factory(corpus, embed):
                nonlocal store
                store = PersistentRetriever(corpus, embed, identity, settings)
                return store

        return await evaluate(corpus, cases, model.embed if model else None, factory)
    finally:
        try:
            if store:
                await store.close()
        finally:
            if model:
                await model.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("examples/corpus"))
    parser.add_argument("--cases", type=Path, default=Path("examples/retrieval_cases.json"))
    parser.add_argument("--backend", choices=["memory", "es-milvus"], default="memory")
    parser.add_argument(
        "--hybrid", action="store_true", help="Send sample text to embedding service"
    )
    args = parser.parse_args()
    try:
        print(json_text(asyncio.run(execute(args))), end="")
    except Exception as error:
        print(json_text({"error": type(error).__name__}), end="")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
