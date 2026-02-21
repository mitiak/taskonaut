# Changelog

## Unreleased

## 0.3.0 - 2026-02-21

- Add tenacity-based retries with exponential backoff for tool execution.
- Add tool-call idempotency keys based on `(task_id, step_id, tool_name)` and enforce uniqueness in Postgres.
- Add per-task PostgreSQL advisory locking plus row-level locking to prevent concurrent `advance` races.
- Extend `tool_calls` with `retry_count`, `last_error`, `started_at`, and `finished_at`.
- Add Alembic migration for new `tool_calls` columns and idempotency constraints.
- Update API schemas and tests for retry/idempotency metadata.
- Document retry/idempotency/locking behavior in `README.md`.

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
