from __future__ import annotations

from taskrunner.cli import build_parser, get_tasks_command, run_app_command


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


def test_parser_supports_api_base_url_option() -> None:
    parser = build_parser()
    args = parser.parse_args(["--api-base-url", "http://127.0.0.1:9000", "get-tasks"])

    assert args.api_base_url == "http://127.0.0.1:9000"
