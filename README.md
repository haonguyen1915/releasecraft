# ReleaseCraft

A powerful CLI tool for automating releases, changelogs, and version management with AI-powered release notes generation.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
  - [releaser init](#releaser-init)
  - [releaser bump](#releaser-bump)
  - [releaser commit-gen](#releaser-commit-gen)
  - [releaser commit-lint](#releaser-commit-lint)
  - [releaser cache](#releaser-cache)
- [Configuration](#configuration)
  - [Project Settings](#project-settings)
  - [Release Configuration](#release-configuration)
  - [Pre-Release Management](#pre-release-management)
  - [Changelog Settings](#changelog-settings)
  - [AI-Powered Release Notes](#ai-powered-release-notes)
  - [LLM Configuration](#llm-configuration)
  - [Hooks](#hooks)
  - [Commit Linting](#commit-linting)
  - [Commit Generation](#commit-generation)
- [Examples](#examples)
- [Advanced Features](#advanced-features)
  - [AI-Generated Release Notes](#ai-generated-release-notes)
  - [Pre-Release Workflows](#pre-release-workflows)
  - [Custom Prompts](#custom-prompts)
- [Contributing](#contributing)
- [License](#license)

## Overview

ReleaseCraft automates your release workflow with intelligent version bumping, changelog generation, and AI-powered release notes. It supports Poetry, npm, and setuptools projects with conventional commits.

## Features

✨ **Intelligent Version Bumping**
- Automatic semantic versioning based on conventional commits
- Support for major, minor, patch, and pre-release versions
- Multiple project types: Poetry, npm, setuptools

🤖 **AI-Powered Release Notes**
- Generate comprehensive release notes using OpenAI
- Automatic categorization of changes
- Include code diffs for important features
- Customizable prompts

📝 **Changelog Management**
- Automatic CHANGELOG.md updates
- Conventional commit parsing
- Custom changelog formatting

🔍 **Commit Message Tools**
- AI-powered commit message generation
- Conventional commit linting
- Interactive commit creation

🎯 **Pre-Release Support**
- Branch-based pre-release workflows
- Automatic pre-release versioning
- Channel-based releases (alpha, beta, rc)

⚙️ **Flexible Configuration**
- TOML-based configuration
- Per-project or global settings
- Extensive customization options

## Installation

### Using pip

```bash
pip install releasecraft
```

### From source

```bash
git clone https://github.com/yourusername/releasecraft.git
cd releasecraft
pip install -e .
```

## Quick Start

1. **Initialize configuration in your project:**

```bash
cd your-project
releaser init
```

2. **Make some commits following conventional commits:**

```bash
git commit -m "feat: add new feature"
git commit -m "fix: resolve bug"
```

3. **Bump version and create release:**

```bash
releaser bump
```

That's it! ReleaseCraft will automatically:
- Determine the version bump based on commits
- Update version in project files
- Generate changelog
- Create git tag
- Optionally generate AI-powered release notes

## Commands

### releaser init

Initialize ReleaseCraft configuration for your project.

```bash
# Interactive setup
releaser init

# Non-interactive with defaults
releaser init --yes

# Global configuration
releaser init --global

# Specify project type
releaser init --project-type poetry
```

**Options:**
- `--yes`: Accept all defaults, non-interactive
- `--global`: Write to `~/.releaser/config.toml`
- `--path PATH`: Custom config file path
- `--project-type {auto,poetry,setuptools,npm}`: Specify project type
- `--tag-prefix PREFIX`: Default tag prefix (default: "v")
- `--use-native/--no-use-native`: Use native tooling when available

### releaser bump

Bump version and create release.

```bash
# Auto-detect version bump from commits
releaser bump

# Force specific version bump
releaser bump --type major
releaser bump --type minor
releaser bump --type patch

# Set exact version
releaser bump --manual 2.0.0

# Create pre-release
releaser bump --pre

# Finalize pre-release to stable
releaser bump --finalize

# Dry-run mode (preview only)
releaser bump --dry-run

# With custom release notes
releaser bump --notes "Release notes here"
releaser bump --notes-file notes.txt

# Update changelog
releaser bump --changelog

# Push to remote after release
releaser bump --push
```

**Options:**
- `--manual VERSION`: Set exact version
- `--type {major,minor,patch}`: Force bump type
- `--pre`: Create pre-release version
- `--finalize`: Convert pre-release to stable
- `--dry-run`: Preview changes without applying
- `--push`: Push to remote after creating release
- `--no-commit`: Don't create commit
- `--no-tag`: Don't create tag
- `--notes TEXT`: Inline release notes
- `--notes-file PATH`: Read release notes from file
- `--changelog`: Append to CHANGELOG.md
- `--changelog-file PATH`: Custom changelog path
- `--version-source {file,local_tag,remote_tag,auto}`: Version source

### releaser commit-gen

Generate conventional commit messages from staged changes using AI.

```bash
# Generate from staged changes
git add .
releaser commit-gen --staged

# Generate and auto-commit
releaser commit-gen --staged --yes

# Generate from specific files
releaser commit-gen --files src/main.py src/utils.py

# Include ticket reference
releaser commit-gen --staged --ticket JIRA-123

# Save to file instead of committing
releaser commit-gen --staged --output commit.txt

# Disable AI, use heuristics only
releaser commit-gen --staged --no-ai

# Custom AI model
releaser commit-gen --staged --model gpt-4
```

**Options:**
- `--staged`: Use staged changes
- `--files FILES`: Specific files to analyze
- `--yes, -y`: Auto-commit without prompting
- `--ticket TICKET`: Include ticket reference
- `--output PATH`: Write to file instead of committing
- `--no-ai`: Use heuristics only, disable AI
- `--model MODEL`: AI model to use
- `--temperature FLOAT`: AI temperature (0.0-1.0)
- `--max-tokens INT`: Max AI response tokens
- `--history N`: Include last N commits as context

### releaser commit-lint

Validate commit messages against Conventional Commits specification.

```bash
# Lint commit message from file
releaser commit-lint commit-msg.txt

# Lint last commit
releaser commit-lint .git/COMMIT_EDITMSG

# JSON output
releaser commit-lint commit-msg.txt --format json
```

**Options:**
- `--format {text,json}`: Output format
- `--config PATH`: Custom config file

### releaser cache

Manage AI-generated release notes cache.

```bash
# Show cache statistics
releaser cache stats

# Clear all cache
releaser cache clear

# Clear cache older than 30 days
releaser cache clear --older-than 30

# Force clear without confirmation
releaser cache clear --force
```

**Options:**
- `stats`: Show cache statistics
- `clear`: Clear cache entries
- `--older-than DAYS`: Clear entries older than N days
- `--force`: Skip confirmation prompt

## Configuration

ReleaseCraft uses TOML configuration files. Configuration can be:
- Project-specific: `.releaser.toml` or `.releaser/config.toml`
- Global: `~/.releaser/config.toml`

### Project Settings

```toml
[project]
# Provider type: auto, poetry, setuptools, or npm
type = "auto"

# Tag prefix for git tags (e.g., v1.2.3)
tag_prefix = "v"

# Use native tooling when available (poetry version, npm version)
use_native = false
```

### Release Configuration

```toml
[release]
# Create git commit after version bump
create_commit = true

# Create git tag after version bump
create_tag = true

# Push to remote after release
push = false

# Additional files to update with version
version_targets = []

# Changelog file path
change_log_file = "CHANGELOG.md"

# Allow releasing with uncommitted changes
allow_dirty = false
```

### Pre-Release Management

```toml
[release.pre_release]
# Enable pre-release functionality
enabled = true

# Default pre-release channel (alpha, beta, rc, etc.)
default_channel = "rc"

# Auto-increment pre-release number
auto_increment = true

# Reset pre-release on version bump
reset_on_bump = true

# Branches where pre-releases are allowed
apply = ["develop", "release/*"]

# Branches where pre-releases are blocked
block = ["main", "master", "hotfix/*"]
```

### Changelog Settings

```toml
[release.change_log]
# Enable changelog generation
enabled = true

# Changelog file path
file = "CHANGELOG.md"

# Mode: 'auto' (from commits) or 'notes' (user notes only)
mode = "auto"
```

### AI-Powered Release Notes

```toml
[release.auto_gen_notes]
# Enable AI-powered release notes
enabled = false

# Include code diffs in release notes
include_diff = true

# Always include diffs for these commit types
always_diff_types = ["feat"]

# Maximum commits to analyze
max_commits = 200

# Mode: 'auto' or custom
mode = "auto"
```

### LLM Configuration

```toml
[llm-config]
# Enable LLM features (release notes, commit messages)
enabled = false

# LLM provider (currently only 'openai' supported)
provider = "openai"

# Model to use
model = "gpt-4o-mini"

# Environment variable containing API key
api_key_env = "OPENAI_API_KEY"

# Sampling temperature (0.0-1.0)
temperature = 0.2

# Maximum tokens in response
max_tokens = 2500

# Enable response caching
cache = true

# Auto-accept AI suggestions without prompting
accept_automatically = false

# Fail if AI generation fails (otherwise fall back to basic notes)
fail_on_error = false

# Optional: Custom prompt files
# prompt_release_notes_file = "path/to/custom_release_notes.md.j2"
# system_prompt_file = "path/to/custom_system_prompt.md"
```

### Hooks

```toml
[hooks]
# Shell commands to run before version bump
pre_bump = []

# Shell commands to run after version bump
post_bump = []
```

Example with hooks:

```toml
[hooks]
pre_bump = ["make test", "make lint"]
post_bump = ["make build", "make docs"]
```

### Commit Linting

```toml
[commit_lint]
# Enable commit message linting
enabled = true

# Allowed commit types
types = [
  "feat",
  "fix",
  "docs",
  "chore",
  "refactor",
  "perf",
  "test",
  "build",
  "ci",
  "revert",
  "style"
]

# Skip linting merge commits
skip_merge_commits = true

# Skip linting revert commits
skip_revert_commits = true
```

### Commit Generation

```toml
[commit_gen]
# Number of recent commits to use as context
history_commits = 10

# Demote 'feat' to 'chore' if similar to recent commits
demote_feat_if_similar = true

# Allow scope in commit messages
allow_scope = false
```

## Examples

### Basic Workflow

```bash
# 1. Initialize project
cd my-project
releaser init --project-type poetry

# 2. Make changes and commit
git add .
releaser commit-gen --staged --yes

# 3. Create release
releaser bump --changelog --push
```

### Pre-Release Workflow

```bash
# On develop branch
git checkout develop

# Create pre-release
releaser bump --pre
# Output: 1.2.0-rc.1

# More changes...
releaser bump --pre
# Output: 1.2.0-rc.2

# Ready to release
git checkout main
git merge develop
releaser bump --finalize
# Output: 1.2.0
```

### Manual Version Control

```bash
# Set specific version
releaser bump --manual 2.0.0

# Force major bump
releaser bump --type major

# Preview without changes
releaser bump --dry-run
```

### AI-Powered Release Notes

```bash
# Enable in config
# [llm-config]
# enabled = true
# model = "gpt-4o-mini"

# Set API key
export OPENAI_API_KEY="your-api-key"

# Create release with AI notes
releaser bump --changelog

# The AI will generate comprehensive release notes
# categorized by type (Features, Bug Fixes, etc.)
```

### Custom Changelog

```bash
# Add custom notes
releaser bump \
  --notes "This release includes major performance improvements" \
  --changelog

# From file
releaser bump --notes-file release-notes.md --changelog
```

## Advanced Features

### AI-Generated Release Notes

ReleaseCraft can generate comprehensive release notes using OpenAI:

1. **Enable AI in configuration:**

```toml
[llm-config]
enabled = true
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"

[release.auto_gen_notes]
enabled = true
include_diff = true
always_diff_types = ["feat"]
```

2. **Set your API key:**

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

3. **Generate release:**

```bash
releaser bump --changelog
```

The AI will:
- Analyze all commits since last release
- Categorize changes (Features, Bug Fixes, etc.)
- Generate human-readable descriptions
- Include code diffs for important changes
- Format output in Markdown

### Pre-Release Workflows

Configure branch-based pre-release rules:

```toml
[release.pre_release]
enabled = true
default_channel = "rc"

# Pre-releases allowed on these branches
apply = ["develop", "release/*"]

# Pre-releases blocked on these branches
block = ["main", "master", "hotfix/*"]
```

**Usage:**

```bash
# On develop branch - creates 1.0.0-rc.1
git checkout develop
releaser bump --pre

# Subsequent pre-releases increment: 1.0.0-rc.2, 1.0.0-rc.3, etc.
releaser bump --pre

# On main branch - finalizes to 1.0.0
git checkout main
releaser bump --finalize
```

### Custom Prompts

Customize AI behavior with custom prompts:

1. **Create custom prompt file** (`custom_release_notes.md.j2`):

```markdown
Generate release notes for version {{ version }}.

Commits:
{% for commit in commits %}
- {{ commit.message }}
{% endfor %}

Focus on user-facing changes and improvements.
```

2. **Update configuration:**

```toml
[llm-config]
prompt_release_notes_file = "custom_release_notes.md.j2"
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Made with ❤️ by the ReleaseCraft team**

For more information and updates, visit our [GitHub repository](https://github.com/haonguyen1915).
