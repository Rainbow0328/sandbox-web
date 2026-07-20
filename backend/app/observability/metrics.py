"""Prometheus-style metrics collection and /metrics endpoint.

v0.1 uses a simple in-memory collector. For production, swap to
prometheus_client or OpenTelemetry.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from fastapi.responses import PlainTextResponse


class MetricsCollector:
    """Thread-safe in-memory metrics collector."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, dict[str, float]] = defaultdict(dict)
        self._gauges: dict[str, dict[str, float]] = defaultdict(dict)
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def inc_counter(self, name: str, labels: dict[str, str], value: float = 1) -> None:
        """Increment a labeled counter."""
        key = self._labels_key(labels)
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0) + value

    def set_gauge(self, name: str, labels: dict[str, str], value: float) -> None:
        """Set a labeled gauge."""
        key = self._labels_key(labels)
        with self._lock:
            self._gauges[name][key] = value

    def observe_histogram(self, name: str, value: float) -> None:
        """Observe a histogram value (simplified — stores all values)."""
        with self._lock:
            self._histograms[name].append(value)

    def _labels_key(self, labels: dict[str, str]) -> str:
        return ",".join(f"{k}=\"{v}\"" for k, v in sorted(labels.items()))

    def render_prometheus(self) -> str:
        """Render all metrics in Prometheus text format."""
        lines: list[str] = []

        with self._lock:
            # Counters
            for name in sorted(self._counters):
                lines.append(f"# TYPE {name} counter")
                for label_key, value in sorted(self._counters[name].items()):
                    lines.append(f"{name}{{{label_key}}} {value}")

            # Gauges
            for name in sorted(self._gauges):
                lines.append(f"# TYPE {name} gauge")
                for label_key, value in sorted(self._gauges[name].items()):
                    lines.append(f"{name}{{{label_key}}} {value}")

            # Histograms (simplified summary)
            for name in sorted(self._histograms):
                values = self._histograms[name]
                if not values:
                    continue
                lines.append(f"# TYPE {name} summary")
                count = len(values)
                total = sum(values)
                avg = total / count if count else 0
                lines.append(f'{name}_count {count}')
                lines.append(f'{name}_sum {total}')
                lines.append(f'{name}_avg {avg}')

        return "\n".join(lines) + "\n"


_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Return the singleton metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


async def metrics_endpoint() -> PlainTextResponse:
    """FastAPI endpoint: GET /metrics — Prometheus text format."""
    collector = get_metrics_collector()
    return PlainTextResponse(
        collector.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
