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
	@echo "🚀 Linting with ruff"
	poetry run ruff check
	@echo "🚀 Checking with pylint"
	poetry run pylint cachine
	@echo "🚀 Checking with mypy"
	@if command -v mypy >/dev/null 2>&1; then \
		poetry run mypy cachine ; \
	else \
		echo "⚠️  mypy not installed; skipping type check" ; \
	fi
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
	@if command -v mypy >/dev/null 2>&1; then \
		poetry run mypy tests ; \
	else \
		echo "⚠️  mypy not installed; skipping type check" ; \
	fi
	@echo "🟢 All checks have passed"

.PHONY: fix
fix:
	@echo "🚀 Fixing with ruff"
	poetry run ruff check --fix cachine
	poetry run ruff check --fix tests

.PHONY: format
format:
	poetry run ruff format

.PHONY: test
test:
	@echo "🚀 Running tests with pytest"
	poetry run pytest tests


