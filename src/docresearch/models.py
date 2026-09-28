"""Strict tool contracts shared by the agent, dispatcher and tests."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
SummaryText = Annotated[str, Field(min_length=1, max_length=500)]
SourceId = Annotated[str, Field(pattern=r"^[a-f0-9]{16}$")]
TaskId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")]
FilePath = Annotated[str, Field(min_length=1, max_length=180)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Contract):
    pass


class Search(Contract):
    query: ShortText
    limit: int = Field(default=5, ge=1, le=8)


class ReadSource(Contract):
    source_id: SourceId


class Task(Contract):
    task_id: TaskId


class PlannedTask(Contract):
    task_id: TaskId
    question: ShortText
    depends_on: list[TaskId] = Field(default_factory=list, max_length=4)


class Plan(Contract):
    tasks: list[PlannedTask] = Field(min_length=1, max_length=8)


class ReadFile(Contract):
    area: Literal["corpus", "work"]
    path: FilePath
    start_line: int = Field(default=1, ge=1)
    max_lines: int = Field(default=60, ge=1, le=120)


class WriteFile(Contract):
    path: FilePath
    content: str = Field(max_length=12000)
    expected_version: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")


class EditFile(Contract):
    path: FilePath
    old_text: str = Field(min_length=1, max_length=6000)
    new_text: str = Field(max_length=6000)
    expected_version: str = Field(pattern=r"^[a-f0-9]{64}$")


class Finding(Contract):
    statement: SummaryText
    source_ids: list[SourceId] = Field(min_length=1, max_length=8)


class ResearchResult(Contract):
    findings: list[Finding] = Field(default_factory=list, max_length=6)
    gaps: list[SummaryText] = Field(default_factory=list, max_length=4)


class Report(ResearchResult):
    title: str = Field(min_length=1, max_length=160)
    findings: list[Finding] = Field(default_factory=list, max_length=24)
    gaps: list[SummaryText] = Field(default_factory=list, max_length=40)


class SaveReport(Contract):
    title: str = Field(min_length=1, max_length=160)
    finding_ids: list[str] = Field(default_factory=list, max_length=24)
    findings: list[Finding] = Field(default_factory=list, max_length=6)
    gaps: list[SummaryText] = Field(default_factory=list, max_length=8)


class QueryRewrite(Contract):
    queries: list[SummaryText] = Field(min_length=1, max_length=2)


class EvidenceGrade(Contract):
    ordered_ids: list[SourceId] = Field(default_factory=list, max_length=8)
    sufficient: bool
    missing: str = Field(max_length=500)
    retry_query: str = Field(default="", max_length=500)


class ToolCall(Contract):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments: str = Field(max_length=24000)


class Reply(Contract):
    content: str = ""
    calls: list[ToolCall] = Field(default_factory=list, max_length=8)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class Limits(Contract):
    max_calls: int = Field(default=48, ge=1, le=100)
    max_tools: int = Field(default=64, ge=1, le=200)
    parent_steps: int = Field(default=10, ge=1, le=20)
    child_steps: int = Field(default=10, ge=1, le=12)
    max_tasks: int = Field(default=4, ge=1, le=8)
    concurrency: int = Field(default=2, ge=1, le=4)
    request_timeout: float = Field(default=30.0, gt=0, le=120)
    run_timeout: float = Field(default=180.0, gt=0, le=600)


Status = Literal["completed", "partial", "failed", "budget_exhausted", "timeout"]
