# Changelog

## 0.1.0 - 2026-02-20

- Bootstrap Python 3.12 project with `uv`
- Add FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg, pytest, ruff, mypy
- Implement deterministic task-runner flow (`echo` -> `add`)
- Add PostgreSQL `Task` model with status and step history
- Expose `POST /tasks` and `GET /tasks/{task_id}`
- Add `taskrunner` CLI with `run-flow` and `get-task`
- Add Alembic migration for `tasks` table
