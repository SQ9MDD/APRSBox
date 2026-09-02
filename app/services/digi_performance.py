from __future__ import annotations

from typing import Any, Mapping


DIGI_STALE_LIMIT_MS = 5_000.0
MIN_RF_DIGI_HOT_PATH_SAMPLES = 50


def evaluate_digi_performance(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify current RF DIGI headroom from the bounded core latency snapshot."""
    payload = dict(snapshot or {})
    hot_path = _mapping(payload.get("rf_digi_hot_path_ms"))
    rf_dispatcher = _mapping(payload.get("rf_tx_dispatcher"))
    digiflow_queue = _mapping(payload.get("digiflow_queue"))

    sample_count = _nonnegative_int(hot_path.get("sample_count"))
    p99_ms = _positive_float(hot_path.get("p99_ms"))
    stale_drops = _nonnegative_int(rf_dispatcher.get("recent_stale_digi_tx_drops"))
    queue_overflows = (
        _nonnegative_int(rf_dispatcher.get("recent_queue_overflows"))
        + _nonnegative_int(digiflow_queue.get("recent_queue_overflows"))
    )
    forced_insufficient = stale_drops > 0 or queue_overflows > 0

    if forced_insufficient:
        return _result(
            status="ready",
            score=1,
            label="Insufficient",
            tone="error",
            headroom_multiplier=DIGI_STALE_LIMIT_MS / p99_ms if p99_ms is not None else None,
            p99_hot_path_ms=p99_ms,
            sample_count=sample_count,
            stale_drops=stale_drops,
            queue_overflows=queue_overflows,
            forced_insufficient=True,
        )
    if sample_count < MIN_RF_DIGI_HOT_PATH_SAMPLES or p99_ms is None:
        return _result(
            status="collecting",
            score=None,
            label=None,
            tone="neutral",
            headroom_multiplier=None,
            p99_hot_path_ms=p99_ms,
            sample_count=sample_count,
            stale_drops=stale_drops,
            queue_overflows=queue_overflows,
            forced_insufficient=False,
        )

    headroom = DIGI_STALE_LIMIT_MS / p99_ms
    if headroom >= 10.0:
        score, label, tone = 5, "Excellent", "ok"
    elif headroom >= 5.0:
        score, label, tone = 4, "Good", "ok"
    elif headroom >= 2.0:
        score, label, tone = 3, "Fair", "neutral"
    elif headroom >= 1.0:
        score, label, tone = 2, "Marginal", "warn"
    else:
        score, label, tone = 1, "Insufficient", "error"
    return _result(
        status="ready",
        score=score,
        label=label,
        tone=tone,
        headroom_multiplier=headroom,
        p99_hot_path_ms=p99_ms,
        sample_count=sample_count,
        stale_drops=stale_drops,
        queue_overflows=queue_overflows,
        forced_insufficient=False,
    )


def _result(**values: Any) -> dict[str, Any]:
    values["minimum_samples"] = MIN_RF_DIGI_HOT_PATH_SAMPLES
    return values


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None
