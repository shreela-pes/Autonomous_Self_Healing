"""
ProjectCorrelationEngine — ML-based cross-resource correlation learning.

Learns temporal relationships between resource metrics within a project
by computing Pearson cross-correlation (with lag) on daily_history time series.

Unlike the rule-based CorrelationEngine, this discovers correlations from
observed data, not hardcoded domain rules. All results are qualified as
"statistical associations" and presented with confidence levels.

Key design decisions:
  - Lag range ±2 days: captures same-day co-movement and 1-2 day lead-lag effects
  - Min |r| = 0.65 with p-value < 0.05: reduces spurious correlations
  - Min 7 overlapping observations: prevents unreliable estimates from sparse data
  - Results capped at 20 per project: prevents prompt bloat
  - Cache TTL 6 hours: avoids recomputing on every document in batch mode
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.stats import pearsonr

logger = logging.getLogger(__name__)

_MIN_CORRELATION    = 0.65   # Pearson |r| threshold
_MIN_OVERLAP        = 7      # minimum common date points
_MAX_LAG_DAYS       = 2      # check lags: -2, -1, 0, +1, +2
_CACHE_TTL_HOURS    = 48     # recompute a resource's correlations at most every N hours of EVENT time
_MAX_RESULTS        = 20     # cap per project to keep prompts concise


@dataclass
class MetricCorrelation:
    """A learned statistical association between two (resource, metric) pairs."""
    resource_a_id:     str
    resource_a_type:   str
    resource_a_metric: str
    resource_b_id:     str
    resource_b_type:   str
    resource_b_metric: str
    correlation_r:     float    # Pearson r in [-1, 1]
    lag_days:          int      # 0=same-day; >0=A leads B; <0=B leads A
    n_observations:    int
    direction:         str      # "positive" | "negative"
    confidence:        str      # "low" | "medium" | "high"
    interpretation:    str

    def to_dict(self) -> dict:
        return {
            "resource_a_id":     self.resource_a_id,
            "resource_a_type":   self.resource_a_type,
            "resource_a_metric": self.resource_a_metric,
            "resource_b_id":     self.resource_b_id,
            "resource_b_type":   self.resource_b_type,
            "resource_b_metric": self.resource_b_metric,
            "correlation_r":     round(self.correlation_r, 3),
            "lag_days":          self.lag_days,
            "n_observations":    self.n_observations,
            "direction":         self.direction,
            "confidence":        self.confidence,
            "interpretation":    self.interpretation,
        }


class ProjectCorrelationEngine:
    """
    Maintains one correlation matrix per project, refreshed every _CACHE_TTL_HOURS.
    Call get_correlations_for_resource() to retrieve correlations involving a given resource.
    """

    def __init__(self) -> None:
        # project_id → (computed_at, list[MetricCorrelation])
        self._cache: dict[str, tuple[datetime, list[MetricCorrelation]]] = {}

    def get_correlations_for_resource(
        self,
        project_id:         str,
        target_resource_id: str,
        resource_profiles:  list[dict],
        as_of:              Optional[datetime] = None,
    ) -> list[MetricCorrelation]:
        """
        Returns correlations where target_resource_id is one of the two sides.
        Automatically recomputes if the project cache is stale.
        Returns [] if the project has fewer than 2 resources.
        """
        if not project_id or len(resource_profiles) < 2:
            return []

        now = as_of or datetime.now(timezone.utc)      # EVENT time when replaying history
        key = (project_id, target_resource_id)
        cached = self._cache.get(key)
        if cached:
            computed_at, all_corrs = cached
            age_hours = (now - computed_at).total_seconds() / 3600
            if 0 <= age_hours < _CACHE_TTL_HOURS:
                return all_corrs

        # Recompute (only pairs that involve the target resource)
        if callable(resource_profiles):
            resource_profiles = resource_profiles()      # load profiles lazily - only when a refresh is due
        try:
            all_corrs = _compute_correlations(resource_profiles, target=target_resource_id)
        except Exception as exc:
            logger.warning("Project correlation failed for %s: %s", project_id, exc)
            all_corrs = []

        self._cache[key] = (now, all_corrs)
        logger.debug(
            "Project %s: %d metric correlations across %d resources",
            project_id, len(all_corrs), len(resource_profiles),
        )
        return self._filter_for(all_corrs, target_resource_id)

    @staticmethod
    def _filter_for(
        corrs: list[MetricCorrelation],
        rid: str,
    ) -> list[MetricCorrelation]:
        return [c for c in corrs if c.resource_a_id == rid or c.resource_b_id == rid]


# ── Internal computation ───────────────────────────────────────────────────────

def _compute_correlations(resource_profiles: list[dict], target: Optional[str] = None) -> list[MetricCorrelation]:
    """
    Build date-aligned time series for every (resource, metric) pair, then
    compute pairwise Pearson cross-correlation at lags 0 to ±_MAX_LAG_DAYS.
    Returns statistically significant pairs with |r| >= _MIN_CORRELATION,
    sorted by |r| descending.
    """
    # Build: series[rid][metric] = {date_str: avg}
    series: dict[str, dict[str, dict[str, float]]] = {}
    rtypes: dict[str, str] = {}

    for profile in resource_profiles:
        rid = profile.get("_id")
        if not rid:
            continue
        rtypes[rid] = profile.get("resource_type", "unknown")
        series[rid] = {}

        for metric, mdata in (profile.get("metrics") or {}).items():
            if not isinstance(mdata, dict):
                continue
            history = mdata.get("daily_history") or []
            date_vals: dict[str, float] = {}
            for h in history:
                avg  = h.get("avg")
                date = h.get("date")
                if avg is None or avg != avg or date is None:   # skip None / NaN
                    continue
                key = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
                date_vals[key] = float(avg)
            if len(date_vals) >= _MIN_OVERLAP:
                series[rid][metric] = date_vals

    # Flatten to list of (rid, metric) pairs for indexed iteration
    all_pairs: list[tuple[str, str]] = [
        (rid, metric)
        for rid, metrics in series.items()
        for metric in metrics
    ]

    if len(all_pairs) < 2:
        return []

    results: list[MetricCorrelation] = []

    for i in range(len(all_pairs)):
        for j in range(i + 1, len(all_pairs)):
            rid_a, metric_a = all_pairs[i]
            rid_b, metric_b = all_pairs[j]

            # Same resource + same metric is always r=1 — skip
            if rid_a == rid_b and metric_a == metric_b:
                continue

            dates_a = series[rid_a][metric_a]
            dates_b = series[rid_b][metric_b]
            common  = sorted(set(dates_a.keys()) & set(dates_b.keys()))
            if len(common) < _MIN_OVERLAP:
                continue

            va = np.array([dates_a[d] for d in common], dtype=float)
            vb = np.array([dates_b[d] for d in common], dtype=float)

            # Standardise so correlations aren't driven by scale differences
            va = (va - va.mean()) / (va.std() + 1e-9)
            vb = (vb - vb.mean()) / (vb.std() + 1e-9)

            best_r, best_lag, best_n = 0.0, 0, len(common)
            for lag in range(-_MAX_LAG_DAYS, _MAX_LAG_DAYS + 1):
                if lag == 0:
                    a_sl, b_sl = va, vb
                elif lag > 0:
                    a_sl, b_sl = va[:-lag], vb[lag:]
                else:
                    a_sl, b_sl = va[-lag:], vb[:lag]

                n = len(a_sl)
                if n < _MIN_OVERLAP:
                    continue
                try:
                    r, p = pearsonr(a_sl, b_sl)
                except Exception:
                    continue
                if not np.isfinite(r) or p >= 0.05:    # require statistical significance
                    continue
                if abs(r) > abs(best_r):
                    best_r, best_lag, best_n = float(r), lag, n

            if abs(best_r) < _MIN_CORRELATION:
                continue

            corr = _make_result(
                rid_a, rtypes.get(rid_a, "unknown"), metric_a,
                rid_b, rtypes.get(rid_b, "unknown"), metric_b,
                best_r, best_lag, best_n,
            )
            results.append(corr)

    return sorted(results, key=lambda c: abs(c.correlation_r), reverse=True)[:_MAX_RESULTS]


def _make_result(
    rid_a: str, type_a: str, metric_a: str,
    rid_b: str, type_b: str, metric_b: str,
    r: float, lag: int, n: int,
) -> MetricCorrelation:
    direction = "positive" if r > 0 else "negative"

    if abs(r) >= 0.85 and n >= 14:
        confidence = "high"
    elif abs(r) >= 0.70 and n >= 10:
        confidence = "medium"
    else:
        confidence = "low"

    # Short labels to keep interpretation readable
    label_a = rid_a[-40:] if len(rid_a) > 40 else rid_a
    label_b = rid_b[-40:] if len(rid_b) > 40 else rid_b

    if lag == 0:
        timing = "at the same time"
    elif lag > 0:
        timing = f"{lag} day(s) before"
    else:
        timing = f"{abs(lag)} day(s) after"

    moves = "rises/falls together with" if direction == "positive" else "moves inversely to"

    interpretation = (
        f"{type_a}/{metric_a} ({label_a}) {moves} "
        f"{type_b}/{metric_b} ({label_b}) "
        f"[r={r:+.2f}, {timing}, n={n} days, {confidence} confidence]. "
        "Statistical association only — not a confirmed causal relationship."
    )

    return MetricCorrelation(
        resource_a_id     = rid_a,
        resource_a_type   = type_a,
        resource_a_metric = metric_a,
        resource_b_id     = rid_b,
        resource_b_type   = type_b,
        resource_b_metric = metric_b,
        correlation_r     = r,
        lag_days          = lag,
        n_observations    = n,
        direction         = direction,
        confidence        = confidence,
        interpretation    = interpretation,
    )
