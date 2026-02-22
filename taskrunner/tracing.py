from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_TRACING_CONFIGURED = False


def _resolve_otlp_traces_endpoint() -> str:
    explicit = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if explicit:
        return explicit

    base = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    return f"{base.rstrip('/')}/v1/traces"


def configure_tracing(service_name: str = "taskrunner") -> None:
    global _TRACING_CONFIGURED
    if _TRACING_CONFIGURED:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    span_exporter = OTLPSpanExporter(endpoint=_resolve_otlp_traces_endpoint())
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    _TRACING_CONFIGURED = True


def get_tracer(name: str = "taskrunner") -> Any:
    return trace.get_tracer(name)


def format_trace_id(trace_id: int) -> str:
    return f"{trace_id:032x}" if trace_id else ""


def format_span_id(span_id: int) -> str:
    return f"{span_id:016x}" if span_id else ""
