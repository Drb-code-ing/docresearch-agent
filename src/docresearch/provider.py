"""A small OpenAI-compatible transport; no credentials are stored in artifacts."""

import json
import os
from typing import Protocol

import httpx

from .models import Reply, ToolCall


class ProviderProtocolError(Exception):
    """The endpoint returned a successful status but an invalid response shape."""


class Model(Protocol):
    async def chat(self, messages: list[dict], tools: list[dict]) -> Reply: ...


class CompatibleModel:
    def __init__(self, base_url: str, api_key: str, model: str, embedding_model: str = ""):
        url = httpx.URL(base_url)
        if url.scheme not in {"http", "https"} or url.username or url.password or url.query:
            raise ValueError("Use an HTTP(S) base URL without credentials or query parameters")
        if not api_key or not model:
            raise ValueError("API key and chat model are required")
        self.model = model
        self.embedding_model = embedding_model
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            follow_redirects=False,
        )

    @classmethod
    def from_env(cls) -> "CompatibleModel":
        return cls(
            os.environ.get("DOCRESEARCH_BASE_URL", ""),
            os.environ.get("DOCRESEARCH_API_KEY", ""),
            os.environ.get("DOCRESEARCH_MODEL", ""),
            os.environ.get("DOCRESEARCH_EMBEDDING_MODEL", ""),
        )

    async def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        response = await self.client.post(
            "chat/completions",
            json={"model": self.model, "messages": messages, "tools": tools, "max_tokens": 1600},
        )
        response.raise_for_status()
        try:
            body = response.json()
            message = body["choices"][0]["message"]
            usage = body.get("usage") or {}
            return Reply(
                content=message.get("content") or "",
                calls=[
                    ToolCall(
                        id=c["id"], name=c["function"]["name"], arguments=c["function"]["arguments"]
                    )
                    for c in message.get("tool_calls") or []
                ],
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise ProviderProtocolError("Invalid chat response") from error

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.post(
            "embeddings",
            json={"model": self.embedding_model, "input": texts},
        )
        response.raise_for_status()
        try:
            data = sorted(response.json()["data"], key=lambda row: row["index"])
            if [row["index"] for row in data] != list(range(len(texts))):
                raise ValueError("Embedding response indices do not match inputs")
            return [row["embedding"] for row in data]
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise ProviderProtocolError("Invalid embedding response") from error

    async def close(self) -> None:
        await self.client.aclose()


class DemoModel:
    """Deterministic fixture for the bundled example, not a language model."""

    async def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        parent = any(t["function"]["name"] == "task" for t in tools)
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]

        def call(name: str, payload: dict, suffix: str = "1") -> ToolCall:
            return ToolCall(
                id=f"demo-{len(results)}-{suffix}",
                name=name,
                arguments=json.dumps(payload, ensure_ascii=False),
            )

        if parent and not results:
            return Reply(
                calls=[
                    call("task", {"question": "pgvector PostgreSQL 小型知识库部署与关系查询"}),
                    call("task", {"question": "Milvus 向量数据库部署与维护成本"}, "2"),
                ]
            )
        if not parent and not results:
            return Reply(calls=[call("search", {"query": messages[1]["content"], "limit": 2})])
        findings: list[dict] = []
        if parent:
            for result in results:
                findings.extend(result.get("result", {}).get("findings", []))
            return Reply(
                calls=[
                    call(
                        "save_report",
                        {
                            "title": "小型知识库选型资料摘录（离线演示）",
                            "findings": findings[:8],
                            "gaps": [
                                "离线模式只演示派发、检索与落盘；未执行真实模型推理或性能对比。"
                            ],
                        },
                    )
                ]
            )
        for result in results:
            for source in result.get("sources", []):
                paragraphs = [p.strip() for p in source["text"].split("\n\n") if p.strip()]
                excerpt = next(
                    (p for p in paragraphs if "pgvector 是" in p or "Milvus 是" in p),
                    paragraphs[-1],
                )
                findings.append({"statement": excerpt, "source_ids": [source["id"]]})
        return Reply(
            calls=[
                call(
                    "finish_research",
                    {
                        "findings": findings[:4],
                        "gaps": [] if findings else ["当前查询没有检索到资料。"],
                    },
                )
            ]
        )
