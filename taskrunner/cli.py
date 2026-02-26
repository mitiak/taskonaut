from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Callable
from uuid import UUID

import httpx
import uvicorn

from taskrunner.db import SessionLocal
from taskrunner.log_config import configure_logging
from taskrunner.metrics import dump_metrics_snapshot
from taskrunner.policy import PolicyViolationError
from taskrunner.schemas import TaskResponse
from taskrunner.service import TaskNotFoundError, TaskRunnerService
from taskrunner.tracing import configure_tracing

logger = logging.getLogger(__name__)


def _format_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return json.dumps(payload, indent=2)


def _print_json_response(response: httpx.Response) -> None:
    try:
        payload = response.json()
    except ValueError:
        print(response.text)
        return
    if isinstance(payload, dict) and isinstance(payload.get("trace_id"), str):
        _print_task_payload(payload)
        return
    print(json.dumps(payload, indent=2))


def _print_task_payload(task_payload: dict[str, object]) -> None:
    trace_id = task_payload.get("trace_id")
    if isinstance(trace_id, str):
        print(f"trace_id: {trace_id}")
        jaeger_ui_url = os.getenv("JAEGER_UI_URL", "http://localhost:16686").rstrip("/")
        print(f"trace_url: {jaeger_ui_url}/trace/{trace_id}")
    print(json.dumps(task_payload, indent=2))


def _api_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    json_body: dict[str, object] | None = None,
) -> httpx.Response | None:
    url = f"{args.api_base_url.rstrip('/')}{path}"
    try:
        return httpx.request(method, url, json=json_body, timeout=10.0)
    except httpx.RequestError as exc:
        logger.error("cli.api.unreachable", extra={"url": url, "error": str(exc)})
        print(f"Failed to reach API at {url}: {exc}")
        return None


def run_flow_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.run_flow.started",
        extra={
            "flow_name": args.flow,
            "api_base_url": args.api_base_url,
        },
    )
    create_response = _api_request(
        args,
        "POST",
        "/tasks",
        json_body={"flow_name": args.flow},
    )
    if create_response is None:
        return 1
    if create_response.is_error:
        logger.warning("cli.run_flow.failed", extra={"status_code": create_response.status_code})
        print(_format_api_error(create_response))
        return 1

    try:
        task_payload = create_response.json()
        task_id = task_payload["id"]
    except (ValueError, KeyError, TypeError):
        print("Unexpected create-task response payload")
        return 1

    if args.mode == "create":
        logger.info("cli.run_flow.created", extra={"task_id": task_id})
        _print_json_response(create_response)
        return 0

    path = f"/tasks/{task_id}/advance" if args.mode == "advance" else f"/tasks/{task_id}/run"
    body = None if args.mode == "advance" else {"max_steps": args.max_steps}
    execute_response = _api_request(args, "POST", path, json_body=body)
    if execute_response is None:
        return 1
    if execute_response.is_error:
        logger.warning(
            "cli.run_flow.execute_failed",
            extra={
                "task_id": task_id,
                "mode": args.mode,
                "status_code": execute_response.status_code,
            },
        )
        print(_format_api_error(execute_response))
        return 1
    logger.info("cli.run_flow.succeeded", extra={"task_id": task_id, "mode": args.mode})
    _print_json_response(execute_response)
    return 0


def get_task_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.get_task.started",
        extra={"task_id": args.task_id, "api_base_url": args.api_base_url},
    )
    try:
        UUID(args.task_id)
    except ValueError:
        print(f"Invalid task id: {args.task_id}")
        return 1

    response = _api_request(args, "GET", f"/tasks/{args.task_id}")
    if response is None:
        return 1
    if response.status_code == 404:
        logger.warning("cli.get_task.not_found", extra={"task_id": args.task_id})
        print(_format_api_error(response))
        return 1
    if response.is_error:
        logger.warning(
            "cli.get_task.failed",
            extra={"task_id": args.task_id, "status_code": response.status_code},
        )
        print(_format_api_error(response))
        return 1
    logger.info("cli.get_task.succeeded", extra={"task_id": args.task_id})
    _print_json_response(response)
    return 0


