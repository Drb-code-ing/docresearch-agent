"""BM25 by default; optional dense vectors combined by reciprocal ranks."""

import re
from collections.abc import Awaitable, Callable

import numpy as np
from rank_bm25 import BM25Okapi

from .workspace import Corpus, Source

Embed = Callable[[list[str]], Awaitable[list[list[float]]]]


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())
    # Chinese characters + adjacent bigrams keep the demo dependency-light.
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def normalized(vectors: list[list[float]], count: int, dimension: int | None = None) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != count or matrix.shape[1] == 0:
        raise ValueError("Invalid embedding shape")
    if dimension is not None and matrix.shape[1] != dimension:
        raise ValueError("Embedding dimension changed")
    if not np.isfinite(matrix).all():
        raise ValueError("Non-finite embedding")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("Zero or invalid embedding norm")
    return matrix / norms


class Retriever:
    def __init__(self, corpus: Corpus, embed: Embed | None = None):
        self.corpus = corpus
        self.items = list(corpus.sources.values())
        self.tokens = [tokenize(item.text) for item in self.items]
        # The fallback token avoids division by zero on punctuation-only corpora.
        self.bm25 = BM25Okapi([tokens or ["__empty__"] for tokens in self.tokens])
        self.embed = embed
        self.vectors: np.ndarray | None = None

    async def prepare(self) -> None:
        if self.embed:
            vectors: list[list[float]] = []
            for offset in range(0, len(self.items), 32):
                batch = self.items[offset : offset + 32]
                vectors.extend(await self.embed([item.text for item in batch]))
            self.vectors = normalized(vectors, len(self.items))

    async def search(self, query: str, limit: int = 5) -> list[Source]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        overlap = set(query_tokens)
        # BM25 can be zero/negative in very small corpora; require lexical overlap,
        # not a positive score, and use source ID for reproducible ties.
        lexical = sorted(
            (i for i, tokens in enumerate(self.tokens) if overlap.intersection(tokens)),
            key=lambda i: (-float(scores[i]), self.items[i].id),
        )[:20]
        rankings = [lexical]
        if self.embed:
            if self.vectors is None:
                raise ValueError("Dense index has not been prepared")
            query_vector = normalized(await self.embed([query]), 1, self.vectors.shape[1])[0]
            similarities = self.vectors @ query_vector
            dense = sorted(
                (i for i, score in enumerate(similarities) if score > 0),
                key=lambda i: (-float(similarities[i]), self.items[i].id),
            )[:20]
            rankings.append(dense)
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, index in enumerate(ranking, 1):
                fused[index] = fused.get(index, 0.0) + 1 / (60 + rank)
        ordered = sorted(fused, key=lambda i: (-fused[i], self.items[i].id))
        return [self.items[i] for i in ordered[:limit]]
