import os
import platform
from pathlib import Path


def claude_dir() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ["USERPROFILE"]) / ".claude"
    return Path.home() / ".claude"


def config_dir() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ["USERPROFILE"]) / ".claude-cfg"
    return Path.home() / ".claude-cfg"


def config_file() -> Path:
    return config_dir() / "config.json"


def backups_dir() -> Path:
    return config_dir() / "backups"
