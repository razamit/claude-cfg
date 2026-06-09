import io
import json
import platform
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from claude_cfg import __version__
from claude_cfg.paths import (
    CLAUDE_TOKEN,
    HOME_TOKEN,
    PYTHON_TOKEN,
    collapse_interpreter,
    collapse_paths,
    expand_interpreter,
    expand_paths,
    resolve_python,
)

SCHEMA_VERSION = 3

# Secrets and machine-bound state are never captured, even if a tracked folder
# happens to contain them. Keeps snapshots light and safe for public backends.
_EXCLUDED_NAMES = {".credentials.json", ".DS_Store", "Thumbs.db"}
_EXCLUDED_TOPS = {"projects", "todos", "statsig", "shell-snapshots", "ide", "logs"}
# Re-fetchable / derived directory trees, excluded wherever they appear. Plugin
# marketplaces are git clones and the cache is rebuilt from the JSON manifests,
# so only the small manifests need to travel — not thousands of cloned files.
_EXCLUDED_SEGMENTS = {".git", "node_modules", "__pycache__"}
_EXCLUDED_PREFIXES = ("plugins/cache/", "plugins/marketplaces/")


def _is_excluded(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    if name in _EXCLUDED_NAMES or name.endswith(".log"):
        return True
    if parts[0] in _EXCLUDED_TOPS:
        return True
    if any(seg in _EXCLUDED_SEGMENTS for seg in parts):
        return True
    return any(rel.startswith(prefix) for prefix in _EXCLUDED_PREFIXES)


def _slug(message: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in message.lower())
    parts = [p for p in safe.split("-") if p]
    return "-".join(parts[:6])


def snapshot_key(snapshot_id: int, timestamp: str, message: str) -> str:
    ts = timestamp.replace(":", "").replace("-", "").replace("T", "T")[:15]
    slug = _slug(message) if message else "snapshot"
    return f"snapshots/{snapshot_id:03d}_{ts}_{slug}.zip"


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _transform_json(text: str, fn) -> tuple[str, bool]:
    """Apply ``fn`` to every string value; reserialize only if something changed."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        new = fn(text)
        return new, new != text
    new_obj, changed = _walk(obj, fn)
    if not changed:
        return text, False
    return json.dumps(new_obj, indent=2), True


def _walk(obj, fn):
    if isinstance(obj, dict):
        out, changed = {}, False
        for key, value in obj.items():
            out[key], c = _walk(value, fn)
            changed = changed or c
        return out, changed
    if isinstance(obj, list):
        out, changed = [], False
        for value in obj:
            nv, c = _walk(value, fn)
            out.append(nv)
            changed = changed or c
        return out, changed
    if isinstance(obj, str):
        new = fn(obj)
        return new, new != obj
    return obj, False


def _tokenize(rel: str, data: bytes, home: Path) -> bytes:
    """Capture-side transform: machine paths -> portable tokens.

    Interpreter normalization rides on JSON values only, where command fields
    (hooks, statusLine) live; collapse paths first so script paths are already
    tokenized when :func:`collapse_interpreter` looks for a command hint.
    """
    if not _is_text(data):
        return data
    text = data.decode("utf-8")
    if rel.endswith(".json"):
        new, changed = _transform_json(
            text, lambda s: collapse_interpreter(collapse_paths(s, home))
        )
    else:
        new = collapse_paths(text, home)
        changed = new != text
    return new.encode("utf-8") if changed else data


def _detokenize(rel: str, data: bytes, home: Path, sep: str, python: str) -> bytes:
    """Restore-side transform: portable tokens -> native values for this OS."""
    if not _is_text(data):
        return data
    text = data.decode("utf-8")
    if not any(t in text for t in (HOME_TOKEN, CLAUDE_TOKEN, PYTHON_TOKEN)):
        return data
    if rel.endswith(".json"):
        new, changed = _transform_json(
            text, lambda s: expand_interpreter(expand_paths(s, home, sep), python)
        )
    else:
        new = expand_paths(text, home, sep)
        changed = new != text
    return new.encode("utf-8") if changed else data


def create_zip(
    tracked: list[str],
    claude_dir: Path,
    snapshot_id: int,
    message: str,
) -> bytes:
    home = claude_dir.parent
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    files_included: list[str] = []
    buf = io.BytesIO()

    def add(src: Path) -> None:
        rel = src.relative_to(claude_dir).as_posix()
        if _is_excluded(rel):
            return
        payload = _tokenize(rel, src.read_bytes(), home)
        zf.writestr(rel, payload)
        files_included.append(rel)

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in tracked:
            src = claude_dir / entry.rstrip("/")
            if not src.exists():
                continue
            if src.is_dir():
                for child in sorted(src.rglob("*")):
                    if child.is_file():
                        add(child)
            else:
                add(src)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "id": snapshot_id,
            "timestamp": timestamp,
            "message": message,
            "machine": socket.gethostname(),
            "source_platform": platform.system().lower(),
            "source_home": HOME_TOKEN,
            "claude_cfg_version": __version__,
            "files": files_included,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()


def extract_zip(data: bytes, claude_dir: Path) -> list[str]:
    home = claude_dir.parent
    sep = "\\" if platform.system() == "Windows" else "/"
    python = resolve_python()
    buf = io.BytesIO(data)
    extracted: list[str] = []
    base = claude_dir.resolve()
    with zipfile.ZipFile(buf, mode="r") as zf:
        for name in zf.namelist():
            if name == "manifest.json":
                continue
            if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                raise ValueError(f"Refusing unsafe zip entry: {name!r}")
            dest = (claude_dir / name).resolve()
            try:
                dest.relative_to(base)
            except ValueError:
                raise ValueError(f"Refusing unsafe zip entry: {name!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_detokenize(name, zf.read(name), home, sep, python))
            extracted.append(name)
    return extracted


def read_manifest(data: bytes) -> dict:
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, mode="r") as zf:
        return json.loads(zf.read("manifest.json"))
