import io
import json
import platform
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from claude_cfg import __version__


def _slug(message: str) -> str:
    safe = "".join(c if c.isalnum() else "-" for c in message.lower())
    parts = [p for p in safe.split("-") if p]
    return "-".join(parts[:6])


def snapshot_key(snapshot_id: int, timestamp: str, message: str) -> str:
    ts = timestamp.replace(":", "").replace("-", "").replace("T", "T")[:15]
    slug = _slug(message) if message else "snapshot"
    return f"snapshots/{snapshot_id:03d}_{ts}_{slug}.zip"


def create_zip(
    tracked: list[str],
    claude_dir: Path,
    snapshot_id: int,
    message: str,
) -> bytes:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    files_included: list[str] = []
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in tracked:
            src = claude_dir / entry.rstrip("/")
            if not src.exists():
                continue
            if src.is_dir():
                for child in sorted(src.rglob("*")):
                    if child.is_file():
                        rel = child.relative_to(claude_dir).as_posix()
                        zf.write(child, rel)
                        files_included.append(rel)
            else:
                rel = src.relative_to(claude_dir).as_posix()
                zf.write(src, rel)
                files_included.append(rel)

        manifest = {
            "id": snapshot_id,
            "timestamp": timestamp,
            "message": message,
            "machine": socket.gethostname(),
            "platform": platform.system().lower(),
            "claude_cfg_version": __version__,
            "files": files_included,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()


def extract_zip(data: bytes, claude_dir: Path) -> list[str]:
    buf = io.BytesIO(data)
    extracted: list[str] = []
    with zipfile.ZipFile(buf, mode="r") as zf:
        for name in zf.namelist():
            if name == "manifest.json":
                continue
            dest = claude_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            extracted.append(name)
    return extracted


def read_manifest(data: bytes) -> dict:
    buf = io.BytesIO(data)
    with zipfile.ZipFile(buf, mode="r") as zf:
        return json.loads(zf.read("manifest.json"))
