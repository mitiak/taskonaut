# taskrunner

Deterministic task-runner service in Python 3.12 using `uv`, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, and PostgreSQL.

## Features

- Deterministic state machine for a predefined flow: `echo` then `add`
- Tool contracts with Pydantic input/output models
- PostgreSQL `tasks` persistence with status and step history
- HTTP API:
  - `POST /tasks` starts the flow
  - `GET /tasks/{task_id}` fetches task state
- CLI:
  - `taskrunner run-flow`
  - `taskrunner get-task`

## Requirements

- Python 3.12
- `uv`
- PostgreSQL

## Setup

```bash
uv sync
```

Set your database URL:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/taskrunner'
```

Run migrations:

```bash
uv run alembic upgrade head
```

## Run API

```bash
uv run uvicorn main:app --reload
```

## API Usage

Create task:

```bash
curl -s -X POST http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello","a":2,"b":3}'
```

Fetch task:

```bash
curl -s http://127.0.0.1:8000/tasks/<task_id>
```

## CLI Usage

Run flow:

```bash
uv run taskrunner run-flow --text hello --a 2 --b 3
```

Fetch task:

```bash
uv run taskrunner get-task <task_id>
```

## Quality Checks

```bash
uv run ruff check .
uv run mypy taskrunner
uv run pytest
```
