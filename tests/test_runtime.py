import asyncio
import json

import pytest

from docresearch.models import Finding, Limits, Plan, Reply, ResearchResult, ToolCall
from docresearch.provider import DemoModel
from docresearch.runtime import AgentState, Budget, BudgetExceeded, ResearchRun


def call(name, args, key="1"):
    return ToolCall(id=key, name=name, arguments=json.dumps(args))


class ConstantModel:
    def __init__(self, reply):
        self.reply = reply

    async def chat(self, messages, tools):
        return self.reply


def test_demo_end_to_end(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel(), mode="deterministic-demo")
    result = asyncio.run(run.run("compare"))
    assert result.status == "partial"
    assert result.metadata["tasks"] == 2
    assert result.metadata["peak_child_concurrency"] <= 2
    assert result.metadata["model_calls_including_embeddings"] == 13
    sources = json.loads((result.directory / "sources.json").read_text(encoding="utf-8"))
    assert sources
    report = (result.directory / "report.md").read_text(encoding="utf-8")
    assert "deterministic-demo" in report
    assert all(source["id"] in report for source in sources)
    assert {p.name for p in result.directory.iterdir()} == {
        "report.md",
        "sources.json",
        "trace.json",
        "run.json",
        "tasks.json",
    }
    with pytest.raises(ValueError):
        asyncio.run(run.run("again"))


@pytest.mark.parametrize("tool", ["task", "save_report", "bash", "plan"])
def test_child_cannot_delegate_or_publish(corpus, tmp_path, tool):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel())
    child = AgentState("child", False)
    assert asyncio.run(run.dispatch(call(tool, {}), child)) == {"error": "tool_not_allowed"}


def test_schema_rejects_extra_or_wrong_type(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel())
    state = AgentState("child", False)
    for args in ({"query": "x", "limit": "5"}, {"query": "x", "path": "../secret"}):
        result = asyncio.run(run.dispatch(call("search", args), state))
        assert result["error"] == "invalid_arguments_or_source"


def test_citation_must_be_seen(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel())
    key = next(iter(corpus.sources))
    result = ResearchResult(findings=[Finding(statement="claim", source_ids=[key])])
    with pytest.raises(ValueError):
        run.validate_evidence(result, AgentState("child", False))
    run.validate_evidence(result, AgentState("child", False, seen={key}))


def test_search_limit(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel())
    state = AgentState("child", False)
    for _ in range(3):
        assert "sources" in asyncio.run(run.dispatch(call("search", {"query": "SQL"}), state))
    assert (
        asyncio.run(run.dispatch(call("search", {"query": "SQL"}), state))["error"]
        == "search_limit"
    )


def test_shared_budget_never_overshoots():
    async def scenario():
        budget = Budget(Limits(max_calls=2))

        async def work():
            await asyncio.sleep(0)
            return 1

        results = await asyncio.gather(
            *(budget.invoke(work) for _ in range(4)), return_exceptions=True
        )
        assert budget.calls == 2
        assert sum(isinstance(r, BudgetExceeded) for r in results) == 2

    asyncio.run(scenario())


def test_budget_exhaustion_leaves_diagnostics_not_report(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel(), Limits(max_calls=1))
    result = asyncio.run(run.run("compare"))
    assert result.status == "budget_exhausted"
    assert result.metadata["model_calls_including_embeddings"] == 1
    assert run.active_children == 0
    assert not (result.directory / "report.md").exists()


def test_step_limit_and_bad_final_result(corpus, tmp_path):
    model = ConstantModel(
        Reply(calls=[call("save_report", {"title": "x", "findings": [], "gaps": []})])
    )
    result = asyncio.run(
        ResearchRun(corpus, tmp_path / "out", model, Limits(parent_steps=2)).run("q")
    )
    assert result.status == "failed"
    assert result.metadata["error"] == "StepLimit"


@pytest.mark.parametrize("timeout_type", ["request", "run"])
def test_timeout_cancels_children(corpus, tmp_path, timeout_type):
    class SlowChildren(DemoModel):
        async def chat(self, messages, tools):
            if not any(t["function"]["name"] == "task" for t in tools):
                await asyncio.sleep(10)
            return await super().chat(messages, tools)

    limits = Limits(
        request_timeout=0.01 if timeout_type == "request" else 20.0,
        run_timeout=0.03 if timeout_type == "run" else 20.0,
    )
    run = ResearchRun(corpus, tmp_path / "out", SlowChildren(), limits)
    outcome = asyncio.run(run.run("compare"))
    assert outcome.status in {"partial", "timeout"}
    assert run.active_children == 0
    assert outcome.metadata["elapsed_ms"] < 1000


def test_child_context_and_evidence_return(corpus, tmp_path):
    messages_seen = []

    class RecordingDemo(DemoModel):
        async def chat(self, messages, tools):
            messages_seen.append(json.loads(json.dumps(messages)))
            return await super().chat(messages, tools)

    run = ResearchRun(corpus, tmp_path / "out", RecordingDemo())
    parent = AgentState("parent", True)
    run.coordinator.plan(Plan.model_validate({"tasks": [{"task_id": "sql", "question": "SQL"}]}))
    output = asyncio.run(run.child("sql", parent))
    assert len(messages_seen[0]) == 2
    assert messages_seen[0][1]["content"] == "SQL"
    assert output["findings"]
    assert "sources" not in output
    assert not parent.seen


def test_tool_budget_and_concurrency_one(corpus, tmp_path):
    run = ResearchRun(corpus, tmp_path / "out", DemoModel(), Limits(concurrency=1, max_tools=2))
    outcome = asyncio.run(run.run("compare"))
    assert outcome.status == "budget_exhausted"
    assert outcome.metadata["tool_calls"] == 2
    assert outcome.metadata["peak_child_concurrency"] <= 1


def test_duplicate_tool_ids_rejected(corpus, tmp_path):
    model = ConstantModel(Reply(calls=[call("list_documents", {}), call("list_documents", {})]))
    outcome = asyncio.run(ResearchRun(corpus, tmp_path / "out", model).run("q"))
    assert outcome.status == "failed"
    assert outcome.metadata["error"] == "ValueError"
