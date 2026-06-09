import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path

# Portable tokens. Stored snapshots use these instead of machine-specific
# absolute paths so a snapshot taken on one OS restores cleanly on any other.
HOME_TOKEN = "${HOME}"
CLAUDE_TOKEN = "${CLAUDE_HOME}"


def _home() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("USERPROFILE") or Path.home())
    return Path.home()


def claude_dir() -> Path:
    return _home() / ".claude"


def config_dir() -> Path:
    return _home() / ".claude-cfg"


def config_file() -> Path:
    return config_dir() / "config.json"


def backups_dir() -> Path:
    return config_dir() / "backups"


@dataclass
class Target:
    """The machine a snapshot is being captured from or restored to."""

    platform: str  # win32 | darwin | linux
    home: Path
    claude_home: Path
    sep: str  # native path separator for shell-bound fields
    is_wsl: bool


def detect_target() -> Target:
    system = platform.system()
    if system == "Windows":
        plat, sep = "win32", "\\"
    elif system == "Darwin":
        plat, sep = "darwin", "/"
    else:
        plat, sep = "linux", "/"
    is_wsl = "microsoft" in platform.uname().release.lower()
    home = _home()
    return Target(
        platform=plat,
        home=home,
        claude_home=home / ".claude",
        sep=sep,
        is_wsl=is_wsl,
    )


# A path token is followed by its tail up to the next whitespace or quote.
_TAIL = r'([^\s"\'`]*)'


def collapse_paths(value: str, home: Path) -> str:
    """Replace machine-specific home/.claude paths with portable tokens.

    Matches absolute paths (either separator style), the ``~/.claude`` shortcut,
    and normalizes the captured tail to ``/`` so stored form is OS-neutral.
    """
    claude_home = home / ".claude"
    flags = re.IGNORECASE if os.name == "nt" else 0
    # Most specific first: .claude before the bare home it lives under.
    bases = [
        (str(claude_home), CLAUDE_TOKEN),
        (claude_home.as_posix(), CLAUDE_TOKEN),
        ("~/.claude", CLAUDE_TOKEN),
        (str(home), HOME_TOKEN),
        (home.as_posix(), HOME_TOKEN),
    ]
    out = value
    for base, token in bases:
        pattern = re.compile(re.escape(base) + _TAIL, flags)
        out = pattern.sub(lambda m: token + m.group(1).replace("\\", "/"), out)
    return out


def expand_paths(value: str, home: Path, sep: str) -> str:
    """Reverse of :func:`collapse_paths` against a target machine.

    Tokens become native absolute paths; tails are converted to ``sep`` so the
    result is valid on the restoring OS (backslashes on Windows, slashes else).
    """
    claude_home = str(home / ".claude")
    home_str = str(home)
    out = value
    for token, base in ((CLAUDE_TOKEN, claude_home), (HOME_TOKEN, home_str)):
        pattern = re.compile(re.escape(token) + _TAIL)
        out = pattern.sub(
            lambda m: base + (m.group(1) if sep == "/" else m.group(1).replace("/", sep)),
            out,
        )
    return out
