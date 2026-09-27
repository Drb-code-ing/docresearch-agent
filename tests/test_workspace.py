import json
from pathlib import Path

import pytest

from docresearch.workspace import ArtifactWriter, Corpus, contained


def test_snapshot_stable_ids_and_original_lines(corpus):
    again = Corpus(corpus.root)
    assert list(corpus.sources) == list(again.sources)
    source = next(s for s in corpus.sources.values() if s.path == "postgres.md")
    assert (source.start_line, source.end_line) == (1, 3)
    assert len(source.version) == 64
    (corpus.root / source.path).write_text("changed", encoding="utf-8")
    assert "SQL" in corpus.read(source.id).text
    assert source.id not in Corpus(corpus.root).sources


def test_unknown_source_denied(corpus):
    with pytest.raises(ValueError):
        corpus.read("../../secret")


def test_path_escape_denied(corpus):
    with pytest.raises(ValueError):
        contained(corpus.root, corpus.root / ".." / "secret.md")


def test_hidden_and_nontext_ignored(corpus):
    (corpus.root / ".secret.md").write_text("secret", encoding="utf-8")
    (corpus.root / "image.bin").write_bytes(b"\x00")
    assert len(Corpus(corpus.root).documents) == 3


def test_symlink_not_followed(corpus, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    try:
        (corpus.root / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("OS denies unprivileged symlink creation")
    assert len(Corpus(corpus.root).documents) == 3


@pytest.mark.parametrize(
    "content",
    [b"x" * 256001, b"x" * 1801, b"\xff"],
    ids=["oversize-file", "oversize-line", "invalid-utf8"],
)
def test_invalid_document_rejected(corpus, content):
    (corpus.root / "bad.md").write_bytes(content)
    with pytest.raises((ValueError, UnicodeError)):
        Corpus(corpus.root)


def test_empty_corpus(tmp_path):
    with pytest.raises(ValueError):
        Corpus(tmp_path)


@pytest.mark.parametrize("relative", [".", "reports", ".."])
def test_output_overlap_denied(corpus, relative):
    with pytest.raises(ValueError):
        ArtifactWriter(corpus.root / relative, corpus.root)


def test_publish_no_overwrite_or_arbitrary_path(corpus, tmp_path):
    writer = ArtifactWriter(tmp_path / "reports", corpus.root)
    directory = writer.publish("abc123", {"run.json": json.dumps({"status": "failed"})})
    assert json.loads((directory / "run.json").read_text()) == {"status": "failed"}
    with pytest.raises(FileExistsError):
        writer.publish("abc123", {})
    with pytest.raises(ValueError):
        writer.write(directory, "../source.md", "overwrite")
    with pytest.raises(ValueError):
        writer.publish("../evil", {})
    assert not list(directory.glob("*.tmp"))


def test_chunks_preserve_all_lines(tmp_path: Path):
    root = tmp_path / "docs"
    root.mkdir()
    text = "\n".join(f"line {i} " + "a" * 40 for i in range(100))
    (root / "long.md").write_text(text, encoding="utf-8")
    sources = list(Corpus(root).sources.values())
    assert len(sources) > 1
    assert "\n".join(s.text for s in sources) == text
    assert all(a.end_line + 1 == b.start_line for a, b in zip(sources, sources[1:], strict=False))
