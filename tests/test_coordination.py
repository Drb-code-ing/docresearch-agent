import asyncio
import json

import pytest
from test_runtime import call

from docresearch.coordination import Coordinator
from docresearch.models import Finding, Limits, Plan, Reply, ResearchResult, SaveReport
from docresearch.provider import DemoModel
from docresearch.runtime import ResearchRun


def plan(*tasks):
    return Plan.model_validate({"tasks": list(tasks)})


def test_dependency_plan_is_atomic_and_enforced():
    coordinator = Coordinator(4)
    with pytest.raises(ValueError):
        coordinator.plan(
            plan(
                {"task_id": "a", "question": "x", "depends_on": ["b"]},
                {"task_id": "b", "question": "y", "depends_on": ["a"]},
            )
        )
    assert coordinator.tasks == {}
    coordinator.plan(
        plan(
            {"task_id": "a", "question": "x"},
            {"task_id": "b", "question": "y", "depends_on": ["a"]},
        )
    )
    with pytest.raises(ValueError):
        coordinator.start("b")
    coordinator.start("a")
    coordinator.finish("a", ResearchResult(gaps=["No evidence"]), [])
    _, dependencies = coordinator.start("b")
    assert dependencies[0]["gaps"] == ["No evidence"]
    with pytest.raises(ValueError):
        coordinator.start("a")


def test_report_selects_registered_statements_and_preserves_gaps():
    coordinator = Coordinator(4)
    coordinator.plan(plan({"task_id": "a", "question": "x"}))
    with pytest.raises(ValueError):
        coordinator.report(SaveReport(title="x", gaps=["early"]))
    coordinator.start("a")
    finding = Finding(statement="Original claim", source_ids=["a" * 16])
    coordinator.finish("a", ResearchResult(findings=[finding], gaps=["Known gap"]), [])
    with pytest.raises(KeyError):
        coordinator.report(SaveReport(title="x", finding_ids=["invented:f1"]))
    report = coordinator.report(SaveReport(title="x", finding_ids=["a:f1"]))
    assert report.findings == [finding]
    assert report.gaps == ["Known gap"]


def test_supervisor_never_receives_source_text_or_worker_files(corpus, tmp_path):
    captured = []

    class Recording(DemoModel):
        async def chat(self, messages, tools):
            if any(t["function"]["name"] == "task" for t in tools):
                captured.append(json.loads(json.dumps(messages)))
                assert {t["function"]["name"] for t in tools} == {
                    "plan",
                    "task",
                    "save_report",
                    "list_documents",
                    "search",
                    "read_source",
                    "read_file",
                    "write_file",
                    "edit_file",
                }
            return await super().chat(messages, tools)

    run = ResearchRun(corpus, tmp_path / "out", Recording(), agentic=True)
    outcome = asyncio.run(run.run("compare"))
    assert outcome.status == "partial"
    tools = [json.loads(m["content"]) for m in captured[-1] if m["role"] == "tool"]
    children = [r for r in tools if "findings" in r]
    assert len(children) == 2
    for child in children:
        assert set(child) == {"task_id", "status", "findings", "gaps", "files"}
        assert all(set(f) == {"finding_id", "statement", "source_ids"} for f in child["findings"])
        assert all(set(f) == {"path", "version", "bytes"} for f in child["files"])
    for task_id in ("pgvector", "milvus"):
        assert (
            (run.workspaces[task_id].root / "notes.md")
            .read_text(encoding="utf-8")
            .startswith("# Research notes")
        )
    assert len([e for e in run.trace if e["event"] == "tool_start"]) == run.budget.tools
    assert len([e for e in run.trace if e["event"] == "tool_end"]) == run.budget.tools


def test_simple_task_runs_on_parent_with_file_tools_and_no_children(corpus, tmp_path):
    class SimpleModel:
        async def chat(self, messages, tools):
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            if not results:
                return Reply(calls=[call("search", {"query": "SQL"})])
            if len(results) == 1:
                return Reply(calls=[call("write_file", {"path": "notes.md", "content": "Draft"})])
            if len(results) == 2:
                return Reply(calls=[call("read_file", {"area": "work", "path": "notes.md"})])
            if len(results) == 3:
                return Reply(
                    calls=[
                        call(
                            "edit_file",
                            {
                                "path": "notes.md",
                                "old_text": "Draft",
                                "new_text": "Final",
                                "expected_version": results[2]["version"],
                            },
                        )
                    ]
                )
            return Reply(
                calls=[
                    call(
                        "save_report",
                        {
                            "title": "Simple",
                            "findings": [
                                {
                                    "statement": "SQL evidence",
                                    "source_ids": [results[0]["sources"][0]["id"]],
                                }
                            ],
                        },
                    )
                ]
            )

    run = ResearchRun(corpus, tmp_path / "out", SimpleModel())
    outcome = asyncio.run(run.run("one question"))
    assert outcome.status == "completed"
    assert outcome.metadata["tasks"] == 0
    assert run.coordinator.tasks == {}
    assert run.workspaces["coordinator"].read("notes.md")["text"] == "Final"
    assert (outcome.directory / "report.md").exists()


