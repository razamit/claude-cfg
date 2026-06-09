import io
import json
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from claude_cfg import snapshot as snap
from claude_cfg.paths import collapse_paths, expand_paths


# --- pure tokenization (cross-platform, separator-agnostic) -----------------

def test_collapse_windows_path():
    home = PureWindowsPath(r"C:\Users\amit")
    value = r"python C:\Users\amit\.claude\hooks\guard.py --flag"
    assert collapse_paths(value, home) == "python ${CLAUDE_HOME}/hooks/guard.py --flag"


def test_collapse_posix_and_tilde():
    home = PurePosixPath("/home/bob")
    assert collapse_paths("/home/bob/.claude/x.py", home) == "${CLAUDE_HOME}/x.py"
    assert collapse_paths("~/.claude/x.py", home) == "${CLAUDE_HOME}/x.py"
    assert collapse_paths("/home/bob/Documents", home) == "${HOME}/Documents"


def test_roundtrip_windows_to_linux():
    stored = collapse_paths(
        r"python C:\Users\amit\.claude\hooks\guard.py", PureWindowsPath(r"C:\Users\amit")
    )
    assert stored == "python ${CLAUDE_HOME}/hooks/guard.py"
    restored = expand_paths(stored, PurePosixPath("/home/bob"), "/")
    assert restored == "python /home/bob/.claude/hooks/guard.py"


def test_roundtrip_linux_to_windows():
    stored = collapse_paths(
        "python /home/bob/.claude/hooks/guard.py", PurePosixPath("/home/bob")
    )
    assert stored == "python ${CLAUDE_HOME}/hooks/guard.py"
    restored = expand_paths(stored, PureWindowsPath(r"C:\Users\amit"), "\\")
    assert restored == r"python C:\Users\amit\.claude\hooks\guard.py"


def test_no_paths_unchanged():
    home = PurePosixPath("/home/bob")
    assert collapse_paths("just some prose", home) == "just some prose"


# --- snapshot integration ---------------------------------------------------

def _zip_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.namelist()


def _zip_text(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(name).decode("utf-8")


def test_settings_path_roundtrip(tmp_path):
    src = tmp_path / "home1" / ".claude"
    (src / "hooks").mkdir(parents=True)
    (src / "hooks" / "guard.py").write_text("# guard")
    settings = {"hooks": {"PreToolUse": [{"command": f"python {src / 'hooks' / 'guard.py'}"}]}}
    (src / "settings.json").write_text(json.dumps(settings))

    data = snap.create_zip(["settings.json"], src, 1, "t")
    stored = _zip_text(data, "settings.json")
    assert "${CLAUDE_HOME}" in stored
    assert str(src) not in stored

    dst = tmp_path / "home2" / ".claude"
    dst.mkdir(parents=True)
    snap.extract_zip(data, dst)
    restored = json.loads((dst / "settings.json").read_text())
    cmd = restored["hooks"]["PreToolUse"][0]["command"]
    assert str(dst) in cmd
    assert "home1" not in cmd


def test_token_free_json_kept_verbatim(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    raw = '{"theme": "dark"}'
    (claude / "settings.json").write_text(raw)
    data = snap.create_zip(["settings.json"], claude, 1, "t")
    # Untouched files keep byte-for-byte formatting (no needless reserialization).
    assert _zip_text(data, "settings.json") == raw


def test_excluded_files_skipped(tmp_path):
    claude = tmp_path / ".claude"
    (claude / "skills").mkdir(parents=True)
    (claude / "skills" / "real.md").write_text("# skill")
    (claude / "skills" / "debug.log").write_text("noise")
    (claude / "skills" / ".DS_Store").write_bytes(b"\x00\x01")
    (claude / ".credentials.json").write_text('{"token": "secret"}')
    (claude / "projects").mkdir()
    (claude / "projects" / "x.json").write_text("{}")

    data = snap.create_zip(
        ["skills/", ".credentials.json", "projects/"], claude, 1, "t"
    )
    names = _zip_names(data)
    assert "skills/real.md" in names
    assert "skills/debug.log" not in names
    assert "skills/.DS_Store" not in names
    assert ".credentials.json" not in names
    assert all(not n.startswith("projects/") for n in names)


def test_plugin_caches_and_clones_excluded(tmp_path):
    claude = tmp_path / ".claude"
    plugins = claude / "plugins"
    plugins.mkdir(parents=True)
    # Portable manifests — kept.
    (plugins / "installed_plugins.json").write_text("{}")
    (plugins / "known_marketplaces.json").write_text("{}")
    # Re-fetchable trees — dropped.
    (plugins / "cache" / "a").mkdir(parents=True)
    (plugins / "cache" / "a" / "big.js").write_text("x")
    (plugins / "marketplaces" / "m" / ".git").mkdir(parents=True)
    (plugins / "marketplaces" / "m" / ".git" / "HEAD").write_text("ref")
    (plugins / "marketplaces" / "m" / "plugin.md").write_text("# p")

    data = snap.create_zip(["plugins/"], claude, 1, "t")
    names = _zip_names(data)
    assert "plugins/installed_plugins.json" in names
    assert "plugins/known_marketplaces.json" in names
    assert all(not n.startswith("plugins/cache/") for n in names)
    assert all(not n.startswith("plugins/marketplaces/") for n in names)


def test_nested_git_and_node_modules_excluded(tmp_path):
    claude = tmp_path / ".claude"
    skills = claude / "skills"
    (skills / "tool" / ".git").mkdir(parents=True)
    (skills / "tool" / ".git" / "config").write_text("x")
    (skills / "tool" / "node_modules" / "dep").mkdir(parents=True)
    (skills / "tool" / "node_modules" / "dep" / "index.js").write_text("x")
    (skills / "tool" / "skill.md").write_text("# real")

    names = _zip_names(snap.create_zip(["skills/"], claude, 1, "t"))
    assert "skills/tool/skill.md" in names
    assert all("/.git/" not in n and "/node_modules/" not in n for n in names)


def test_manifest_schema_v2(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# hi")
    manifest = snap.read_manifest(snap.create_zip(["CLAUDE.md"], claude, 1, "t"))
    assert manifest["schema_version"] == 2
    assert "source_platform" in manifest
    assert manifest["source_home"] == "${HOME}"


def test_binary_asset_untouched(tmp_path):
    claude = tmp_path / ".claude"
    (claude / "skills").mkdir(parents=True)
    blob = bytes(range(256))
    (claude / "skills" / "logo.png").write_bytes(blob)
    data = snap.create_zip(["skills/"], claude, 1, "t")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert zf.read("skills/logo.png") == blob
