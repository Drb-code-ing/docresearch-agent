"""Append-only task plans and validated, compact worker results."""

from dataclasses import dataclass

from .models import Finding, Plan, PlannedTask, Report, ResearchResult, SaveReport


@dataclass
class TaskRecord:
    task: PlannedTask
    status: str = "pending"
    result: dict | None = None


class Coordinator:
    def __init__(self, max_tasks: int):
        self.max_tasks = max_tasks
        self.tasks: dict[str, TaskRecord] = {}
        self.findings: dict[str, Finding] = {}
        self.gaps: list[str] = []

    def plan(self, plan: Plan) -> dict:
        incoming = {task.task_id: task for task in plan.tasks}
        if "coordinator" in incoming:
            raise ValueError("Reserved agent name")
        if len(incoming) != len(plan.tasks) or set(incoming) & self.tasks.keys():
            raise ValueError("Task IDs must be new and unique")
        if len(self.tasks) + len(incoming) > self.max_tasks:
            raise ValueError("Task plan limit exceeded")
        known = set(self.tasks) | set(incoming)
        if any(set(t.depends_on) - known for t in incoming.values()):
            raise ValueError("Unknown dependency")
        pending = dict(incoming)
        ready = set(self.tasks)
        while pending:
            batch = {key for key, task in pending.items() if set(task.depends_on) <= ready}
            if not batch:
                raise ValueError("Cyclic task plan")
            ready.update(batch)
            pending = {key: task for key, task in pending.items() if key not in batch}
        self.tasks.update({key: TaskRecord(task) for key, task in incoming.items()})
        return {"tasks": [{"task_id": key, "status": r.status} for key, r in self.tasks.items()]}

    def start(self, task_id: str) -> tuple[TaskRecord, list[dict]]:
        record = self.tasks[task_id]
        if record.status != "pending":
            raise ValueError("Task already started; use a new task ID for follow-up")
        dependencies = [self.tasks[key] for key in record.task.depends_on]
        if any(item.status == "failed" for item in dependencies):
            self.fail(task_id, "dependency_failed")
            raise ValueError("A dependency failed")
        if any(item.status != "completed" for item in dependencies):
            raise ValueError("Dependencies must finish before dispatch")
        record.status = "running"
        return record, [item.result for item in dependencies]

    def finish(self, task_id: str, result: ResearchResult, files: list[dict]) -> dict:
        findings = []
        for number, finding in enumerate(result.findings, 1):
            key = f"{task_id}:f{number}"
            self.findings[key] = finding
            findings.append({"finding_id": key, **finding.model_dump()})
        summary = {
            "task_id": task_id,
            "status": "completed",
            "findings": findings,
            "gaps": result.gaps,
            "files": files,
        }
        self.gaps.extend(result.gaps)
        self.tasks[task_id].status = "completed"
        self.tasks[task_id].result = summary
        return summary

    def fail(self, task_id: str, kind: str) -> dict:
        result = {"task_id": task_id, "status": "failed", "error": kind}
        self.tasks[task_id].status = "failed"
        self.tasks[task_id].result = result
        self.gaps.append(f"Task {task_id} failed: {kind}")
        return result

    def report(self, command: SaveReport) -> Report:
        self.resolve_blocked()
        if any(r.status in {"pending", "running"} for r in self.tasks.values()):
            raise ValueError("Execute every planned task before publishing")
        if len(set(command.finding_ids)) != len(command.finding_ids):
            raise ValueError("Duplicate finding IDs")
        findings = [self.findings[key] for key in command.finding_ids] + command.findings
        gaps = list(dict.fromkeys(self.gaps + command.gaps))
        if not findings and not gaps:
            raise ValueError("Report must contain findings or gaps")
        return Report(title=command.title, findings=findings, gaps=gaps)

    def resolve_blocked(self) -> None:
        changed = True
        while changed:
            changed = False
            for task_id, record in self.tasks.items():
                if record.status == "pending" and any(
                    self.tasks[key].status == "failed" for key in record.task.depends_on
                ):
                    self.fail(task_id, "dependency_failed")
                    changed = True

    def snapshot(self) -> list[dict]:
        return [
            {**record.task.model_dump(), "status": record.status, "result": record.result}
            for record in self.tasks.values()
        ]
