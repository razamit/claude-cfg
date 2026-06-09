# claude-cfg — Portability & Restore Spec

> Companion to `PLAN.md`. `PLAN.md` defines the storage layer (providers, snapshot zip, `index.json`, CLI). This file defines the layer above it: **what gets captured, how it is made platform-neutral, and how it is restored correctly on Windows, macOS, Linux, or WSL.**
> Drop this in the repo root and reference it from `CLAUDE.md` alongside `PLAN.md`.

---

## 1. Core principle

The tool must **never copy the whole `~/.claude/` folder**. It captures an explicit allowlist, classifies each entry, transforms platform-bound content into neutral form on capture, and reverses the transform on restore. Allowlist, not denylist: a denylist leaks new secret files the moment Claude Code adds one.

Three passes on capture: **collect -> classify -> transform-out (tokenize + redact)**.
Three passes on restore: **transform-in (expand + platform-select) -> merge -> validate**.

---

## 2. File taxonomy

Every candidate path falls into exactly one category. The category decides the handler.

| Category | Meaning | Handler on capture | Handler on restore |
|---|---|---|---|
| `verbatim` | Pure portable text/markdown, no paths, no platform deps | Copy bytes, hash | Write bytes |
| `tokenized` | Text containing absolute/home paths | Rewrite home paths to tokens, normalize separators to `/` | Expand tokens to target home, fix separators for shell fields |
| `extract` | A whitelisted subset pulled out of a larger machine-bound file | Pull only allowed keys, tokenize, redact | Merge subset into existing target file |
| `hooks` | Hook commands (the fragile part) | Detect platform deps, store per-platform variants or flag | Select target-platform variant, warn on flagged |
| `excluded` | Secrets, transient state, machine-bound history | Never captured | n/a |

### Default include set

```
verbatim:
  CLAUDE.md
  commands/**         (*.md)
  agents/**           (*.md)
  skills/**           (all files, including bundled scripts/assets)
  hooks/**            (script files, if hooks are externalized — see §6)

tokenized:
  settings.json
  settings.local.json   (optional, off by default: personal/experimental)

extract:
  ~/.claude.json        (global mcpServers ONLY — see §5)
```

### Default exclude set (never captured, even if present)

```
.credentials.json        secrets
projects/**              session history keyed by local path
todos/**                 transient
statsig/**               telemetry
shell-snapshots/**        machine state
ide/**                   editor binding
logs/**, *.log           noise
**/.DS_Store, **/Thumbs.db
```

Include/exclude are overridable in the config file (`include` / `exclude` glob arrays), but the four secret/state excludes above are **hard-locked** unless `--allow-unsafe` is passed.

---

## 3. Path tokenization

Three tokens, expanded at restore time against the target machine.

| Token | Meaning |
|---|---|
| `${HOME}` | User home directory |
| `${CLAUDE_HOME}` | The `.claude` directory root |
| `${PYTHON}` | The python launcher available on the target (`python3` preferred, then `python`) |

