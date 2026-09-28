import pytest

from docresearch.workspace import WorkFiles


def test_private_workspaces_and_versioned_edit(tmp_path):
    a, b = WorkFiles(tmp_path / "a"), WorkFiles(tmp_path / "b")
    first = a.write("notes.md", "first\nsecond")
    b.write("notes.md", "other")
    assert a.read("notes.md")["text"] == "first\nsecond"
    assert b.read("notes.md")["text"] == "other"
    updated = a.edit("notes.md", "first", "updated", first["version"])
    with pytest.raises(ValueError):
        a.edit("notes.md", "second", "lost update", first["version"])
    with pytest.raises(ValueError):
        a.write("notes.md", "overwrite")
    assert a.read("notes.md")["version"] == updated["version"]
    assert a.read("notes.md")["text"] == "updated\nsecond"


@pytest.mark.parametrize(
    "path", ["../b/x.md", "/tmp/x.md", "C:/x.md", "a\\b.md", ".env", "x.py", "a/.hidden/x.txt"]
)
def test_work_path_escape_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        WorkFiles(tmp_path).write(path, "x")


def test_ambiguous_edit_and_limits_leave_original(tmp_path):
    files = WorkFiles(tmp_path)
    item = files.write("notes.txt", "repeat repeat")
    with pytest.raises(ValueError):
        files.edit("notes.txt", "repeat", "x", item["version"])
    with pytest.raises(ValueError):
        files.write("notes.txt", "x" * 12001, item["version"])
    assert files.read("notes.txt")["text"] == "repeat repeat"


def test_corpus_read_file_uses_snapshot(corpus):
    source = next(iter(corpus.sources.values()))
    (corpus.root / source.path).write_text("Changed after snapshot", encoding="utf-8")
    result = corpus.read_file(source.path, 1, 120)
    assert "Changed after snapshot" not in result["text"]
    assert source.id in result["source_ids"]


def test_work_symlink_rejected(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    try:
        (work / "link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        WorkFiles(work).write("link/x.md", "x")