def get_tasks_command(args: argparse.Namespace) -> int:
    logger.info("cli.get_tasks.started", extra={"api_base_url": args.api_base_url})
    response = _api_request(args, "GET", "/tasks")
    if response is None:
        return 1
    if response.is_error:
        logger.warning("cli.get_tasks.failed", extra={"status_code": response.status_code})
        print(_format_api_error(response))
        return 1
    logger.info("cli.get_tasks.succeeded", extra={"status_code": response.status_code})
    _print_json_response(response)
    return 0


def advance_task_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.advance_task.started",
        extra={"task_id": args.task_id, "api_base_url": args.api_base_url},
    )
    try:
        UUID(args.task_id)
    except ValueError:
        print(f"Invalid task id: {args.task_id}")
        return 1

    response = _api_request(args, "POST", f"/tasks/{args.task_id}/advance")
    if response is None:
        return 1
    if response.is_error:
        logger.warning(
            "cli.advance_task.failed",
            extra={"task_id": args.task_id, "status_code": response.status_code},
        )
        print(_format_api_error(response))
        return 1
    logger.info("cli.advance_task.succeeded", extra={"task_id": args.task_id})
    _print_json_response(response)
    return 0


def run_task_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.run_task.started",
        extra={
            "task_id": args.task_id,
            "max_steps": args.max_steps,
            "api_base_url": args.api_base_url,
        },
    )
    try:
        UUID(args.task_id)
    except ValueError:
        print(f"Invalid task id: {args.task_id}")
        return 1

    response = _api_request(
        args,
        "POST",
        f"/tasks/{args.task_id}/run",
        json_body={"max_steps": args.max_steps},
    )
    if response is None:
        return 1
    if response.is_error:
        logger.warning(
            "cli.run_task.failed",
            extra={"task_id": args.task_id, "status_code": response.status_code},
        )
        print(_format_api_error(response))
        return 1
    logger.info("cli.run_task.succeeded", extra={"task_id": args.task_id})
    _print_json_response(response)
    return 0


def run_app_command(args: argparse.Namespace) -> int:
    if args.reload:
        uvicorn.run("taskrunner.api:app", host=args.host, port=args.port, reload=True)
    else:
        from taskrunner.api import app

        uvicorn.run(app, host=args.host, port=args.port)
    return 0


