"""Strict tool contracts shared by the agent, dispatcher and tests."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ShortText = Annotated[str, Field(min_length=1, max_length=2000)]
SourceId = Annotated[str, Field(pattern=r"^[a-f0-9]{16}$")]


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
    question: ShortText


class Finding(Contract):
    statement: ShortText
    source_ids: list[SourceId] = Field(min_length=1, max_length=8)


class ResearchResult(Contract):
    findings: list[Finding] = Field(default_factory=list, max_length=8)
    gaps: list[ShortText] = Field(default_factory=list, max_length=8)


class Report(ResearchResult):
    title: str = Field(min_length=1, max_length=160)


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
    max_calls: int = Field(default=24, ge=1, le=100)
    max_tools: int = Field(default=48, ge=1, le=200)
    parent_steps: int = Field(default=8, ge=1, le=20)
    child_steps: int = Field(default=5, ge=1, le=10)
    max_tasks: int = Field(default=4, ge=1, le=8)
    concurrency: int = Field(default=2, ge=1, le=4)
    request_timeout: float = Field(default=30.0, gt=0, le=120)
    run_timeout: float = Field(default=180.0, gt=0, le=600)


Status = Literal["completed", "partial", "failed", "budget_exhausted", "timeout"]
