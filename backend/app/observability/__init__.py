"""Observability module: health checks and Prometheus-style metrics."""

from app.observability.metrics import (
    MetricsCollector,
    get_metrics_collector,
    metrics_endpoint,
)

__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "metrics_endpoint",
]
