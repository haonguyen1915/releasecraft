## [0.3.2] - 2026-07-12

### Release Notes

### What's Changed
- Resolved a critical issue with dependency versioning to enhance stability.

### Bug Fixes

- fix: bump (2ff6f7f)

**Contributors:** @Nguyễn Văn Hảo

**Compare changes:** [v0.3.1...v0.3.2](https://github.com/haonguyen1915/releasecraft.git/-/compare/v0.3.1...v0.3.2)

## [0.3.1] - 2026-04-23

### Release Notes

Enhanced release with new dry-run capabilities and improved dependency management.

### What's Changed
- Introduced 'apply-files' option for dry-run to preview changes without committing.
- Optimized Cargo.lock update strategy for better dependency management.

### Features

- feat: add apply-files option for dry-run (6626d34)

### Refactoring

- refactor: improve Cargo.lock update strategy (12b6a34)

**Contributors:** @Nguyễn Văn Hảo

**Compare changes:** [v0.3.0-rc.3...v0.3.1](https://github.com/haonguyen1915/releasecraft.git/-/compare/v0.3.0-rc.3...v0.3.1)

## [0.3.0-rc.3] - 2026-02-23 (Pre-release)

### Release Notes

Enhanced release automation and provider support.

### What's Changed
- Added support for automatic release target selection based on Git remote configuration.
- Introduced multi-provider support for version management, including NPM and Cargo.
- Improved OpenAI model compatibility by updating token parameter handling.

### Features

- feat: support npm cargo (03d4dfd)
- feat: add auto release target selection (f5f8efc)

### Chores

- chore: support ignore type in changelog (dc0ca95)
- chore: fix update version for npm (facbc08)
- chore: fix openai (09ab425)

**Contributors:** @Nguyễn Văn Hảo

**Compare changes:** [v0.3.0-rc.2...v0.3.0-rc.3](https://github.com/haonguyen1915/releasecraft.git/-/compare/v0.3.0-rc.2...v0.3.0-rc.3)

## [0.3.0-rc.2] - 2025-11-20 (Pre-release)

### Release Notes

Enhanced release management with new features and improved configuration.

### What's Changed
- Introduced GitLab and GitHub release options for streamlined version management.
- Added auto-add-all option to CLI for easier commit handling.
- Implemented logging configuration support for better debugging and monitoring.

### Features

- feat: add GitLab and GitHub release options (322a5f1)
- feat: add auto-add-all option to CLI (8e7b47c)
- feat: add logging configuration support (c04f2a0)

### Bug Fixes

- fix: update package data configuration (ed5ed1d)

### Documentation

- docs: add repository guidelines and update README (5ce96a2)
- docs: update README for ReleaseCraft (7ddbe7d)

### Refactoring

- refactor: improve changelog header formatting (701415d)
- refactor: update highlights section header (b4b5149)
- refactor: improve semver regex and tests (324947c)
- refactor: enhance pre-release configuration handling (8e1e2fa)

### Chores

- chore: fix lint (496752b)
- chore: fix lint errors (ddb4298)
- chore: update ReadMe (72f9d3e)

**Contributors:** @Nguyễn Văn Hảo

**Compare changes:** [v0.3.0-rc.1...v0.3.0-rc.2](https://github.com/haonguyen1915/releasecraft.git/-/compare/v0.3.0-rc.1...v0.3.0-rc.2)

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

