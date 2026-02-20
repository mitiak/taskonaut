# taskrunner

Deterministic task-runner service in Python 3.12 using `uv`, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, and PostgreSQL.

## Features

- Deterministic state machine for a predefined flow: `echo` then `add`
- Tool contracts with Pydantic input/output models
- PostgreSQL `tasks` persistence with status and step history
- HTTP API:
  - `POST /tasks` starts the flow
  - `GET /tasks` lists all tasks
  - `GET /tasks/{task_id}` fetches task state
- CLI:
  - `taskrunner run-flow`
  - `taskrunner get-task`

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

List tasks:

```bash
curl -s http://127.0.0.1:8000/tasks
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
