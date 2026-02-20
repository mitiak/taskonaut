from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from uuid import UUID

from taskrunner.db import SessionLocal
from taskrunner.schemas import TaskCreateRequest, TaskResponse
from taskrunner.service import TaskNotFoundError, TaskRunnerService


def run_flow_command(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        service = TaskRunnerService(session)
        task = service.run_predefined_flow(
            TaskCreateRequest(text=args.text, a=args.a, b=args.b)
        )
        print(json.dumps(TaskResponse.model_validate(task).model_dump(mode="json"), indent=2))
    return 0


def get_task_command(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        service = TaskRunnerService(session)
        try:
            task = service.get_task(UUID(args.task_id))
        except TaskNotFoundError as exc:
            print(str(exc))
            return 1
        print(json.dumps(TaskResponse.model_validate(task).model_dump(mode="json"), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taskrunner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_flow = subparsers.add_parser("run-flow", help="Run the predefined echo+add flow")
    run_flow.add_argument("--text", default="hello", help="Input for echo tool")
    run_flow.add_argument("--a", type=int, default=1, help="First addend")
    run_flow.add_argument("--b", type=int, default=2, help="Second addend")
    run_flow.set_defaults(func=run_flow_command)

    get_task = subparsers.add_parser("get-task", help="Fetch task by id")
    get_task.add_argument("task_id", help="Task UUID")
    get_task.set_defaults(func=get_task_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command: Callable[[argparse.Namespace], int] = args.func
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
