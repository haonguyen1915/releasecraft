# Repository Guidelines

## Project Structure & Modules
- Source code lives in `releaser/` (CLI entry in `releaser/cli.py`, workflows in `releaser/workflow.py`, AI prompts in `releaser/ai/`, config helpers in `releaser/config/`).
- Tests are in `tests/`, mirroring the package layout (for example `tests/test_cli_*.py`).
- Build and coverage artifacts (`build/`, `dist/`, `htmlcov/`, `releasecraft.egg-info/`) are generated; do not edit them by hand.

## Build, Test & Development Commands
- `make install` – install dependencies with Poetry (including dev tools).
- `make test` – run the pytest suite with coverage.
- `make lint` – run lockfile check, ruff/flake8, pylint and mypy on `releaser/`.
- `make fix` / `make format` – auto-fix style via ruff and format code.
- Run the CLI via `poetry run releaser ...` or `poetry run release-drafter ...`.

## Coding Style & Naming
- Python 3.9+ code, 4-space indentation, prefer type hints; production code is mypy-strict.
- Formatting is via ruff/black conventions (line length ~88–100); do not hand-wrap differently.
- Use descriptive, snake_case names for functions, variables and modules; keep CLI command names consistent with existing subcommands.

## Testing Guidelines
- Tests use `pytest` (see `pyproject.toml` for configuration) and live under `tests/`.
- Name test files `test_*.py` and functions `test_*`; place tests next to the feature they cover.
- Before opening a PR, run at least `make test` and `make lint`.

## Commit & Pull Request Guidelines
- Follow Conventional Commit-style messages (e.g. `fix:`, `refactor:`, `docs:`, `chore(release):`).
- Keep commits focused and descriptive in the imperative mood (e.g. `fix: handle empty changelog`).
- PRs should include: a short summary, motivation/context, key changes, how to run relevant commands, and any notable CLI output or screenshots.

## Agent-Specific Notes
- Prefer modifying `releaser/` and `tests/`; avoid touching generated artifacts.
- When updating behavior, also update or add tests to keep coverage meaningful.
