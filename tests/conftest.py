from pathlib import Path

import pytest

from docresearch.workspace import Corpus


@pytest.fixture
def corpus(tmp_path: Path) -> Corpus:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "postgres.md").write_text(
        "# PostgreSQL\n\npgvector supports SQL queries.\n", encoding="utf-8"
    )
    (root / "milvus.txt").write_text(
        "Milvus supports vector search and scalar filters.\n", encoding="utf-8"
    )
    (root / "notes.md").write_text("No comparable benchmark is supplied.\n", encoding="utf-8")
    return Corpus(root)
