from __future__ import annotations

from datetime import UTC, datetime

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskrunner.models import Task, TaskStatus, ToolCall, ToolCallStatus


def _duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=UTC)
    duration = (finished_at - started_at).total_seconds()
    return duration if duration >= 0 else None


def dump_metrics_snapshot(db: Session) -> str:
    registry = CollectorRegistry()
    task_counter = Counter(
        "taskrunner_tasks_total",
        "Total tasks by status",
        labelnames=("status",),
        registry=registry,
    )
    tool_call_counter = Counter(
        "taskrunner_tool_calls_total",
        "Total tool calls by status and tool name",
        labelnames=("status", "tool_name"),
        registry=registry,
    )
    tool_duration_histogram = Histogram(
        "taskrunner_tool_call_duration_seconds",
        "Tool call duration in seconds",
        labelnames=("status", "tool_name"),
        registry=registry,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
    )

    task_status_counts = db.execute(
        select(Task.status, func.count(Task.id)).group_by(Task.status)
    ).all()
    for status, count in task_status_counts:
        task_counter.labels(status=status.value).inc(count)
    for status in TaskStatus:
        task_counter.labels(status=status.value)

    tool_call_counts = db.execute(
        select(ToolCall.status, ToolCall.tool_name, func.count(ToolCall.id))
        .group_by(ToolCall.status, ToolCall.tool_name)
        .order_by(ToolCall.status, ToolCall.tool_name)
    ).all()
    for status, tool_name, count in tool_call_counts:
        tool_call_counter.labels(status=status.value, tool_name=tool_name).inc(count)
    for status in ToolCallStatus:
        for tool_name in ("log_summarizer", "threat_classifier", "incident_reporter"):
            tool_call_counter.labels(status=status.value, tool_name=tool_name)
            tool_duration_histogram.labels(status=status.value, tool_name=tool_name)

    durations = db.execute(
        select(
            ToolCall.status,
            ToolCall.tool_name,
            ToolCall.started_at,
            ToolCall.finished_at,
        )
    ).all()
    for status, tool_name, started_at, finished_at in durations:
        duration = _duration_seconds(started_at=started_at, finished_at=finished_at)
        if duration is None:
            continue
        tool_duration_histogram.labels(status=status.value, tool_name=tool_name).observe(duration)

    return generate_latest(registry).decode("utf-8")