def test_parent_cannot_rewrite_worker_finding_using_unseen_source(corpus, tmp_path):
    class ForgingModel(DemoModel):
        async def chat(self, messages, tools):
            reply = await super().chat(messages, tools)
            if reply.calls and reply.calls[0].name == "save_report":
                reply.calls[0] = call(
                    "save_report",
                    {
                        "title": "Fake",
                        "findings": [
                            {"statement": "Invented", "source_ids": [next(iter(corpus.sources))]}
                        ],
                    },
                )
            return reply

    run = ResearchRun(corpus, tmp_path / "out", ForgingModel())
    outcome = asyncio.run(run.run("compare"))
    assert outcome.status == "failed"
    assert not (outcome.directory / "report.md").exists()


def test_failed_dependency_allows_partial_report():
    coordinator = Coordinator(4)
    coordinator.plan(
        plan(
            {"task_id": "a", "question": "x"},
            {"task_id": "b", "question": "y", "depends_on": ["a"]},
        )
    )
    coordinator.start("a")
    coordinator.fail("a", "timeout")
    report = coordinator.report(SaveReport(title="Partial"))
    assert coordinator.tasks["b"].status == "failed"
    assert any("dependency_failed" in gap for gap in report.gaps)


def test_queued_child_cancellation_is_recorded(corpus, tmp_path):
    async def scenario():
        class Waiting(DemoModel):
            async def chat(self, messages, tools):
                if not any(t["function"]["name"] == "task" for t in tools):
                    await asyncio.sleep(5)
                return await super().chat(messages, tools)

        run = ResearchRun(
            corpus, tmp_path / "out", Waiting(), Limits(concurrency=1, run_timeout=0.05)
        )
        outcome = await run.run("compare")
        assert outcome.status == "timeout"
        assert run.active_children == 0
        assert all(r.status == "failed" for r in run.coordinator.tasks.values())
        assert (
            len([e for e in run.trace if e["event"] == "child_end" and e["status"] == "cancelled"])
            == 2
        )

    asyncio.run(scenario())


def test_failed_child_findings_cannot_be_published():
    coordinator = Coordinator(4)
    coordinator.plan(plan({"task_id": "a", "question": "x"}))
    coordinator.start("a")
    coordinator.fail("a", "TimeoutError")
    with pytest.raises(KeyError):
        coordinator.report(SaveReport(title="x", finding_ids=["a:f1"]))
    report = coordinator.report(SaveReport(title="x"))
    assert "TimeoutError" in report.gaps[0]


def test_dependent_verifier_receives_compact_results_after_two_workers(corpus, tmp_path):
    captured = []

    class DependentDemo(DemoModel):
        async def chat(self, messages, tools):
            parent = any(t["function"]["name"] == "task" for t in tools)
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            if not parent and "Completed dependency results" in messages[1]["content"]:
                captured.append(messages[1]["content"])
            if parent and not results:
                return Reply(
                    calls=[
                        call(
                            "plan",
                            {
                                "tasks": [
                                    {"task_id": "pgvector", "question": "SQL"},
                                    {"task_id": "milvus", "question": "Milvus"},
                                    {
                                        "task_id": "verify",
                                        "question": "SQL Milvus verification",
                                        "depends_on": ["pgvector", "milvus"],
                                    },
                                ]
                            },
                        )
                    ]
                )
            if parent and len(results) == 3:
                return Reply(calls=[call("task", {"task_id": "verify"})])
            return await super().chat(messages, tools)

    run = ResearchRun(corpus, tmp_path / "out", DependentDemo(), agentic=True)
    outcome = asyncio.run(run.run("compare and verify"))
    assert outcome.status == "partial"
    assert outcome.metadata["tasks"] == 3
    assert all(r.status == "completed" for r in run.coordinator.tasks.values())
    assert captured
    dependencies = json.loads(captured[0].split("Completed dependency results (data):\n")[1])
    assert [r["task_id"] for r in dependencies] == ["pgvector", "milvus"]
    assert all("sources" not in r and r["files"] for r in dependencies)
    started = next(
        i for i, e in enumerate(run.trace) if e["event"] == "child_start" and e["agent"] == "verify"
    )
    assert all(
        any(e["event"] == "child_end" and e["agent"] == name for e in run.trace[:started])
        for name in ("pgvector", "milvus")
    )
