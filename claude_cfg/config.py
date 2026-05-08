import json
import os
import platform
from pathlib import Path
from typing import Any

from claude_cfg.paths import config_file, config_dir

DEFAULT_TRACKED = [
    "settings.json",
    "CLAUDE.md",
    "commands/",
    "skills/",
    "agents/",
    "plugins/",
]

_MASKED_KEYS = {"access_key", "secret_key", "token", "password"}


def load() -> dict:
    path = config_file()
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Run `claude-cfg init` first."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save(cfg: dict) -> None:
    path = config_file()
    config_dir().mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    # Restrict to owner-only on POSIX; Windows ACLs already default to per-user.
    if platform.system() != "Windows":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def masked(cfg: dict) -> dict:
    """Return config with credential values replaced by '***'."""
    result = {}
    for k, v in cfg.items():
        if isinstance(v, dict):
            result[k] = {
                sk: "***" if sk in _MASKED_KEYS else sv
                for sk, sv in v.items()
            }
        else:
            result[k] = v
    return result


def set_value(key_path: str, value: Any) -> None:
    """Set a dot-separated key path in config. E.g. 'r2.bucket'."""
    cfg = load()
    parts = key_path.split(".")
    target = cfg
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
    save(cfg)


def validate(cfg: dict) -> None:
    storage = cfg.get("storage")
    if not storage:
        raise ValueError("Config missing 'storage' key.")
    valid = {"s3", "r2", "local", "gist", "sftp"}
    if storage not in valid:
        raise ValueError(f"Unknown storage backend: {storage!r}. Valid: {valid}")
