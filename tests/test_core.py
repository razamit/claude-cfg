import json
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_cfg import core
from claude_cfg.providers.base import StorageProvider


class MemoryProvider(StorageProvider):
    def __init__(self):
        self._store: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes) -> None:
        self._store[key] = data

    def download(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    def list_keys(self, prefix: str = "") -> list[str]:
        return [k for k in self._store if k.startswith(prefix)]

    def exists(self, key: str) -> bool:
        return key in self._store


@pytest.fixture
def fake_claude(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text('{"x": 1}')
    (claude / "CLAUDE.md").write_text("# Test")
    return claude


@pytest.fixture
def cfg(fake_claude):
    return {
        "storage": "local",
        "tracked": ["settings.json", "CLAUDE.md"],
    }


def test_push_creates_snapshot(cfg, fake_claude):
    provider = MemoryProvider()
    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        result = core.push("initial", cfg, provider)

    assert result["id"] == 1
    assert result["file_count"] == 2
    assert provider.exists("index.json")

    index = json.loads(provider.download("index.json"))
    assert len(index["snapshots"]) == 1
    assert index["snapshots"][0]["message"] == "initial"


def test_push_increments_id(cfg, fake_claude):
    provider = MemoryProvider()
    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        r1 = core.push("first", cfg, provider)
        r2 = core.push("second", cfg, provider)
    assert r1["id"] == 1
    assert r2["id"] == 2


def test_pull_restores_latest(cfg, fake_claude, tmp_path):
    provider = MemoryProvider()
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()

    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        core.push("snap1", cfg, provider)

    with (
        patch("claude_cfg.core.claude_dir", return_value=restore_dir),
        patch("claude_cfg.core._backup_current"),
    ):
        result = core.pull(None, cfg, provider)

    assert result["id"] == 1
    assert (restore_dir / "settings.json").exists()


def test_pull_by_id(cfg, fake_claude, tmp_path):
    provider = MemoryProvider()
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()

    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        core.push("first", cfg, provider)
        core.push("second", cfg, provider)

    with (
        patch("claude_cfg.core.claude_dir", return_value=restore_dir),
        patch("claude_cfg.core._backup_current"),
    ):
        result = core.pull(1, cfg, provider)

    assert result["id"] == 1
    assert result["message"] == "first"


def test_pull_invalid_id_raises(cfg, fake_claude):
    provider = MemoryProvider()
    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        core.push("snap", cfg, provider)

    with pytest.raises(ValueError, match="not found"):
        with patch("claude_cfg.core._backup_current"):
            core.pull(99, cfg, provider)


def test_pull_empty_backend_raises(cfg):
    provider = MemoryProvider()
    with pytest.raises(RuntimeError, match="No snapshots"):
        core.pull(None, cfg, provider)


def test_expand_referenced_files_picks_up_script(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"statusLine": {"command": "python ~/.claude/statusline-command.py"}}'
    )
    (tmp_path / "statusline-command.py").write_text("# script")

    tracked = ["settings.json"]
    result = core._expand_referenced_files(tracked, tmp_path)
    assert "statusline-command.py" in result


def test_expand_referenced_files_skips_missing(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"cmd": "~/.claude/ghost.py"}'
    )
    tracked = ["settings.json"]
    result = core._expand_referenced_files(tracked, tmp_path)
    assert "ghost.py" not in result


def test_expand_referenced_files_no_duplicates(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"cmd": "~/.claude/statusline-command.py"}'
    )
    (tmp_path / "statusline-command.py").write_text("# script")

    tracked = ["settings.json", "statusline-command.py"]
    result = core._expand_referenced_files(tracked, tmp_path)
    assert result.count("statusline-command.py") == 1


def test_push_includes_referenced_file(fake_claude, cfg):
    (fake_claude / "settings.json").write_text(
        '{"statusLine": {"command": "python ~/.claude/statusline-command.py"}}'
    )
    (fake_claude / "statusline-command.py").write_text("# script")

    provider = MemoryProvider()
    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        result = core.push("with script", cfg, provider)

    assert result["file_count"] == 3  # settings.json + CLAUDE.md + statusline-command.py


def test_list_snapshots_order(cfg, fake_claude):
    provider = MemoryProvider()
    with patch("claude_cfg.core.claude_dir", return_value=fake_claude):
        core.push("a", cfg, provider)
        core.push("b", cfg, provider)
        core.push("c", cfg, provider)

    snapshots = core.list_snapshots(provider)
    assert [s["id"] for s in snapshots] == [3, 2, 1]
