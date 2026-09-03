from __future__ import annotations

from typing import Any, Mapping


MIN_EVENT_LOOP_LAG_SAMPLES = 10

# These limits deliberately assess scheduler responsiveness rather than RF
# airtime.  They therefore work when no interface is currently carrying
# traffic and provide a useful signal for modest hardware.
EVENT_LOOP_SCORE_LIMITS_MS = (
    (15.0, 5, "Excellent", "ok"),
    (40.0, 4, "Good", "ok"),
    (100.0, 3, "Sufficient", "neutral"),
    (250.0, 2, "Marginal", "warn"),
)


def evaluate_digi_performance(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify the current health of the APRSBox core installation.

    The name is retained because it is the existing dashboard API, but this is
    intentionally not a DIGI throughput benchmark.  The primary signal is
    recent event-loop lag, which is sampled continuously, with queue pressure
    and recent frame loss acting as safety limits.
    """
    payload = dict(snapshot or {})
    if str(payload.get("status") or "").lower() == "unavailable":
        return _result(
            status="unavailable",
            score=None,
            label=None,
            tone="error",
            event_loop_p95_ms=None,
            queue_utilisation=None,
            queue_name=None,
            stale_drops=0,
            queue_overflows=0,
        )

    event_loop = _mapping(payload.get("event_loop_lag_ms"))
    rf_dispatcher = _mapping(payload.get("rf_tx_dispatcher"))
    digiflow_queue = _mapping(payload.get("digiflow_queue"))
    aprsis_queue = _mapping(payload.get("aprsis_tx_dispatcher"))
    rx_side_effect_queue = _mapping(payload.get("rx_side_effect_dispatcher"))

    sample_count = _nonnegative_int(event_loop.get("sample_count"))
    p95_ms = _optional_nonnegative_float(event_loop.get("p95_ms"))
    stale_drops = _nonnegative_int(rf_dispatcher.get("recent_stale_digi_tx_drops"))
    queue_overflows = (
        _nonnegative_int(rf_dispatcher.get("recent_queue_overflows"))
        + _nonnegative_int(digiflow_queue.get("recent_queue_overflows"))
    )
    queue_name, queue_utilisation = _worst_queue_utilisation(
        ("DIGI Flow", digiflow_queue),
        ("RF TX", rf_dispatcher),
        ("APRS-IS TX", aprsis_queue),
        ("RX side effects", rx_side_effect_queue),
    )

    if stale_drops > 0 or queue_overflows > 0:
        return _result(
            status="ready",
            score=1,
            label="Insufficient",
            tone="error",
            event_loop_p95_ms=p95_ms,
            queue_utilisation=queue_utilisation,
            queue_name=queue_name,
            stale_drops=stale_drops,
            queue_overflows=queue_overflows,
        )
    if sample_count < MIN_EVENT_LOOP_LAG_SAMPLES or p95_ms is None:
        return _result(
            status="warming",
            score=None,
            label=None,
            tone="neutral",
            event_loop_p95_ms=p95_ms,
            queue_utilisation=queue_utilisation,
            queue_name=queue_name,
            stale_drops=stale_drops,
            queue_overflows=queue_overflows,
        )

    score, label, tone = _score_for_event_loop_lag(p95_ms)
    if queue_utilisation is not None:
        if queue_utilisation >= 0.90:
            score = min(score, 1)
        elif queue_utilisation >= 0.60:
            score = min(score, 2)
        elif queue_utilisation >= 0.25:
            score = min(score, 3)
    label, tone = _label_and_tone_for_score(score)
    return _result(
        status="ready",
        score=score,
        label=label,
        tone=tone,
        event_loop_p95_ms=p95_ms,
        queue_utilisation=queue_utilisation,
        queue_name=queue_name,
        stale_drops=stale_drops,
        queue_overflows=queue_overflows,
    )


def _result(**values: Any) -> dict[str, Any]:
    values["minimum_samples"] = MIN_EVENT_LOOP_LAG_SAMPLES
    return values


def _score_for_event_loop_lag(p95_ms: float) -> tuple[int, str, str]:
    for limit_ms, score, label, tone in EVENT_LOOP_SCORE_LIMITS_MS:
        if p95_ms <= limit_ms:
            return score, label, tone
    return 1, "Insufficient", "error"


def _label_and_tone_for_score(score: int) -> tuple[str, str]:
    return {
        5: ("Excellent", "ok"),
        4: ("Good", "ok"),
        3: ("Sufficient", "neutral"),
        2: ("Marginal", "warn"),
    }.get(score, ("Insufficient", "error"))


def _worst_queue_utilisation(
    *queues: tuple[str, Mapping[str, Any]],
) -> tuple[str | None, float | None]:
    worst_name: str | None = None
    worst_ratio: float | None = None
    for name, queue in queues:
        explicit_ratio = queue.get("max_queue_utilisation")
        if explicit_ratio is not None:
            ratio = min(1.0, _nonnegative_float(explicit_ratio))
            if worst_ratio is None or ratio > worst_ratio:
                worst_name, worst_ratio = name, ratio
            continue
        capacity = _positive_float(queue.get("capacity") or queue.get("queue_capacity"))
        if capacity is None:
            continue
        ratio = _nonnegative_float(queue.get("current_depth") or queue.get("current_queue_depth")) / capacity
        if worst_ratio is None or ratio > worst_ratio:
            worst_name, worst_ratio = name, min(1.0, ratio)
    return worst_name, worst_ratio


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


def _nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _optional_nonnegative_float(value: Any) -> float | None:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None
