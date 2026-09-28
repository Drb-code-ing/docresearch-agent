"""Read a bounded document snapshot and publish artifacts outside the corpus."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_FILE_BYTES = 256_000
MAX_TOTAL_BYTES = 2_000_000
MAX_FILES = 100
MAX_CHUNKS = 400
CHUNK_CHARS = 1800


@dataclass(frozen=True)
class Source:
    id: str
    path: str
    start_line: int
    end_line: int
    version: str
    text: str

    def payload(self) -> dict:
        return asdict(self)


def contained(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Path escapes the configured directory")
    return resolved


class Corpus:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Corpus must be a directory")
        self.sources: dict[str, Source] = {}
        self.documents: list[dict] = []
        self.texts: dict[str, str] = {}
        total = 0
        # Skip hidden directories and links rather than following arbitrary trees.
        for directory, dirs, filenames in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs if not d.startswith(".") and not (Path(directory) / d).is_symlink()
            )
            for name in sorted(filenames):
                if name.startswith(".") or Path(name).suffix.lower() not in {".md", ".txt"}:
                    continue
                file = Path(directory) / name
                if file.is_symlink():
                    continue
                file = contained(self.root, file)
                if len(self.documents) >= MAX_FILES:
                    raise ValueError("Corpus has too many files")
                with file.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                total += len(raw)
                if len(raw) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    raise ValueError("Corpus exceeds byte limits")
                text = raw.decode("utf-8-sig")
                relative = file.relative_to(self.root).as_posix()
                self.texts[relative] = text
                version = hashlib.sha256(raw).hexdigest()
                self.documents.append({"path": relative, "version": version, "bytes": len(raw)})
                self._chunk(relative, version, text)
        if not self.sources:
            raise ValueError("No nonempty UTF-8 Markdown/TXT documents found")

    def _chunk(self, path: str, version: str, text: str) -> None:
        buffer: list[str] = []
        start = 1
        size = 0

        def add(end: int) -> None:
            content = "\n".join(buffer)
            if not content.strip():
                return
            identity = f"{path}\0{version}\0{start}\0{end}\0{content}"
            key = hashlib.sha256(identity.encode()).hexdigest()[:16]
            self.sources[key] = Source(key, path, start, end, version, content)
            if len(self.sources) > MAX_CHUNKS:
                raise ValueError("Corpus has too many chunks")

        for number, line in enumerate(text.splitlines(), 1):
            if len(line) > CHUNK_CHARS:
                raise ValueError("A source line exceeds 1800 characters; split it first")
            if buffer and size + len(line) + 1 > CHUNK_CHARS:
                add(number - 1)
                buffer = []
                start = number
                size = 0
            buffer.append(line)
            size += len(line) + 1
        if buffer:
            add(start + len(buffer) - 1)

    def read(self, source_id: str) -> Source:
        if source_id not in self.sources:
            raise ValueError("Unknown source ID")
        # Returns the indexed snapshot, not a later version of the file.
        return self.sources[source_id]

    def read_file(self, path: str, start_line: int, max_lines: int) -> dict:
        lines = self.texts[path].splitlines()
        selected = lines[start_line - 1 : start_line - 1 + max_lines]
        text = "\n".join(selected)
        if len(text) > 12000:
            raise ValueError("Read fewer lines")
        end = start_line + len(selected) - 1
        ids = [
            source.id
            for source in self.sources.values()
            if source.path == path and source.start_line >= start_line and source.end_line <= end
        ]
        version = next(d["version"] for d in self.documents if d["path"] == path)
        return {
            "path": path,
            "version": version,
            "text": text,
            "start_line": start_line,
            "source_ids": ids,
        }


class WorkFiles:
    """A worker owns a small text workspace; edits require the last observed hash."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, relative: str) -> Path:
        if "\\" in relative or ":" in relative:
            raise ValueError("Use a relative POSIX path")
        item = Path(relative)
        if item.is_absolute() or any(p in {"..", "."} or p.startswith(".") for p in item.parts):
            raise ValueError("Invalid work path")
        if item.suffix.lower() not in {".md", ".txt", ".json"}:
            raise ValueError("Only text work files are supported")
        current = self.root
        for part in item.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Symbolic links are not supported")
        return contained(self.root, current)

    def read(self, relative: str, start_line: int = 1, max_lines: int = 60) -> dict:
        path = self.path(relative)
        raw = path.read_bytes()
        if len(raw) > 48000:
            raise ValueError("Work file too large")
        text = raw.decode("utf-8")
        return {
            "path": relative,
            "version": hashlib.sha256(raw).hexdigest(),
            "text": "\n".join(text.splitlines()[start_line - 1 : start_line - 1 + max_lines]),
        }

    def write(self, relative: str, text: str, expected_version: str = "") -> dict:
        path = self.path(relative)
        raw = text.encode("utf-8")
        if len(text) > 12000 or len(raw) > 48000:
            raise ValueError("Work file too large")
        old = path.read_bytes() if path.exists() else None
        version = hashlib.sha256(old).hexdigest() if old is not None else ""
        if version != expected_version:
            raise ValueError("Stale file version; read it before editing")
        inventory = self.inventory()
        if old is None and len(inventory) >= 8:
            raise ValueError("Worker file count limit exceeded")
        if sum(f["bytes"] for f in inventory) - len(old or b"") + len(raw) > 96000:
            raise ValueError("Worker byte limit exceeded")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"path": relative, "version": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def edit(self, relative: str, old_text: str, new_text: str, expected_version: str) -> dict:
        content = self.path(relative).read_text(encoding="utf-8")
        if content.count(old_text) != 1:
            raise ValueError("Edit must match exactly once")
        return self.write(relative, content.replace(old_text, new_text, 1), expected_version)

    def inventory(self) -> list[dict]:
        if not self.root.exists():
            return []
        files = []
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symbolic links are not supported")
            if path.is_file():
                raw = path.read_bytes()
                files.append(
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "version": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                    }
                )
        return files


class ArtifactWriter:
    def __init__(self, root: Path, corpus_root: Path):
        self.root = root.resolve()
        corpus_root = corpus_root.resolve()
        if self.root.is_relative_to(corpus_root) or corpus_root.is_relative_to(self.root):
            raise ValueError("Report directory and corpus must be separate trees")

    def write(self, directory: Path, name: str, content: str) -> None:
        if name not in {"report.md", "sources.json", "trace.json", "run.json", "tasks.json"}:
            raise ValueError("Unknown artifact")
        target = contained(self.root, directory / name)
        if target.exists():
            raise ValueError("Refusing to overwrite an existing artifact")
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def publish(self, run_id: str, artifacts: dict[str, str]) -> Path:
        if not run_id.isalnum():
            raise ValueError("Invalid run ID")
        directory = contained(self.root, self.root / run_id)
        directory.mkdir(parents=True, exist_ok=False)
        for name, content in artifacts.items():
            self.write(directory, name, content)
        return directory


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
