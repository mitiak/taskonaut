# taskonaut

Deterministic taskonaut service in Python 3.12 using `uv`, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, and PostgreSQL.

## Features

- Deterministic state machine for a predefined flow: `echo` then `add`
- Tool contracts with Pydantic input/output models
- PostgreSQL persistence across `tasks`, `task_steps`, and `tool_calls`
- Tenacity-based tool retries with exponential backoff (max 3 attempts)
- Idempotent tool execution keyed by `(task_id, step_id, tool_name)`
- Per-task DB locking during `advance` to prevent concurrent workers from racing
- HTTP API:
  - `POST /tasks` creates a task in `PLANNED`
  - `POST /tasks/{task_id}/advance` performs one transition
  - `POST /tasks/{task_id}/run` advances until terminal state (guarded by `max_steps`)
  - `GET /tasks` lists all tasks
  - `GET /tasks/{task_id}` fetches task state
- CLI:
  - `taskonaut run-flow`
  - `taskonaut get-task`

## Requirements

- Python 3.12
- `uv`
- Docker (recommended for local PostgreSQL)

## Setup

```bash
uv sync
```

Start PostgreSQL in Docker:

```bash
docker compose up -d db
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

## API Usage

Create task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello","a":2,"b":3}'
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

List tasks:

```bash
curl -s http://127.0.0.1:8000/tasks
```

## CLI Usage

Create + run flow (default mode):

```bash
uv run taskonaut run-flow --text hello --a 2 --b 3
```

Create + advance only once:

```bash
uv run taskonaut run-flow --mode advance --text hello --a 2 --b 3
```

Create only (leave task in PLANNED):

```bash
uv run taskonaut run-flow --mode create --text hello --a 2 --b 3
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

## Quality Checks

```bash
uv run ruff check .
uv run mypy taskrunner
uv run pytest
```
