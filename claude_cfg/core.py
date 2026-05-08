import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from claude_cfg import snapshot as snap
from claude_cfg.paths import backups_dir, claude_dir
from claude_cfg.providers.base import StorageProvider

# Matches ~/.claude/<rel-path> in any string value — catches both / and \ separators
_CLAUDE_REF_RE = re.compile(r"~/\.claude[/\\]([\w./\\-]+)")

_INDEX_KEY = "index.json"


def _load_index(provider: StorageProvider) -> dict:
    if not provider.exists(_INDEX_KEY):
        return {"snapshots": []}
    return json.loads(provider.download(_INDEX_KEY))


def _save_index(provider: StorageProvider, index: dict) -> None:
    provider.upload(_INDEX_KEY, json.dumps(index, indent=2).encode())


def push(message: str, cfg: dict, provider: StorageProvider) -> dict:
    tracked: list[str] = cfg.get("tracked", [])
    source_dir = claude_dir()
    all_tracked = _expand_referenced_files(tracked, source_dir)

    index = _load_index(provider)
    snapshots = index["snapshots"]
    next_id = (snapshots[-1]["id"] + 1) if snapshots else 1

    zip_data = snap.create_zip(all_tracked, source_dir, next_id, message)
    manifest = snap.read_manifest(zip_data)
    key = snap.snapshot_key(next_id, manifest["timestamp"], message)

    provider.upload(key, zip_data)

    snapshots.append({
        "id": next_id,
        "timestamp": manifest["timestamp"],
        "message": message,
        "machine": manifest["machine"],
        "key": key,
    })
    _save_index(provider, index)

    return {
        "id": next_id,
        "timestamp": manifest["timestamp"],
        "key": key,
        "file_count": len(manifest["files"]),
        "size_bytes": len(zip_data),
    }


def pull(snapshot_id: int | None, cfg: dict, provider: StorageProvider) -> dict:
    index = _load_index(provider)
    snapshots = index["snapshots"]

    if not snapshots:
        raise RuntimeError("No snapshots found. Push first.")

    if snapshot_id is None:
        entry = snapshots[-1]
    else:
        matching = [s for s in snapshots if s["id"] == snapshot_id]
        if not matching:
            raise ValueError(
                f"Snapshot #{snapshot_id} not found. "
                f"Available: {[s['id'] for s in snapshots]}"
            )
        entry = matching[0]

    key = entry.get("key") or _find_key_by_id(provider, entry["id"])
    zip_data = provider.download(key)

    _backup_current(cfg)

    dest = claude_dir()
    extracted = snap.extract_zip(zip_data, dest)

    return {
        "id": entry["id"],
        "timestamp": entry["timestamp"],
        "message": entry.get("message", ""),
        "files_restored": len(extracted),
    }


def list_snapshots(provider: StorageProvider) -> list[dict]:
    index = _load_index(provider)
    return list(reversed(index["snapshots"]))


def _backup_current(cfg: dict) -> Path:
    source_dir = claude_dir()
    tracked = _expand_referenced_files(cfg.get("tracked", []), source_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dest = backups_dir() / ts
    backup_dest.mkdir(parents=True, exist_ok=True)

    for entry in tracked:
        src = source_dir / entry.rstrip("/")
        if not src.exists():
            continue
        dst = backup_dest / entry.rstrip("/")
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    return backup_dest


def _expand_referenced_files(tracked: list[str], source_dir: Path) -> list[str]:
    """Scan tracked files for ~/.claude/<path> references and add them."""
    extra: set[str] = set()
    base = source_dir.resolve()
    for entry in tracked:
        path = source_dir / entry.rstrip("/")
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in _CLAUDE_REF_RE.finditer(text):
            rel = match.group(1).replace("\\", "/")
            ref_path = (source_dir / rel).resolve()
            try:
                safe_rel = ref_path.relative_to(base)
            except ValueError:
                continue
            if ref_path.is_file():
                extra.add(safe_rel.as_posix())

    seen = set(tracked)
    return tracked + [r for r in sorted(extra) if r not in seen]


def _find_key_by_id(provider: StorageProvider, snapshot_id: int) -> str:
    prefix = f"snapshots/{snapshot_id:03d}_"
    keys = provider.list_keys("snapshots/")
    matches = [k for k in keys if k.startswith(prefix)]
    if not matches:
        raise FileNotFoundError(f"No snapshot zip found for id {snapshot_id}")
    return matches[0]
