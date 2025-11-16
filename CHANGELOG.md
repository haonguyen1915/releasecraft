# Changelog

## v0.3.0-rc.1 – 2025-11-16

### Release Notes

Introducing enhanced CLI features and AI-powered release notes generation in version 0.3.0-rc.1.

### Highlights
- Added a version source option to the CLI for improved version resolution flexibility.
- Introduced an auto-commit feature in the CLI to streamline the commit process without prompts.
- Implemented AI-powered generation of release notes, enhancing the documentation process with intelligent summaries.
- Enhanced commit message generation through an API, allowing for better integration and automation in workflows.

### Features

- feat: add version source option to CLI (8b22b55)
- feat: add auto-commit option to CLI (faeb461)
- feat: API support generate commit message (7ad4b0b)
- feat: add convention for commit lint (ceae60c)
- feat: implement API collector data (c24cad8)
- feat: add service generate release notes (574dbb5)
- feat: add ai module engine (0cda2a5)
- feat: implement base features (6e97d14)

### Bug Fixes

- fix: error on add changelog auto (aeaba43)

### Refactoring

- refactor: improve linting and configuration handling (bc4c8a3)
- refactor: update changelog handling and cleanup (83068a9)
- refactor: update releaser configuration settings (e562754)
- refactor: improve CLI prompt clarity (34e7dde)
- refactor: improve provider configuration handling (dd9b5b8)

### Chores

- chore: update releaser configuration settings (c8131ff)
- chore: enable AI-powered release notes generation (df8d9c9)
- chore: enhance releaser configuration (c14ea2b)
- chore: update commit message generation (4d1e140)
- chore: support alway diff for type commit (f8db176)
- chore: enhace CLI prompting (a41accf)
- chore: add API CLI for cache (d459762)
- chore: enhance prompt for generate release note (cae4653)
- chore: add cache for LLM generate (e028aac)
- chore: update logic for flow notes (2607922)
- chore: show change logs in dry-run (cc00363)
- chore: Ask to update changelog if not specified via flags (c52b15e)
- chore: remove change logs (fb775b1)
- chore: impl bump version cli (a2ed720)
- chore: add release toml (a88b5ff)
- chore: remove trash (e82ac46)

### Other

- Initial commit (5304600)

**Contributors:** @Nguyễn Văn Hảo

