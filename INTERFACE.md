# Releaser CLI Interface (Phase 1)

Scope: CLI-first design for easy version bumping and basic configuration, including an `init` command that saves defaults to repo-level and/or host-level (`~/.releaser`). Python API details are deferred to a later phase.

## Goals

- Make version bumps one-liners (auto or manual).
- Follow Conventional Commits for automatic bumping.
- Support writing versions to common places (pyproject, __init__.py), and sync extra version targets.
- Provide dry-run, commit+tag, and push options with predictable results.
 - Keep CLI-focused; Python API can come later.

## Versioning Rules (Conventional Commits)

- `BREAKING CHANGE` (or `!` after type/scope) → major bump.
- `feat:` → minor bump.
- Everything else (e.g., `fix:`, `chore:`, `docs:`) → patch bump.
- Existing behavior: last tag is the base; if no tag, start from `0.0.1`.
- Tag prefix defaults to `v` (customizable).

---

## CLI Overview

Commands in this phase:
- `releaser init` Initialize configuration (repo-level and/or host-level).
- `releaser bump` Bump version (auto/manual), write targets, commit, tag, and optionally push.

Configuration sources and precedence:
1) CLI flags
2) Environment variables
3) Repo config: `./.releaser.toml` (or `./.releaser/config.toml`)
4) Host config: `~/.releaser/config.toml`
5) Built-in defaults

---

## CLI: init

Purpose: Create a configuration file with sensible defaults and provider selection for this project and/or this host.

Usage:
- `releaser init` (interactive; writes `./.releaser.toml`)
- `releaser init --global` (interactive; writes `~/.releaser/config.toml`)
- `releaser init --path PATH` (non-default location)
- `releaser init --yes` (accept defaults; non-interactive)

Key prompts (interactive):
- Project type: `auto | poetry | setuptools | npm`
- Tag prefix: default `v`
- Use native tooling if available: `true/false` (e.g., `poetry version`, `npm version`)
- Version write targets (comma-separated):
  - `pyproject.toml:project.version`
  - `package/__init__.py:__version__`
  - `package.json:json(version)` (implied for npm)
- Default behavior: commit/tag/push booleans
 - Pre-release defaults:
   - Enable pre-release flow by default? `[y/N]` (default: N)
   - Default pre-release channel `[alpha/beta/rc/custom]` (default: rc)
   - Auto-increment pre-release number? `[Y/n]` (default: Y)
   - Reset pre-release number when base version changes? `[Y/n]` (default: Y)

Flags:
- `--project-type` Force provider type
- `--tag-prefix` Default tag prefix
- `--use-native/--no-native` Prefer native ecosystem command
- `--files` One or more `PATH[:selector]` entries to prefill (writes to `version_targets` in config)
- `--commit/--no-commit` Default commit behavior
- `--tag/--no-tag` Default tag behavior
- `--push/--no-push` Default push behavior

Generated files:
- Repo: `./.releaser.toml` (preferred) or `./.releaser/config.toml`
- Host: `~/.releaser/config.toml` inside directory `~/.releaser/`

Sample generated `.releaser.toml`:

```toml
[project]
type = "auto"            # auto|poetry|setuptools|npm
tag_prefix = "v"
use_native = true

[version]
strategy = "auto"         # auto|manual
since = ""               # default: last tag
to = "HEAD"

[pre_release]
enabled = false
default_channel = "rc"   # alpha|beta|rc|custom
auto_increment = true
reset_on_bump = true
apply = ["release/*", "develop"]
block = ["main", "master"]
channel_map = { develop = "alpha" }

[bump_rules]
apply = ["develop", "release/*"]
block = ["main", "master"]

version_targets = [
  "pyproject.toml:project.version",
  "pkg/__init__.py:__version__",
]

[defaults]
commit = true
tag = true
push = false
```

---

## CLI: bump

Purpose: Compute the next version (auto/manual), write it to configured targets, optionally commit+tag+push.

Usage:
- `releaser bump` (interactive by default; uses config for defaults)

Interactive flow (default):
- Pre-check: if current branch is disallowed by `[bump_rules]`, show the reason and exit.
- Shows detected provider, current version, and last tag.
- Prompt 1 — Select bump type (shows computed targets):
  - Patch → vX.Y.(Z+1)
  - Minor → vX.(Y+1).0
  - Major → v(X+1).0.0
  - Manual → enter exact version
  - Cancel
  - Note: One option may be marked “recommended” based on commit history, but you always choose.
- Prompt 2 — Release line:
  - Stable release [default]
  - Pre-release (uses configured channel; auto-increments when enabled)
    - Option is disabled with a reason if branch rules disallow (global off, blocked branch, or not in apply list)
  - Finalize pre-release to stable (shown only if current is pre-release)
- Prompt 3 — Actions (pre-filled from `[defaults]`):
  - Commit? [Y/n]
  - Tag? [Y/n]
  - Push? [y/N]
- Prompt 4 — Release notes:
  - None [default]
  - Write notes (opens $EDITOR; multi-line). Notes go into commit body and annotated tag.
  - Read notes from file path
  - Optionally update changelog (asks: Update CHANGELOG.md? [y/N], path default: `CHANGELOG.md`)
