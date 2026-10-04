# Every target wraps `uv run python -m engine.cli <command>`.
# On Windows without make, run the uv command directly (see the right-hand side).
# Tip: export UV_PYTHON_INSTALL_DIR to a path without spaces if uv cannot install Python.
CLI = uv run python -m engine.cli

.PHONY: setup recon corpus facts compile geo resolve lookups timelines changes export score snapshot all \
        test lint serve bench deploy-api ingest-file method-note audio watch-dry

setup:
	uv sync
	@test -f .env || cp .env.example .env

recon:
	$(CLI) recon

corpus:
	$(CLI) corpus

facts:
	$(CLI) facts

compile:
	$(CLI) compile $(ARGS)

geo:
	$(CLI) geo

resolve:
	$(CLI) resolve

lookups:
	$(CLI) lookups

timelines:
	$(CLI) timelines

changes:
	$(CLI) changes

export:
	$(CLI) export

score:
	$(CLI) score

snapshot:
	$(CLI) snapshot

all: compile geo resolve lookups timelines changes export score snapshot

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

serve:
	uv run uvicorn engine.api.main:app --reload --port 8000

bench:
	$(CLI) bench --api $(API)

deploy-api:
	$(CLI) deploy-api

ingest-file:
	$(CLI) ingest-file $(FILE)

method-note:
	$(CLI) method-note

audio:
	$(CLI) audio

watch-dry:
	$(CLI) watch --mode check --simulate
