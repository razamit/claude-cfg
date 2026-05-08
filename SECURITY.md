# Security Policy

## Supported versions

Only the latest released version of `claude-cfg` receives fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Email the maintainer at **razamit23@gmail.com** with:

- A description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- The version of `claude-cfg` and your environment

You can expect an initial response within 7 days. Once a fix is ready, a patch release will be published to PyPI and the advisory disclosed in the GitHub Security Advisories tab.

## Scope

In scope:
- Code execution, credential leakage, or path-traversal issues in `claude-cfg` itself
- Insecure handling of snapshots, configs, or backend credentials

Out of scope:
- Misuse of a backend you control (e.g. a public S3 bucket)
- Issues in upstream dependencies — please report those upstream

## Known limitations users should be aware of

- **Snapshots are not encrypted.** Tracked files (including `settings.json`) are stored as plain zips on the configured backend. Use a private backend.
- **Credentials are stored in plaintext** in `~/.claude-cfg/config.json`. On POSIX systems the file is `chmod 600` after writing; on Windows it relies on per-user profile ACLs.
- **The SFTP backend uses trust-on-first-use** for host keys (`AutoAddPolicy`). The first connection to a host could be MITM'd on a hostile network. Use only with hosts you control on trusted networks.
