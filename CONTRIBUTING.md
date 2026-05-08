# Contributing to claude-cfg

Thanks for your interest in contributing! This is a small project, so the workflow is intentionally light.

## Reporting bugs

Open an [issue](https://github.com/razamit/claude-cfg/issues/new/choose) using the **Bug report** template. Please include:

- Your OS and Python version
- The `claude-cfg` version (`claude-cfg --version` or check `pyproject.toml`)
- The backend you're using
- Steps to reproduce
- What you expected vs. what happened
- Stack traces if any

## Suggesting features

Open an issue with the **Feature request** template. Explain the use case — "I want to do X because Y" beats "the tool should support X".

## Submitting code

1. **Fork** the repo and create a branch off `main`:
   ```bash
   git checkout -b feature/my-change
   ```
2. **Set up the dev environment**:
   ```bash
   pip install -e ".[dev]"
   ```
3. **Make your change.** Keep it focused — small, single-purpose PRs are merged faster.
4. **Add tests.** Every code change should come with a test that fails without it.
5. **Run the test suite**:
   ```bash
   pytest
   ```
6. **Update [CHANGELOG.md](CHANGELOG.md)** under `[Unreleased]` with a one-line entry.
7. **Open a pull request.** Fill in the PR template; link any related issues.

CI runs on Linux, macOS, and Windows across Python 3.10 / 3.11 / 3.12 — please make sure your change passes locally before pushing.

## Code style

- Follow the existing style of the file you're editing.
- Type hints are used throughout — please add them on new code.
- Keep public CLI behaviour and JSON formats backward-compatible. If you must break them, call it out in the PR description.
- No new runtime dependencies without a strong reason. Optional backends go behind extras (`[s3]`, `[gist]`, `[sftp]`).

## Questions

If you're not sure whether a change is wanted, open an issue to discuss before writing the code. Saves everyone time.

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
