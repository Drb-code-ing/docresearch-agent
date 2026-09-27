"""CLI entry point; all network access is opt-in through the run command."""

import argparse
import asyncio
import json
from pathlib import Path

from .models import Limits
from .provider import CompatibleModel, DemoModel
from .runtime import ResearchRun
from .workspace import Corpus


async def execute(args: argparse.Namespace) -> int:
    corpus = Corpus(args.corpus)
    limits = Limits(max_calls=args.max_calls, run_timeout=float(args.timeout))
    live = args.command == "run"
    model = CompatibleModel.from_env() if live else DemoModel()
    embed = model.embed if live and model.embedding_model else None
    question = args.question if live else "比较 pgvector 与 Milvus 的小型知识库适用性"
    try:
        outcome = await ResearchRun(
            corpus, args.output, model, limits, embed, "live" if live else "deterministic-demo"
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
        if live:
            await model.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Research local Markdown/TXT documents")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("demo", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("--corpus", type=Path, default=Path("examples/corpus"))
        sub.add_argument("--output", type=Path, default=Path("reports"))
        sub.add_argument("--max-calls", type=int, default=24)
        sub.add_argument("--timeout", type=float, default=180)
        if command == "run":
            sub.add_argument("question")
    args = parser.parse_args()
    try:
        code = asyncio.run(execute(args))
    except KeyboardInterrupt:
        code = 130
        print("Cancelled. No final report is guaranteed on external interruption.")
    except Exception as error:
        # Never echo provider bodies, credentials, source text or raw validation inputs.
        code = 1
        print(f"Configuration or output error: {type(error).__name__}. See README for constraints.")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
