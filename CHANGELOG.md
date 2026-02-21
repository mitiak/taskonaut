# Changelog

## Unreleased

## 0.2.0 - 2026-02-21

- Add Docker Compose PostgreSQL service for local development.
- Add `GET /tasks` endpoint and CLI support for listing tasks.
- Rename project package/CLI to `taskonaut`.
- Refactor task execution flow into an explicit step engine.
- Add `logster` integration and project-level `logster.toml` configuration.
- Update logster main line to include `[file]` and `[function:line]`.
- Remove `logger` segment from logster main line output.

## 0.1.0 - 2026-02-20

- Bootstrap Python 3.12 project with `uv`
- Add FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg, pytest, ruff, mypy
- Implement deterministic task-runner flow (`echo` -> `add`)
- Add PostgreSQL `Task` model with status and step history
- Expose `POST /tasks` and `GET /tasks/{task_id}`
- Add `taskrunner` CLI with `run-flow` and `get-task`
- Add Alembic migration for `tasks` table
