import asyncio

import pytest

from docresearch.retrieval import Retriever, normalized, tokenize


def test_english_and_chinese_tokens():
    assert "postgresql" in tokenize("PostgreSQL 数据库")
    assert "数据" in tokenize("PostgreSQL 数据库")


def test_keyword_retrieval_and_empty(corpus):
    retriever = Retriever(corpus)
    assert asyncio.run(retriever.search("SQL"))[0].path == "postgres.md"
    assert asyncio.run(retriever.search("unfindablekeyword")) == []
    assert asyncio.run(retriever.search("!!!")) == []


def test_hybrid_semantic_only_hit(corpus):
    async def embed(texts):
        return [[1.0, 0.0] if "pgvector" in t or t == "relational" else [0.0, 1.0] for t in texts]

    async def run():
        retriever = Retriever(corpus, embed)
        await retriever.prepare()
        return await retriever.search("relational")

    assert asyncio.run(run())[0].path == "postgres.md"


@pytest.mark.parametrize(
    "vectors",
    [[[0.0, 0.0]], [[float("nan"), 1.0]], [[float("inf"), 1.0]], [[1.0]], [], [[1.0], [2.0]]],
)
def test_invalid_embeddings(vectors):
    with pytest.raises(ValueError):
        normalized(vectors, 1, 2)


def test_ranking_is_deterministic(corpus):
    retriever = Retriever(corpus)
    first = asyncio.run(retriever.search("supports", 1))
    assert first == asyncio.run(retriever.search("supports", 1))
