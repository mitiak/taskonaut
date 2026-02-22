from __future__ import annotations

from taskrunner.cli import (
    advance_task_command,
    build_parser,
    get_tasks_command,
    run_app_command,
    run_graph_command,
    run_task_command,
)


def test_parser_supports_run_app_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-app", "--host", "0.0.0.0", "--port", "9000", "--reload"])

    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.reload is True
    assert args.func is run_app_command


def test_parser_supports_get_tasks_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["get-tasks"])

    assert args.func is get_tasks_command


def test_parser_supports_advance_task_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["advance-task", "123e4567-e89b-12d3-a456-426614174000"])

    assert args.func is advance_task_command


def test_parser_supports_run_task_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["run-task", "123e4567-e89b-12d3-a456-426614174000", "--max-steps", "5"]
    )

    assert args.func is run_task_command
    assert args.max_steps == 5


def test_parser_supports_api_base_url_option() -> None:
    parser = build_parser()
    args = parser.parse_args(["--api-base-url", "http://127.0.0.1:9000", "get-tasks"])

    assert args.api_base_url == "http://127.0.0.1:9000"


def test_parser_supports_run_graph_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-graph", "--flow", "echo_add", "--max-steps", "7"])

    assert args.func is run_graph_command
    assert args.flow == "echo_add"
    assert args.max_steps == 7
