import json
import zipfile
from pathlib import Path

import pytest

from claude_cfg import snapshot as snap


@pytest.fixture
def fake_claude_dir(tmp_path):
    (tmp_path / "settings.json").write_text('{"theme": "dark"}')
    (tmp_path / "CLAUDE.md").write_text("# Instructions")
    cmds = tmp_path / "commands"
    cmds.mkdir()
    (cmds / "osint.md").write_text("# OSINT command")
    return tmp_path


def test_create_zip_includes_files(fake_claude_dir):
    tracked = ["settings.json", "CLAUDE.md", "commands/"]
    data = snap.create_zip(tracked, fake_claude_dir, snapshot_id=1, message="test")
    assert len(data) > 0

    import io
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    assert "settings.json" in names
    assert "CLAUDE.md" in names
    assert "commands/osint.md" in names
    assert "manifest.json" in names


def test_manifest_contents(fake_claude_dir):
    data = snap.create_zip(["settings.json"], fake_claude_dir, snapshot_id=3, message="hello")
    manifest = snap.read_manifest(data)
    assert manifest["id"] == 3
    assert manifest["message"] == "hello"
    assert "settings.json" in manifest["files"]
    assert "timestamp" in manifest
    assert "machine" in manifest


def test_extract_zip(fake_claude_dir, tmp_path):
    data = snap.create_zip(["settings.json", "CLAUDE.md"], fake_claude_dir, 1, "t")
    dest = tmp_path / "dest"
    dest.mkdir()
    extracted = snap.extract_zip(data, dest)
    assert "settings.json" in extracted
    assert (dest / "settings.json").read_text() == '{"theme": "dark"}'


def test_missing_tracked_file_skipped(fake_claude_dir):
    data = snap.create_zip(["nonexistent.json"], fake_claude_dir, 1, "t")
    manifest = snap.read_manifest(data)
    assert manifest["files"] == []


def test_snapshot_key_format():
    key = snap.snapshot_key(4, "2026-05-06T14:32:00Z", "added new OSINT skills")
    assert key.startswith("snapshots/004_")
    assert "added-new-osint" in key


def test_slug_truncation():
    msg = "one two three four five six seven eight"
    key = snap.snapshot_key(1, "2026-01-01T00:00:00Z", msg)
    slug_part = key.split("_", 2)[2].replace(".zip", "")
    assert slug_part.count("-") <= 5