- Summary + Confirm to proceed. `--dry-run` shows the same wizard but applies nothing.

Minimal flags (Phase 1):
- `--manual VERSION` Set an exact version (bypasses auto bump)
- `--type {major,minor,patch}` Force bump type (overrides auto)
- `--pre` Use pre-release flow based on config (e.g., -rc.N)
- `--finalize` Convert pre-release to stable (drop suffix)
- `--dry-run` Preview without any changes
- `--version-source {file,local_tag,remote_tag,auto}` Choose how to resolve the current version used as the bump base. `file` reads from project files (default), `local_tag` uses the latest local tag, `remote_tag` uses the latest tag on the Git remote, `auto` picks the newer of file vs latest tag.
- `--push` Push after commit/tag (overrides config default)
- `--no-commit` Do not create a commit
- `--no-tag` Do not create a tag
- `--config PATH` Use a specific config file

Release notes flags (optional):
- `--notes TEXT` Provide release notes directly (multi-line supported via `\n`)
- `--notes-file PATH` Read release notes from a file
- `--changelog` Append notes to `CHANGELOG.md` under the new version heading
- `--changelog-file PATH` Path to changelog (default: `CHANGELOG.md`)

Pre-release flag enforcement:
- `--pre` obeys branch rules. If disallowed, exits non-zero with a clear message, e.g.:
  "Pre-release is disabled on branch 'main' by pre_release.block rule"

Bump flag enforcement:
- Command obeys `[bump_rules]`. If disallowed, exits non-zero with a clear message, e.g.:
  "Bump is disabled on branch 'main' by bump_rules.block rule"

Examples:
- Stable auto bump (guided): `releaser bump`
- Pre-release bump: `releaser bump --pre`
- Finalize pre-release: `releaser bump --finalize`
- Force minor and push: `releaser bump --type minor --push`
- Manual version without tagging: `releaser bump --manual 1.4.0 --no-tag`
- Use specific config: `releaser bump --config .releaser.toml`

Exit codes:
- `0` success; `>0` for validation/IO/git errors.

Output:
- Human: current version, bump reason, new version, targets written, commit/tag/push result; in `--dry-run`, shows plan only.

---

## Best Options With Config Present

When a `.releaser.toml` (or `~/.releaser/config.toml`) is present, the simplest and most reliable flows are:

- Stable release (recommended default)
  - Command: `releaser bump`
  - Behavior: loads config → auto-detect provider → determines bump from commits → writes configured version targets (and native tool if enabled) → commit → tag → optional push (per `[defaults]`).

- Start or continue pre-release
  - Command: `releaser bump --pre`
  - Behavior: same as above, but appends the configured channel (e.g., `-rc.N`). If the previous version is already a pre-release with the same channel, increments `N` when `auto_increment = true`.

- Finalize a pre-release to stable
  - Command: `releaser bump --finalize`
  - Behavior: converts `X.Y.Z-rc.N` to `X.Y.Z` without re-evaluating commit history. Useful after testing RC builds.

- Quick preview
  - Command: `releaser bump --dry-run`
  - Behavior: prints the detected provider, chosen bump type, target version, version targets to update, and git actions—without making changes.

Notes:
- CLI flags always override config. For example, `--no-commit`, `--no-tag`, `--push`, `--pre-channel`, or `--tag-prefix` take precedence.
- Current version resolution can be configured under `[release.version]` using `source = "file|local_tag|remote_tag|auto"`. The default is `file`. When using tag-based sources, tag prefix from `[project].tag_prefix` is respected and stripped from the version value.
- Providers follow config: if `use_native = true`, native commands are preferred (e.g., `npm version`, `poetry version`), and file targets are then synced.
- Git range uses config `[version] since/to` when set; otherwise defaults to “since last tag … to HEAD”.

Recommended defaults in config for most teams:
- `[project] use_native = true` and a `tag_prefix = "v"`.
- `[version] strategy = "auto"`.
- `[defaults] commit = true, tag = true, push = false` (push explicitly when ready).
- `[pre_release] enabled = false` unless you regularly cut RCs; then set `enabled = true` and use `--finalize` for stable.

Cheat sheet:
- Stable: `releaser bump`
- Pre-release: `releaser bump --pre`
- Finalize: `releaser bump --finalize`
- Preview only: `releaser bump --dry-run`

---

## Configuration Examples

Minimal auto-detect (Poetry/Setuptools/NPM) with sane defaults:

```toml
# .releaser.toml
[project]
type = "auto"
tag_prefix = "v"
use_native = true

[version]
strategy = "auto"
since = ""
to = "HEAD"

[pre_release]
enabled = false
default_channel = "rc"
auto_increment = true
reset_on_bump = true

version_targets = [
  "pyproject.toml:project.version",
]

[defaults]
commit = true
tag = true
push = false
```

<!-- Provider-specific examples removed to reduce redundancy. Use minimal config and override with flags when needed. -->

