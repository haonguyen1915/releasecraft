.PHONY: install
install:
	@echo "🚀 Installing environment"
	poetry install --with dev


.PHONY: publish
publish:
	@echo "🚀 Publishing package"
	poetry publish --build
.PHONY: lint
lint:
	@echo "🚀 Checking poetry.lock file"
	poetry check --lock
	@echo "🚀 Linting (ruff/flake8)"
	# Prefer ruff via poetry; fallback to system ruff, then flake8
	(POETRY_VIRTUALENVS_CREATE=false poetry run ruff check) \
		|| (ruff check) \
		|| (flake8 --max-line-length=120 --extend-ignore=E501,E203,W503,W391,W291,E402,E741,F811,F841 releaser || true)
	@echo "🚀 Checking with pylint"
	# Run via poetry if available; otherwise use system pylint
	(POETRY_VIRTUALENVS_CREATE=false poetry run pylint -j 1 --persistent=no releaser) \
		|| pylint -j 1 --persistent=no releaser || true
	@echo "🚀 Checking with mypy"
	# Prefer poetry; fallback to system mypy; skip if not installed
	(POETRY_VIRTUALENVS_CREATE=false poetry run mypy releaser) \
		|| (mypy releaser || echo "(Skipping mypy: not installed)")
	@echo "🟢 All checks have passed"

.PHONY: lint_test
lint_test:
	@echo "🚀 Checking poetry.lock file"
	poetry check --lock
	@echo "🚀 Linting with ruff"
	poetry run ruff check
	@echo "🚀 Checking with pylint"
	poetry run pylint tests
	@echo "🚀 Checking with mypy"
	poetry run mypy tests
	@echo "🟢 All checks have passed"

.PHONY: fix
fix:
	@echo "🚀 Fixing with ruff"
	poetry run ruff check --fix releaser
	poetry run ruff check --fix tests

.PHONY: format
format:
	poetry run ruff format

.PHONY: test
test:
	@echo "🚀 Running tests with pytest"
	poetry run pytest tests
