# taskonaut

Deterministic taskonaut service in Python 3.12 using `uv`, FastAPI, Pydantic v2, SQLAlchemy 2, LangGraph, Alembic, and PostgreSQL.

## Features

- Deterministic LangGraph-based state graphs (no LLM) with registered flows (`echo_add`, `add_echo`)
- Tool contracts with Pydantic input/output models
- PostgreSQL persistence across `tasks`, `task_steps`, `tool_calls`, and `graph_state_snapshots`
- Tenacity-based tool retries with exponential backoff (max 3 attempts)
- Idempotent tool execution keyed by `(task_id, step_id, tool_name)`
- Per-task DB locking during `advance` to prevent concurrent workers from racing
- Structured JSON logs with per-task `trace_id` and per-step/tool-call `span_id`
- Prometheus metrics snapshot exporter via CLI and API `/metrics`
- HTTP API:
  - `POST /tasks` creates a task in `PLANNED` for the selected flow
  - `POST /tasks/{task_id}/advance` performs one transition
  - `POST /tasks/{task_id}/run` advances until terminal state (guarded by `max_steps`)
  - `GET /tasks` lists all tasks
  - `GET /tasks/{task_id}` fetches task state
- CLI:
  - `taskrunner run --flow <name> --input '<json>'`
  - `taskrunner show <task_id>`
  - `taskrunner metrics dump`
  - `taskonaut run-flow`
  - `taskonaut run-graph --flow <name>`
  - `taskonaut get-task`

## Requirements

- Python 3.12
- `uv`
- Docker (recommended for local PostgreSQL)

## Setup

```bash
uv sync
```

Start PostgreSQL and Jaeger in Docker:

```bash
docker compose up -d db jaeger
```

Set your database URL (optional, this is already the app default):

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5433/taskrunner'
```

Run migrations:

```bash
uv run alembic upgrade head
```

Stop the database when done:

```bash
docker compose down
```

Jaeger UI:

```text
http://localhost:16686
```

Default OTLP ingest endpoint used by the app:

```text
http://localhost:4318/v1/traces
```

## If You Already Have Postgres Running

1. Reuse your existing container and point `DATABASE_URL` at it, then run migrations:

```bash
export DATABASE_URL='postgresql+psycopg://<user>:<pass>@localhost:<port>/<db>'
uv run alembic upgrade head
```

2. Keep this project isolated by using the default Compose host port `5433`:

```bash
docker compose up -d db
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5433/taskrunner'
```

3. Change the host port if `5433` is also in use:

```bash
POSTGRES_HOST_PORT=5544 docker compose up -d db
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5544/taskrunner'
```

## Run API

```bash
uv run uvicorn main:app --reload
```

## Retry and Idempotency Behavior

- Tool execution uses exponential backoff retries with up to 3 total attempts.
- `tool_calls` stores retry metadata: `retry_count`, `last_error`, `started_at`, and `finished_at`.
- Each tool call writes an idempotency key built as `<task_id>:<step_id>:<tool_name>`.
- A unique DB constraint enforces one `tool_calls` record per idempotency key.
- If a duplicate execution path is hit for the same step/tool, the existing `tool_calls` row is reused.
- `advance` acquires a PostgreSQL advisory transaction lock per task so only one worker can advance a given task at a time.

## Trace Correlation

- Every task gets a persistent `trace_id`.
- Every step and tool call gets a `span_id`.
- Tool call logs include `trace_id`, `span_id`, and `tool_call_id` for correlation.
- `taskrunner show <task_id>` includes `trace_id` in output.
- CLI prints a Jaeger trace URL for tasks when `trace_id` is present.

## Jaeger Visualization

1. Start Jaeger:

```bash
docker compose up -d jaeger
```

2. Run a task:

```bash
uv run taskrunner run --flow demo --input '{"text":"hi","a":2,"b":3}' --verbose
```

3. Open the printed `trace_url` (or browse `http://localhost:16686`) to inspect the trace timeline and spans.

## API Usage

Create task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello","a":2,"b":3,"flow_name":"echo_add"}'
```

Advance one step:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/<task_id>/advance
```

Run until terminal state:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/<task_id>/run \
  -H 'Content-Type: application/json' \
  -d '{"max_steps":12}'
```

Fetch task:

```bash
curl -s http://127.0.0.1:8000/tasks/<task_id>
```

`GET /tasks/{task_id}` now includes:
- `current_node`
- `next_node`
- `graph_state_summary`

List tasks:

```bash
curl -s http://127.0.0.1:8000/tasks
```

## CLI Usage

Local deterministic run (no API server required):

```bash
uv run taskrunner run --flow demo --input '{"text":"hi","a":2,"b":3}' --verbose
```

Show a task (includes `trace_id`):

```bash
uv run taskrunner show <task_id>
```

Dump Prometheus metrics snapshot:

```bash
uv run taskrunner metrics dump
```

Create + run flow (default mode):

```bash
uv run taskonaut run-flow --flow echo_add --text hello --a 2 --b 3
```

Create + advance only once:

```bash
uv run taskonaut run-flow --flow add_echo --mode advance --text hello --a 2 --b 3
```

Create only (leave task in PLANNED):

```bash
uv run taskonaut run-flow --flow echo_add --mode create --text hello --a 2 --b 3
```

Create + run a registered graph directly:

```bash
uv run taskonaut run-graph --flow add_echo --text hello --a 2 --b 3 --max-steps 12
```

Fetch task:

```bash
uv run taskonaut get-task <task_id>
```

Fetch all tasks:

```bash
uv run taskonaut get-tasks
```

Advance existing task:

```bash
uv run taskonaut advance-task <task_id>
```

Run existing task to terminal:

```bash
uv run taskonaut run-task <task_id> --max-steps 12
```

Override target API URL if needed:

```bash
uv run taskonaut --api-base-url http://127.0.0.1:8011 get-tasks
```

Run API app via CLI:

```bash
uv run taskonaut run-app --host 127.0.0.1 --port 8000 --reload
```

Run API app via CLI with logster-formatted logs:

```bash
uv run taskonaut --logster run-app --host 127.0.0.1 --port 8000 --reload
```

Prometheus endpoint (when API is running):

```bash
curl -s http://127.0.0.1:8000/metrics
```

## Quality Checks

```bash
uv run ruff check .
uv run mypy taskrunner
uv run pytest
```
