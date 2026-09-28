"""Optional DashScope reranker adapter; credentials are independent of chat."""

import math
import os

import httpx

from .provider import ProviderProtocolError


class DashScopeReranker:
    def __init__(self, url: str, api_key: str, model: str, *, trust_env: bool = True):
        parsed = httpx.URL(url)
        if (
            parsed.scheme != "https"
            or not parsed.host
            or parsed.userinfo
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Rerank URL must be HTTPS without credentials or query")
        if not api_key or not model:
            raise ValueError("Rerank key and model are required")
        self.url, self.model = url, model
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            trust_env=trust_env,
            follow_redirects=False,
        )

    @classmethod
    def from_env(cls):
        fields = [
            os.environ.get("DOCRESEARCH_RERANK_" + key, "") for key in ("URL", "API_KEY", "MODEL")
        ]
        if not any(fields):
            return None
        if not all(fields):
            raise ValueError("Set all three rerank variables")
        return cls(
            *fields,
            trust_env=os.environ.get("DOCRESEARCH_TRUST_ENV", "true").lower().strip() == "true",
        )

    async def rank(self, query: str, sources: list) -> list[str]:
        response = await self.client.post(
            self.url,
            json={
                "model": self.model,
                "input": {"query": query, "documents": [s.text for s in sources]},
                "parameters": {"return_documents": False, "top_n": len(sources)},
            },
        )
        response.raise_for_status()
        try:
            rows = response.json()["output"]["results"]
            if not isinstance(rows, list) or len(rows) != len(sources):
                raise ValueError("Incomplete rerank response")
            indices = [row["index"] for row in rows]
            if any(type(i) is not int for i in indices) or set(indices) != set(range(len(sources))):
                raise ValueError("Invalid rerank indices")
            if any(
                type(r["relevance_score"]) not in {int, float}
                or not math.isfinite(r["relevance_score"])
                for r in rows
            ):
                raise ValueError("Invalid rerank scores")
            return [
                sources[row["index"]].id
                for row in sorted(rows, key=lambda r: -r["relevance_score"])
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderProtocolError("Invalid rerank response") from error

    async def close(self):
        await self.client.aclose()
