# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-06-09

### Added
- Interpreter normalization: a leading `python`/`python3` launcher in a tracked
  config command is stored as a neutral `${PYTHON}` token and resolved on restore
  to whichever launcher (`python3` preferred, then `python`) exists on the target
  machine. Fixes status-line / hook commands breaking when a snapshot spelled
  `python` is restored on a host that only has `python3` (e.g. macOS).
- `init` now detects existing snapshots on a configured backend and prompts to
  either push this machine or restore an existing snapshot, instead of always
  pushing.
- `pull` reports the backup directory and, on a cross-platform restore, the
  resolved python launcher.

### Changed
- Snapshot `schema_version` bumped to **3** (new snapshots embed the `${PYTHON}`
  token, which older readers would not expand). Restoring a v3 snapshot with an
  older `claude-cfg` is refused with a clear upgrade message.

## [0.1.0] - 2026-05-07

### Added
- Initial release of `claude-cfg`.
- `init`, `push`, `pull`, `list`, `config show`, `config set` commands.
- `--version` / `-V` flag.
- Storage backends: local folder, AWS S3, Cloudflare R2, GitHub Gist, SFTP.
- Versioned snapshots with monotonic IDs, ISO-8601 timestamps, and messages.
- Manifest-per-snapshot recording machine, platform, and file list.
- Auto-discovery of `~/.claude/<path>` references inside tracked files (e.g. status-line scripts).
- Safe-pull behaviour: current config is backed up to `~/.claude-cfg/backups/<ts>/` before restore.
- Credential masking in `config show` and `config set`.
- Config file `chmod 0600` on POSIX after writing.
- Cross-platform CI on Linux / macOS / Windows × Python 3.10 / 3.11 / 3.12 / 3.13.

### Security
- `extract_zip` rejects archive entries that escape the destination directory (zip slip).
- `_expand_referenced_files` rejects `~/.claude/<path>` references that resolve outside `~/.claude/`.

[Unreleased]: https://github.com/razamit/claude-cfg/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/razamit/claude-cfg/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/razamit/claude-cfg/releases/tag/v0.1.0
