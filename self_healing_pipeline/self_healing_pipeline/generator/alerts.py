"""
Alert evaluation over the generated hourly series.

This mimics what a cloud alert rule does (CloudWatch alarm / Azure Monitor metric alert /
GCP alert policy): evaluate a condition on hourly aggregates, fire after N consecutive
violating periods, resolve after the first healthy period.  Static rules cover cpu /
memory / credits / disk; "dynamic" rules (seasonal band = same hour-of-week median of the
previous four weeks) cover network surge and traffic loss - exactly how Azure dynamic
thresholds / CloudWatch anomaly-detection alarms behave.

Warning and Critical are separate rules, so an escalating problem produces two alert
objects, and a metric that hovers around a threshold produces many short alert episodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# role -> list of (severity, op, threshold, eval_hours)
STATIC_RULES = {
    "cpu":        [("Warning", ">", 75.0, 2), ("Critical", ">", 90.0, 2)],
    "mem":        [("Warning", ">", 75.0, 2), ("Critical", ">", 90.0, 2)],
    "credit":     [("Warning", "<", 20.0, 1), ("Critical", "<", 5.0, 1)],
    "sched_wait": [("Warning", ">", 300.0, 2), ("Critical", ">", 1200.0, 2)],
    "disk":       [("Warning", ">", 75.0, 1), ("Critical", ">", 90.0, 1)],
}
# dynamic rules: (severity, kind, factor, eval_hours)
DYNAMIC_RULES = {
    "net_in":  [("Warning", "surge", 2.5, 2), ("Critical", "surge", 5.0, 2), ("Critical", "drop", 0.15, 3)],
    "net_out": [("Warning", "surge", 2.5, 2), ("Critical", "surge", 5.0, 2), ("Critical", "drop", 0.15, 3)],
}
DYNAMIC_WARMUP_HOURS = 28 * 24
MIN_BASELINE_BYTES = 1.0e8


@dataclass
class Episode:
    role: str
    severity: str
    op: str                      # ">" "<" or "surge" "drop"
    threshold: float             # static threshold, or dynamic multiplier
    eval_hours: int
    fired_idx: int               # hour index at which the eval window completed
    resolved_idx: Optional[int]
    observed: float
    baseline: Optional[float] = None
    condition: str = "static"    # static | dynamic


def _seasonal_baseline(values, i, weeks=4):
    samples = [values[i - 168 * k] for k in range(1, weeks + 1) if i - 168 * k >= 0]
    samples = [s for s in samples if s == s]
    return float(np.median(samples)) if samples else np.nan


def _episodes_from_flags(flags, eval_hours):
    """Yield (fire_idx, resolve_idx|None) from a boolean violation array."""
    n = len(flags)
    out, active, fire = [], False, None
    run = 0
    for i in range(n):
        if flags[i] is None:          # no data -> keep state
            continue
        if flags[i]:
            run += 1
            if not active and run >= eval_hours:
                active, fire = True, i
        else:
            run = 0
            if active:
                out.append((fire, i))
                active, fire = False, None
    if active:
        out.append((fire, None))
    return out


def evaluate(role: str, values: np.ndarray) -> list[Episode]:
    eps: list[Episode] = []
    n = len(values)

    for sev, op, thr, ev in STATIC_RULES.get(role, []):
        flags = []
        for v in values:
            if v != v:
                flags.append(None)
            else:
                flags.append(bool(v > thr) if op == ">" else bool(v < thr))
        for fire, res in _episodes_from_flags(flags, ev):
            win = values[max(fire - ev + 1, 0): fire + 1]
            obs = float(np.nanmax(win) if op == ">" else np.nanmin(win))
            eps.append(Episode(role, sev, op, thr, ev, fire, res, obs))

    for sev, kind, factor, ev in DYNAMIC_RULES.get(role, []):
        flags, base = [], np.full(n, np.nan)
        for i in range(n):
            v = values[i]
            if i < DYNAMIC_WARMUP_HOURS or v != v:
                flags.append(None if v != v else False)
                continue
            b = _seasonal_baseline(values, i)
            base[i] = b
            if not (b == b) or b < MIN_BASELINE_BYTES:
                flags.append(False)
                continue
            flags.append(bool(v > b * factor) if kind == "surge" else bool(v < b * factor))
        for fire, res in _episodes_from_flags(flags, ev):
            win = values[max(fire - ev + 1, 0): fire + 1]
            obs = float(np.nanmax(win) if kind == "surge" else np.nanmin(win))
            eps.append(Episode(role, sev, kind, factor, ev, fire, res, obs,
                               baseline=float(base[fire]) if base[fire] == base[fire] else None,
                               condition="dynamic"))
    eps.sort(key=lambda e: (e.fired_idx, e.severity))
    return eps