Global defaults (host-level) at `~/.releaser/config.toml`:

```toml
[defaults]
commit = true
tag = true
push = false

# Optional global project defaults
[project]
tag_prefix = "v"
use_native = true
```

<!-- Hooks and extra pre-release examples removed for brevity; see main config spec above. -->


## Notes on Backward Compatibility

- `releaser draft` remains available and can later be wired to use the same configuration and bumping logic. No changes required in this phase.

---

## Multi‑Project Providers (Poetry, Setuptools, NPM)

To support different ecosystems out of the box, we introduce a provider abstraction with auto‑detection and configuration. Providers encapsulate how to read/write the current version and optionally use native tooling.

### Detection

- Poetry: `pyproject.toml` with `[project] version` or `[tool.poetry]`.
- Setuptools: `setup.cfg` (`[metadata] version`), `setup.py`, or `__init__.__version__` patterns.
- NPM: `package.json` with `version` field.
- Fallback: configured `version_targets` selectors or defaults.

### Provider Capabilities

- Read current version.
- Write new version (file edits and/or native commands).
- Optional native bump hooks (e.g., `npm version`, `poetry version`).
- Return detailed `FileUpdate` records for transparency.

### CLI Additions

- `--project-type auto|poetry|setuptools|npm` Force or auto detect provider (default: `auto`).
- `--config PATH` Path to config file (default: `.releaser.toml` if present).
- `--use-native/--no-native` Prefer native ecosystem command when available (default: try native, fall back to version_targets).
- `--workspace` For NPM monorepos (planned; see Roadmap).

Examples:
- `releaser bump --project-type poetry` → edits via Poetry provider (prefers `poetry version`).
- `releaser bump --project-type npm --no-native` → updates `package.json` directly.
- `releaser bump --config .releaser.toml --push` → uses config for targets and behavior.

### Config

Use the canonical `.releaser.toml` format defined above (sample + minimal examples). Providers honor:
- `[project]` keys: `type`, `tag_prefix`, `use_native`
- `[version]` keys: `strategy`, `since`, `to`
- `[pre_release]` keys: `enabled`, `default_channel`, `auto_increment`, `reset_on_bump`
- `version_targets` for syncing versions across files

Resolution order when `--project-type=auto`:
- Poetry → Setuptools → NPM → Fallback

Provider behavior in `bump`:
- Provider is selected (or forced) to read and write versions. If `--use-native`, run native commands (e.g., `npm version`, `poetry version`) and then sync file targets.

#### Minimal Parameters Used (Phase 1)

For the first implementation, the CLI reads only a minimal subset of config keys; other keys may be present but are ignored.

- `[project]`: `type`, `tag_prefix`, `use_native`
- `version_targets`: list of write targets (optional; provider defaults apply if omitted)
- `[defaults]`: `commit`, `tag`, `push`
- `[bump_rules]`: `apply`, `block` (optional) — controls whether bump is allowed on a branch
- `[pre_release]`: `enabled`, `default_channel` (optional), `apply`, `block`, `channel_map`

Ignored in Phase 1: `[version]` (e.g., `since`, `to`, `strategy`), provider‑specific blocks, and hooks. Git range defaults to “since last tag … to HEAD”.

Defaults when keys are missing:
- `project.type = "auto"`
- `project.tag_prefix = "v"`
- `project.use_native = true`
- `version_targets = []` (provider chooses sensible defaults)
- `defaults.commit = true`, `defaults.tag = true`, `defaults.push = false`
- `pre_release.enabled = false`, `pre_release.default_channel = "rc"`
- `pre_release.apply = []`, `pre_release.block = []`, `pre_release.channel_map = {}`
- `bump_rules.apply = []`, `bump_rules.block = []`

Minimal config example (everything else uses defaults):

```toml
[project]
type = "auto"
tag_prefix = "v"
use_native = true

[defaults]
commit = true
tag = true
push = false

# Optional: explicitly set pre-release defaults
[pre_release]
enabled = false
default_channel = "rc"
apply = ["release/*", "develop"]     # only these branches can use pre-release (if non-empty)
block = ["main", "master"]            # never allow pre-release on these branches
channel_map = { develop = "alpha" }    # optional: override channel per branch pattern

# Optional: gate bump command by branch
[bump_rules]
apply = ["develop", "release/*"]
block = ["main", "master"]

# Optional: explicit file targets; otherwise provider defaults apply
version_targets = [
  "pyproject.toml:project.version",
]
```

Branch rules evaluation:
- If current branch matches any `block` pattern → pre-release is disallowed.
- Else if `apply` is non-empty and branch does not match any `apply` pattern → disallowed.
- Else pre-release is allowed. The channel is `default_channel` unless a matching `channel_map` entry exists (first matching key wins; glob patterns supported: `*`, `?`).

### Roadmap (Workspaces/Monorepos)

- NPM workspaces: detect `workspaces` in `package.json`; allow glob patterns in config. Emit a `BumpResult` per package (with a rolled‑up summary).
- Python multi‑package mono repos: allow multiple `version_targets` entries and tag once at the root.
