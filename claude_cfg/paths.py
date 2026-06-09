import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# Portable tokens. Stored snapshots use these instead of machine-specific
# absolute paths so a snapshot taken on one OS restores cleanly on any other.
HOME_TOKEN = "${HOME}"
CLAUDE_TOKEN = "${CLAUDE_HOME}"
# The python launcher a command spells differs by OS (``python`` on Windows,
# ``python3`` on macOS/most Linux). Snapshots store this neutral token and the
# restore resolves it to whatever actually exists on the target machine.
PYTHON_TOKEN = "${PYTHON}"

_PYTHON_CANDIDATES = ("python3", "python")


def resolve_python() -> str:
    """The python launcher to bake into restored commands on this machine.

    Prefers ``python3`` (POSIX and modern installs) and falls back to ``python``
    (typical on Windows). Defaults to ``python3`` if neither is on PATH, so a
    restored command is at least well-formed and fixable.
    """
    for candidate in _PYTHON_CANDIDATES:
        if shutil.which(candidate):
            return candidate
    return "python3"


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
    python: str  # python launcher available on this machine


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
        python=resolve_python(),
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


# A bare python launcher at the very start of a command: python, python3,
# python2, python3.11, optionally with a Windows .exe suffix. It must be
# followed by whitespace (i.e. it has arguments) so the lone word "python" in
# prose is never touched. Path-qualified interpreters (``/usr/bin/python3``, a
# venv path) are deliberately left alone — those are explicit, machine-specific
# choices we must not second-guess.
_PYTHON_LAUNCHER_RE = re.compile(
    r'^(\s*)python(?:[23](?:\.\d{1,2})?)?(?:\.exe)?(?=\s)',
    re.IGNORECASE,
)
# Only normalize when the command actually runs a script: a .py file, a path
# separator, or one of our path tokens appears. Keeps us off plain prose.
_SCRIPT_HINT_RE = re.compile(r'\.pyw?\b|[/\\]|\$\{(?:CLAUDE_HOME|HOME)\}')


def collapse_interpreter(value: str) -> str:
    """Capture-side: a leading bare ``python`` launcher -> ``${PYTHON}`` token.

    Run after :func:`collapse_paths`, so script paths are already tokenized and
    available as a hint that this string is a command rather than prose.
    """
    if not _SCRIPT_HINT_RE.search(value):
        return value
    return _PYTHON_LAUNCHER_RE.sub(lambda m: m.group(1) + PYTHON_TOKEN, value)


def expand_interpreter(value: str, python_cmd: str) -> str:
    """Restore-side: ``${PYTHON}`` token -> the launcher this machine has."""
    return value.replace(PYTHON_TOKEN, python_cmd)