**Capture:** normalize the source home prefix (handle both `\` and `/`), replace any literal occurrence with the token, and store all stored-form paths with `/` separators. A Windows value `C:\\Users\\amit\\.claude\\hooks\\guard.py` becomes `${CLAUDE_HOME}/hooks/guard.py`. A leading bare `python`/`python3` launcher in a JSON command value becomes `${PYTHON}` (path-qualified interpreters are left alone).

**Restore:** expand tokens to the target home. JSON config values can stay `/` on all three OSes. Fields that are handed to a shell (hook commands, MCP `command`/`args`) get separators converted to the native form for the target platform. `${PYTHON}` resolves to whichever launcher exists on the target, fixing the common `python` (Windows) vs `python3` (macOS/Linux) mismatch.

Implement `collapse_paths(text, home)` / `expand_paths(text, home)` and `collapse_interpreter(text)` / `expand_interpreter(text, python_cmd)` in `paths.py`.

---

## 4. settings.json handling (`tokenized`)

1. Parse as JSON (fail the entry cleanly if it does not parse).
2. Walk all string values; tokenize any that contain the source home prefix.
3. Route the `hooks` subtree to the hook handler (§6) rather than treating it as plain text.
4. Drop nothing else: permissions, model, env keys are portable.

---

## 5. ~/.claude.json handling (`extract`)

`~/.claude.json` is a **sibling file**, not inside `~/.claude/`. It is large and mostly machine-bound (oauth account, project trust list keyed by absolute path, tips history, telemetry). Capture **only** the global `mcpServers` map. Do not capture `projects[*]` — project-scoped MCP belongs in each repo's `.mcp.json`, which travels with the repo.

For each captured server:
- Tokenize any paths in `command` and `args`.
- Classify the launcher: `npx` / `node` / `python` / `python3` / absolute binary. Record it; an absolute binary path is flagged `needs_review` since it rarely survives a platform move.
- **Strip every value under `env`.** Replace with an `${ENV:VAR_NAME}` placeholder. The actual value is resolved from the target environment on restore and is **never stored** (see §7).

Restore **merges** these servers into the existing target `~/.claude.json`. It must not overwrite the file (local oauth/project state has to survive).

---

## 6. Hook portability (the hard layer)

Hooks are where a naive copy breaks, especially a PreToolUse hard-enforcement layer. Three strategies, in order of preference. The tool supports all three and picks per hook.

**A. Externalize (preferred).** Hook logic lives in a script file under `~/.claude/hooks/`, which syncs as `verbatim`/`tokenized`. The hook `command` is a thin, neutral invocation. Recommend authoring hooks this way. The doc's `init`/`doctor` step can offer to extract inline hook bodies into script files.

**B. Per-platform variants.** Store `command` as a map keyed by platform. The manifest carries all variants; restore selects the target one.

```json
{
  "command": {
    "win32":  "python %CLAUDE_HOME%\\hooks\\guard.py",
    "darwin": "python3 ${CLAUDE_HOME}/hooks/guard.py",
    "linux":  "python3 ${CLAUDE_HOME}/hooks/guard.py"
  }
}
```

**C. Flag and warn.** If a command cannot be classified as portable and has no variant, mark the entry `needs_review: true`. Restore still writes it but emits a warning and leaves the original alongside.

### Portability linter (run during capture)

Scan every hook command. Non-portable signals:
- `C:\`, drive letters, backslash path separators
- `%USERPROFILE%`, `%APPDATA%`, other `%VAR%` Windows expansions
- `.bat`, `.cmd`, `powershell`, `pwsh -Command`
- bare `python ` (ambiguous; prefer `python3` on mac/linux)
- absolute interpreter or binary paths

A hit downgrades the hook from portable to `needs_review` unless a per-platform variant covers it. Normalize `python` <-> `python3` and separators automatically where the rest of the command is otherwise portable.

---

## 7. Secret redaction (mandatory, because of the Gist backend)

The Gist provider can target a public gist. Treat the snapshot as potentially world-readable.

Rules:
- `.credentials.json` is excluded by category and never enters a bundle. Full stop.
- A redaction pass runs over **all** payload bytes before the zip is assembled.
- Patterns to catch: `sk-`, `ghp_`/`gho_`/`github_pat_`, AWS `AKIA…`, `Bearer ` tokens, long base64/hex blobs, and any value under an MCP `env` key.
- On hit: replace with `${ENV:NAME}` placeholder and record the placeholder in the manifest.
- Default behavior on an unredactable secret is to **fail the push** with a clear message. `--allow-secrets` overrides for the local/SFTP/private-R2 case only; the tool refuses `--allow-secrets` when the target provider is `gist`.

On restore, `${ENV:NAME}` placeholders resolve from the target environment. If a referenced variable is unset, restore proceeds and lists the missing variables in the final report rather than failing.

---

## 8. Snapshot manifest (extends PLAN.md schema)

Keep the existing zip + `index.json`. Add a per-snapshot `manifest.json` (schema v3):

```json
{
  "schema_version": 3,
  "created_at": "2026-06-09T10:00:00Z",
  "claude_cfg_version": "x.y.z",
  "source_platform": "win32",
  "source_home": "${HOME}",
  "entries": [
    { "path": "commands/review.md", "category": "verbatim", "sha256": "…" },
    { "path": "settings.json", "category": "tokenized", "sha256": "…",
      "transforms": ["paths", "hooks"] },
    { "path": "claude.json#/mcpServers", "category": "extract", "sha256": "…",
      "transforms": ["paths", "redact"] }
  ],
  "hooks": [
    { "id": "PreToolUse[0]", "strategy": "variants",
      "platforms": ["win32","darwin","linux"], "needs_review": false }
  ],
  "redaction": { "scanned": true, "placeholders": ["ENV:OPENAI_API_KEY"] }
}
```

Restore refuses a bundle whose `schema_version` is newer than the running tool supports, and warns (does not refuse) on older versions.

---

## 9. Capture algorithm

```
1. home, claude_home = resolve_claude_home()          # paths.py
2. rules = load_manifest(config.include, config.exclude)
3. files = glob(rules) under claude_home (+ ~/.claude.json for extract)
4. for f in files: category = classify(f)
5. for f in files: entry, payload = HANDLERS[category](f, home)
6. payload = redact(payload)                           # fail or placeholder
7. bundle = zip(payload_files + manifest.json)
8. provider.push(bundle, name)                         # existing layer
```

## 10. Restore algorithm

```
1. bundle = provider.pull(name)                        # existing layer
2. manifest = read_manifest(bundle); assert_schema_compatible()
3. plat, home, claude_home, cred = detect_target()     # paths.py
4. if not --no-backup: backup(claude_home -> claude_home.bak.<ts>)
5. for entry in manifest.entries:
     RESTORE[entry.category](entry, home, plat)
       verbatim  -> write bytes
       tokenized -> expand_paths(); fix separators on shell fields
       extract   -> merge mcpServers into ~/.claude.json (preserve local state);
                    resolve ${ENV:*} from environment
       hooks     -> pick plat variant; if needs_review, write + warn
6. validate(): JSON-parse settings.json + ~/.claude.json
7. report(): re-auth needed (§11), unset ${ENV:*} vars, flagged hooks
8. exit nonzero if validate() failed (backup already exists)
```

`--dry-run` runs steps 1 to 5 as a plan print with zero writes.

---

## 11. Platform resolution table

| Platform | `.claude` root | Credentials store | Native separator | Re-auth on restore |
|---|---|---|---|---|
| `win32` | `%USERPROFILE%\.claude` | `.credentials.json` (DPAPI-protected) | `\` | Yes |
| `darwin` | `~/.claude` | login Keychain entry "Claude Code" | `/` | Yes |
| `linux` | `~/.claude` | `~/.claude/.credentials.json` | `/` | Yes |
| WSL | `~/.claude` (Linux home) | `~/.claude/.credentials.json` | `/` | Yes |

Credentials are excluded from every snapshot, so **restore always ends with "run `claude` and re-authenticate."** WSL detection: `platform.uname().release` contains `microsoft`. Treat WSL as linux but warn if the user appears to also run a Windows-native install, since the two homes diverge.

---

## 12. Merge and conflict policy

- `verbatim` / `tokenized` files are owned by the snapshot: overwrite, but only after the timestamped backup in restore step 4.
- `~/.claude.json` is **always merged**, never overwritten. Only the captured global `mcpServers` keys are set; everything else in the target file is preserved.
- CLI flag `--on-conflict overwrite|merge|skip` (default `overwrite` for files, `merge` is forced for `~/.claude.json` regardless).

---

## 13. Module touch-points

| File | Add |
|---|---|
| `paths.py` | `detect_target()`, `resolve_claude_home()`, `collapse_paths()`, `expand_paths()`, credential-mechanism lookup |
| `snapshot.py` | `classify()`, category handlers, manifest v2 read/write, `redact()` |
| `portability.py` (new) | hook linter + variant builder, `${ENV:*}` placeholder logic, secret patterns |
| `core.py` | wire capture and restore pipelines onto the providers |
| `cli.py` | flags `--dry-run`, `--on-conflict`, `--no-backup`, `--allow-secrets`; new `doctor` command (validate config + lint hooks + dry-run a capture) |
| config schema | `include`, `exclude`, `redaction` policy, `env_passthrough` list |

---

## 14. Implementation order (extends PLAN.md step list)

1. `classify()` + the include/exclude default manifest (pure, testable).
2. `collapse_paths()` / `expand_paths()` + `detect_target()` in `paths.py`.
3. `verbatim` and `tokenized` handlers end to end against the local provider.
4. `redact()` + secret-pattern tests (assert no secret survives a round trip).
5. `extract` handler for `~/.claude.json` global mcpServers, with merge-on-restore.
6. Hook linter + per-platform variants + `needs_review` flagging.
7. `--dry-run`, backup, `--on-conflict`, validation report.
8. `doctor` command.
9. Cross-platform round-trip tests (synthesize win32/darwin/linux homes in fixtures).

---

## 15. Edge cases / FAQ

- **Credentials never sync.** Every restore prompts re-auth. This is by design, not a gap.
- **macOS uses Keychain, not a file.** Do not attempt to write credentials; just tell the user to re-run `claude`.
- **Project history is not portable** and is excluded. It is keyed by URL-encoded local path and will not map across machines.
- **Symlinks** in `commands/`/`skills/`: resolve to real files on capture and store as files; warn so the user knows the link was flattened.
- **Binary assets inside skills** copy verbatim as files. Add a per-entry size guard (warn above, say, 5 MB) to catch accidental large blobs.
- **`settings.local.json`** is personal/experimental, off by default. Include it explicitly only if the user wants their local overrides to travel.
- **Mixed Windows-native + WSL** on one machine: two separate `.claude` homes. Document that they are distinct snapshot targets.