def run_local_command(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        service = TaskRunnerService(db)
        try:
            request = service.validate_request_payload(flow_name=args.flow, raw_input=args.input)
        except PolicyViolationError as exc:
            print(f"Policy violation [{exc.code}]: {exc.message}")
            return 2
        task = service.create_task(request)
        try:
            task = service.run_task(task.id, max_steps=args.max_steps)
        except PolicyViolationError as exc:
            print(f"Policy violation [{exc.code}]: {exc.message}")
            return 2
        payload = TaskResponse.model_validate(task).model_dump(mode="json")

    _print_task_payload(payload)
    logger.info(
        "cli.run.succeeded",
        extra={"task_id": payload["id"], "trace_id": payload["trace_id"], "flow_name": args.flow},
    )
    return 0


def show_local_command(args: argparse.Namespace) -> int:
    try:
        task_id = UUID(args.task_id)
    except ValueError:
        print(f"Invalid task id: {args.task_id}")
        return 1

    with SessionLocal() as db:
        service = TaskRunnerService(db)
        try:
            task = service.get_task(task_id)
        except TaskNotFoundError as exc:
            print(str(exc))
            return 1
        payload = TaskResponse.model_validate(task).model_dump(mode="json")

    _print_task_payload(payload)
    return 0


def metrics_dump_command(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        print(dump_metrics_snapshot(db))
    return 0


def validate_local_command(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        service = TaskRunnerService(db)
        try:
            request = service.validate_request_payload(flow_name=args.flow, raw_input=args.input)
        except PolicyViolationError as exc:
            print(f"Policy violation [{exc.code}]: {exc.message}")
            return 2
    print(f"Validation passed for flow '{request.flow_name}'")
    return 0


def run_graph_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.run_graph.started",
        extra={
            "flow_name": args.flow,
            "max_steps": args.max_steps,
            "api_base_url": args.api_base_url,
        },
    )
    create_response = _api_request(
        args,
        "POST",
        "/tasks",
        json_body={"flow_name": args.flow},
    )
    if create_response is None:
        return 1
    if create_response.is_error:
        print(_format_api_error(create_response))
        return 1

    try:
        task_payload = create_response.json()
        task_id = task_payload["id"]
    except (ValueError, KeyError, TypeError):
        print("Unexpected create-task response payload")
        return 1

    execute_response = _api_request(
        args,
        "POST",
        f"/tasks/{task_id}/run",
        json_body={"max_steps": args.max_steps},
    )
    if execute_response is None:
        return 1
    if execute_response.is_error:
        print(_format_api_error(execute_response))
        return 1
    logger.info("cli.run_graph.succeeded", extra={"task_id": task_id, "flow_name": args.flow})
    _print_json_response(execute_response)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taskrunner")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("TASKONAUT_API_URL", os.getenv("TASKRUNNER_API_URL", "http://127.0.0.1:8000")),
        help="Base URL for taskonaut API commands",
    )
    parser.add_argument(
        "--logster",
        action="store_true",
        help="Format taskonaut logs with logster (uses logster.toml by default)",
    )
    parser.add_argument(
        "--logster-config",
        help="Path to logster TOML config file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging for CLI commands",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_local = subparsers.add_parser(
        "run",
        help="Run deterministic flow locally against DB without API server",
    )
    run_local.add_argument("--flow", required=True, help="Registered flow name")
    run_local.add_argument(
        "--input",
        required=True,
        help='JSON object input, e.g. \'{"text":"hi","a":2,"b":3}\'',
    )
    run_local.add_argument("--max-steps", type=int, default=32, help="Max transitions")
    run_local.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    run_local.set_defaults(func=run_local_command)

    validate_local = subparsers.add_parser(
        "validate",
        help="Validate flow input and tool schemas/policy without executing tools",
    )
    validate_local.add_argument("--flow", required=True, help="Registered flow name")
    validate_local.add_argument("--input", required=True, help="JSON object input")
    validate_local.set_defaults(func=validate_local_command)

    show_local = subparsers.add_parser("show", help="Show task state by id (includes trace_id)")
    show_local.add_argument("task_id", help="Task UUID")
    show_local.set_defaults(func=show_local_command)

    metrics = subparsers.add_parser("metrics", help="Metrics utilities")
    metrics_subparsers = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_dump = metrics_subparsers.add_parser("dump", help="Dump Prometheus metrics snapshot")
    metrics_dump.set_defaults(func=metrics_dump_command)

    run_flow = subparsers.add_parser(
        "run-flow",
        help="Create task and execute using create/advance/run mode",
    )
    run_flow.add_argument("--flow", default="soc_pipeline", help="Registered flow name")
    run_flow.add_argument(
        "--mode",
        choices=("create", "advance", "run"),
        default="run",
        help="Execution mode after task creation",
    )
    run_flow.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Only used when --mode=run",
    )
    run_flow.set_defaults(func=run_flow_command)

    get_task = subparsers.add_parser("get-task", help="Fetch task by id")
    get_task.add_argument("task_id", help="Task UUID")
    get_task.set_defaults(func=get_task_command)

    get_tasks = subparsers.add_parser("get-tasks", help="Fetch all tasks")
    get_tasks.set_defaults(func=get_tasks_command)

    advance_task = subparsers.add_parser(
        "advance-task",
        help="Advance task by exactly one transition",
    )
    advance_task.add_argument("task_id", help="Task UUID")
    advance_task.set_defaults(func=advance_task_command)

    run_task = subparsers.add_parser(
        "run-task",
        help="Advance task until terminal state or max-steps",
    )
    run_task.add_argument("task_id", help="Task UUID")
    run_task.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum number of advance transitions",
    )
    run_task.set_defaults(func=run_task_command)

    run_graph = subparsers.add_parser(
        "run-graph",
        help="Create and run a deterministic LangGraph flow by name",
    )
    run_graph.add_argument("--flow", required=True, help="Registered flow name")
    run_graph.add_argument("--max-steps", type=int, default=12, help="Max transitions")
    run_graph.set_defaults(func=run_graph_command)

    run_app = subparsers.add_parser("run-app", help="Run the main FastAPI app")
    run_app.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    run_app.add_argument("--port", type=int, default=8000, help="Port to bind")
    run_app.add_argument("--reload", action="store_true", help="Enable auto-reload")
    run_app.set_defaults(func=run_app_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(
        level="DEBUG" if args.verbose else None,
        log_style="logster" if args.logster else "json",
        logster_config_path=args.logster_config,
    )
    configure_tracing(service_name="taskrunner-cli")
    command: Callable[[argparse.Namespace], int] = args.func
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
