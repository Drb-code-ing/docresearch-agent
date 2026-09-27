import asyncio

import pytest

from docresearch.evaluation import Case, evaluate, summarize


def test_metrics_separate_recall_from_no_answer():
    rows = [
        {"expected_documents": ["a", "b"], "returned_documents": ["a", "a"]},
        {"expected_documents": ["b"], "returned_documents": ["a", "b"]},
        {"expected_documents": [], "returned_documents": []},
        {"expected_documents": [], "returned_documents": ["a"]},
    ]
    metrics = summarize(rows)
    assert metrics["mean_document_recall_at_2"] == 0.75
    assert metrics["top_1_document_hit_rate"] == 0.5
    assert metrics["no_answer_empty_result_rate"] == 0.5


def test_empty_groups_are_not_fake_perfect_scores():
    metrics = summarize([])
    assert metrics["mean_document_recall_at_2"] is None
    assert metrics["no_answer_empty_result_rate"] is None


def test_evaluation_rejects_unknown_labels(corpus):
    with pytest.raises(ValueError, match="unknown document"):
        asyncio.run(evaluate(corpus, [Case(query="query", expected_documents=["missing.md"])]))


def test_evaluation_uses_real_retriever_without_chat(corpus):
    path = corpus.documents[0]["path"]
    result = asyncio.run(evaluate(corpus, [Case(query="PostgreSQL", expected_documents=[path])]))
    assert result["mode"] == "bm25"
    assert result["embedding_requests"] == 0
    assert len(result["cases"]) == 1
