"""CLI entry point; all network access is opt-in through the run command."""

import argparse
import asyncio
import json
from pathlib import Path

from .models import Limits
from .provider import CompatibleModel, DemoModel
from .rerank import DashScopeReranker
from .retrieval import Retriever
from .runtime import Budget, ResearchRun
from .stores import PersistentRetriever, StoreSettings, embedding_identity
from .workspace import Corpus


async def execute(args: argparse.Namespace) -> int:
    corpus = Corpus(args.corpus)
    limits = Limits(max_calls=args.max_calls, run_timeout=float(args.timeout))
    live = args.command != "demo"
    model = CompatibleModel.from_env() if live else DemoModel()
    embed = model.embed if live and model.embedding_model else None
    persistent = args.command == "ingest" or (live and args.backend == "es-milvus")
    store = None
    reranker = None
    try:
        reranker = DashScopeReranker.from_env() if args.command == "run" else None
        factory = Retriever
        if persistent:
            if embed is None:
                raise ValueError("Elasticsearch/Milvus requires an embedding model")
            settings = StoreSettings.from_env()
            identity = embedding_identity(
                model.embedding_base_url, model.embedding_model, settings.embedding_revision
            )

            def factory(corpus, metered_embed):
                nonlocal store
                store = PersistentRetriever(corpus, metered_embed, identity, settings)
                return store

        if args.command == "ingest":
            budget = Budget(limits)

            async def metered_embed(texts):
                return await budget.invoke(lambda: model.embed(texts))

            store = factory(corpus, metered_embed)
            async with asyncio.timeout(limits.run_timeout):
                result = await store.ingest()
            print(
                json.dumps(
                    {**result, "embedding_requests": budget.calls}, ensure_ascii=False, indent=2
                )
            )
            return 0
        question = args.question if live else "比较 pgvector 与 Milvus 的小型知识库适用性"
        outcome = await ResearchRun(
            corpus,
            args.output,
            model,
            limits,
            embed,
            "live" if live else "deterministic-demo",
            retriever_factory=factory,
            agentic=True,
            reranker=reranker,
        ).run(question)
        print(
            json.dumps(
                {
                    "status": outcome.status,
                    "directory": str(outcome.directory),
                    "metadata": outcome.metadata,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if outcome.status in {"completed", "partial"} else 1
    finally:
        try:
            if store is not None:
                await store.close()
        finally:
            try:
                if reranker is not None:
                    await reranker.close()
            finally:
                if live:
                    await model.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Research local Markdown/TXT documents")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("demo", "run", "ingest"):
        sub = commands.add_parser(command)
        sub.add_argument("--corpus", type=Path, default=Path("examples/corpus"))
        sub.add_argument("--output", type=Path, default=Path("reports"))
        sub.add_argument("--max-calls", type=int, default=48)
        sub.add_argument("--timeout", type=float, default=180)
        if command == "run":
            sub.add_argument("question")
            sub.add_argument("--backend", choices=["es-milvus", "memory"], default="es-milvus")
    args = parser.parse_args()
    try:
        code = asyncio.run(execute(args))
    except KeyboardInterrupt:
        code = 130
        print("Cancelled. No final report is guaranteed on external interruption.")
    except Exception as error:
        # Never echo provider bodies, credentials, source text or raw validation inputs.
        code = 1
        print(
            f"Configuration, index or output error: {type(error).__name__}. See README for constraints."
        )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
