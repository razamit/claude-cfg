# claude-cfg

> Versioned snapshot-based sync for [Claude Code](https://claude.com/claude-code) config files across machines.

[![CI](https://github.com/razamit/claude-cfg/actions/workflows/ci.yml/badge.svg)](https://github.com/razamit/claude-cfg/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/claude-cfg.svg)](https://pypi.org/project/claude-cfg/)
[![Python versions](https://img.shields.io/pypi/pyversions/claude-cfg.svg)](https://pypi.org/project/claude-cfg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`claude-cfg` is a small CLI that snapshots your `~/.claude/` directory — settings, `CLAUDE.md`, commands, skills, agents, plugins — and syncs the snapshots to a storage backend of your choice. Push from one machine, pull on another, and your Claude Code setup follows you.

It also scans tracked files for `~/.claude/<path>` references (e.g. a status-line command) and includes those automatically, so nothing referenced gets left behind.

---

## Features

- **Versioned snapshots** — every push gets an incrementing ID, timestamp, and message
- **Multiple backends** — Cloudflare R2, AWS S3, local folder (Dropbox/OneDrive/iCloud), GitHub Gist, SFTP
- **Auto-discovery** — referenced scripts (e.g. status-line commands) are picked up automatically
- **Safe pulls** — current config is backed up locally before any restore
- **Cross-platform** — Windows, macOS, Linux
- **No daemon, no server** — just push and pull when you want to

---

## Installation

```bash
pip install claude-cfg
```

To enable a remote backend, install the matching extra:

```bash
pip install "claude-cfg[s3]"     # AWS S3 / Cloudflare R2
pip install "claude-cfg[gist]"   # GitHub Gist
pip install "claude-cfg[sftp]"   # SFTP
pip install "claude-cfg[all]"    # everything
```

Requires Python 3.10+.

---

## Quick start

```bash
# 1. Configure interactively (pick a backend, enter credentials, choose tracked files)
claude-cfg init

# 2. Push your current config as snapshot #1
claude-cfg push "initial setup"

# On another machine, after running `claude-cfg init` with the same backend:
claude-cfg pull           # restore the latest snapshot
claude-cfg list           # see all snapshots
claude-cfg pull --point 3 # restore a specific snapshot
```

---

## Commands

| Command                       | What it does                                              |
| ----------------------------- | --------------------------------------------------------- |
| `claude-cfg init`             | Interactive setup — pick a backend, save config, push #1  |
| `claude-cfg push [message]`   | Snapshot the current `~/.claude/` and upload it           |
| `claude-cfg pull [--point N]` | Restore the latest snapshot (or `#N`) to `~/.claude/`     |
| `claude-cfg list`             | Show all snapshots with ID, timestamp, message, machine   |
| `claude-cfg config show`      | Print the current config (credentials masked)             |
| `claude-cfg config set K V`   | Update a config value, e.g. `claude-cfg config set r2.bucket my-bucket` |

---

## Backends

| Backend | Best for                                | Extra to install |
| ------- | --------------------------------------- | ---------------- |
| `local` | Dropbox / OneDrive / iCloud folder      | (built-in)       |
| `r2`    | Cloudflare R2 — free egress, S3 API     | `[s3]`           |
| `s3`    | AWS S3                                  | `[s3]`           |
| `gist`  | GitHub Gist (private, single-file ok)   | `[gist]`         |
| `sftp`  | Any SSH server                          | `[sftp]`         |

The `local` backend is the simplest path: point it at a folder inside Dropbox/OneDrive/iCloud and your snapshots sync to every machine for free.

---

## What gets tracked

By default:

```
settings.json
CLAUDE.md
commands/
skills/
agents/
plugins/
```

You can override this during `claude-cfg init` or by editing `~/.claude-cfg/config.json`. On push, `claude-cfg` also scans tracked files for `~/.claude/<path>` references and auto-includes any matching files (useful for status-line scripts and similar).

> **Security note**
>
> `settings.json` typically contains API keys and tokens. Snapshots are **not encrypted** — they're plain zips containing whatever is tracked. Only push to **private** backends (your own bucket, a private Gist, an SSH server you own). The `local` backend inside Dropbox/iCloud/OneDrive is fine since the underlying sync is encrypted in transit and access-controlled by your account. **Do not** push to a public S3 bucket or a public Gist.
>
> The `sftp` backend uses trust-on-first-use for host keys — fine for hosts you own on trusted networks, but be aware it can be MITM'd on first connection on a hostile network.

---

## How snapshots are stored

```
<backend root>/
├── index.json                                # list of all snapshots
└── snapshots/
    ├── 001_20260507T101530_initial-setup.zip
    ├── 002_20260507T143022_added-skill.zip
    └── ...
```

Each zip contains the tracked files plus a `manifest.json` with the snapshot ID, timestamp, machine name, and file list. `index.json` is the source of truth for what snapshots exist.

---

## Development

```bash
git clone https://github.com/razamit/claude-cfg.git
cd claude-cfg
pip install -e ".[dev]"
pytest
```

Tests run on Python 3.10/3.11/3.12 across Linux, macOS, and Windows in CI.

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.

---

## License

[MIT](LICENSE) © Amit Razam
