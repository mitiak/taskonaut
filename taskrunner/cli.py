from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Callable
from uuid import UUID

import httpx
import uvicorn

from taskrunner.log_config import configure_logging

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
    print(json.dumps(payload, indent=2))


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
            "text": args.text,
            "a": args.a,
            "b": args.b,
            "flow_name": args.flow,
            "api_base_url": args.api_base_url,
        },
    )
    create_response = _api_request(
        args,
        "POST",
        "/tasks",
        json_body={"text": args.text, "a": args.a, "b": args.b, "flow_name": args.flow},
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


def run_graph_command(args: argparse.Namespace) -> int:
    logger.info(
        "cli.run_graph.started",
        extra={
            "flow_name": args.flow,
            "text": args.text,
            "a": args.a,
            "b": args.b,
            "max_steps": args.max_steps,
            "api_base_url": args.api_base_url,
        },
    )
    create_response = _api_request(
        args,
        "POST",
        "/tasks",
        json_body={"text": args.text, "a": args.a, "b": args.b, "flow_name": args.flow},
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
    parser = argparse.ArgumentParser(prog="taskonaut")
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_flow = subparsers.add_parser(
        "run-flow",
        help="Create task and execute using create/advance/run mode",
    )
    run_flow.add_argument("--text", default="hello", help="Input for echo tool")
    run_flow.add_argument("--a", type=int, default=1, help="First addend")
    run_flow.add_argument("--b", type=int, default=2, help="Second addend")
    run_flow.add_argument("--flow", default="echo_add", help="Deterministic flow name")
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
    run_graph.add_argument("--text", default="hello", help="Input text")
    run_graph.add_argument("--a", type=int, default=1, help="First addend")
    run_graph.add_argument("--b", type=int, default=2, help="Second addend")
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
        log_style="logster" if args.logster else "json",
        logster_config_path=args.logster_config,
    )
    command: Callable[[argparse.Namespace], int] = args.func
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
