# Changelog

## Unreleased

## 0.6.0 - 2026-02-22

## 0.5.0 - 2026-02-22

- Add trace correlation fields: `trace_id` on tasks and `span_id` on steps/tool calls.
- Add structured tool-call logs with `trace_id`, `span_id`, and `tool_call_id`.
- Add local CLI commands: `taskrunner run`, `taskrunner show`, and `taskrunner metrics dump`.
- Add Prometheus metrics snapshot generation and `/metrics` API endpoint.
- Add migration for trace/span schema changes.
- Add `taskrunner` console script alias.
- Add Jaeger (OpenTelemetry OTLP) integration docs and Docker Compose service for trace visualization.
- Add allowlisted tool registry and reject unknown tools before execution.
- Enforce strict Pydantic validation for tool inputs and outputs.
- Add policy limits: `max_input_bytes`, `max_steps`, and `tool_timeout_secs`.
- Add `audit_logs` table for rejected tool calls and policy violations.
- Add CLI `validate` command and explicit non-zero policy violation exits.

## 0.4.0 - 2026-02-22

- Integrate deterministic LangGraph flow execution (no LLM) with registered flows `echo_add` and `add_echo`.
- Add graph-aware task fields: `current_node`, `next_node`, and `graph_state_summary`.
- Persist per-step graph snapshots in Postgres via `graph_state_snapshots`.
- Add Alembic migration for graph snapshot/state tracking schema.
- Add CLI `run-graph --flow <name>` and add `--flow` support to `run-flow`.
- Extend `/tasks/{id}` payload to expose graph execution state.
- Add tests for graph flow registry/execution and CLI/API updates.

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
