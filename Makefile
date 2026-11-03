UV ?= uv
PY_TARGETS := src/pdftunnel tests
IMAGE ?= pdftunnel:dev

.PHONY: install fmt lint type test lock-check check build run smoke clean

install:  ## Create the virtualenv from the lock file
	$(UV) sync --frozen

fmt:  ## Format and auto-fix
	$(UV) run ruff format $(PY_TARGETS)
	$(UV) run ruff check --fix $(PY_TARGETS)

lint:  ## Formatting and lint checks, no changes
	$(UV) run ruff format --check $(PY_TARGETS)
	$(UV) run ruff check $(PY_TARGETS)

type:  ## Strict type check
	$(UV) run mypy

test:  ## Unit and web tests with the coverage gate
	$(UV) run pytest --cov --cov-report=term-missing

lock-check:  ## Fail if pyproject.toml and uv.lock disagree
	$(UV) lock --check

check: lock-check lint type test  ## Everything the quality CI job runs

build:  ## Build the image for this machine
	docker build -t $(IMAGE) .

run: build  ## Run the compose file against the local image (needs TUNNEL_TOKEN in .env)
	IMAGE=$(IMAGE) docker compose up

smoke: build  ## Start the image with a bogus token and fetch a file through a mapped port
	./scripts/smoke.sh $(IMAGE)

clean:
	rm -rf .venv .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
