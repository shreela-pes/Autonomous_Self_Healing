"""
StatisticalEngine — per-resource metric analysis.

For each metric in a resource profile, produces an AlertResult that combines:
  1. Static threshold check (WARN / CRIT)
  2. Trend analysis (linear slope on 24 hourly points → hours to breach)
  3. Anomaly detection (z-score against daily_history baseline)

Uses daily_max for "upper" thresholds and daily_min for "lower" thresholds.
"nonzero" thresholds trigger on any positive peak value.
"anomaly_only" metrics produce a result only if the z-score exceeds the threshold.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..metrics.thresholds import get_threshold
from ..config import (ANOMALY_ZSCORE_THRESHOLD, TREND_HOURS_TO_BREACH_WARN, PREDICTIVE_ALERTS_ENABLED,
                      BASELINE_MIN_SAMPLES, HISTORY_DAYS)
from . import features as F


@dataclass
class AlertResult:
    metric: str
    status: str              # OK | WARN | CRIT | ANOMALY | NO_DATA
    current_value: Optional[float] = None   # daily_max (upper) or daily_min (lower)
    daily_avg: Optional[float] = None
    daily_max: Optional[float] = None
    daily_min: Optional[float] = None
    trend_slope: Optional[float] = None     # units per hour
    trend_direction: str = "stable"         # rising | falling | stable | spike | drop
    anomaly_score: Optional[float] = None   # z-score
    hours_to_breach: Optional[float] = None # None if no breach predicted
    threshold_warn: Optional[float] = None
    threshold_crit: Optional[float] = None
    direction: str = "upper"
    note: str = ""
    # ── Pre-computed anomaly facts (LLM must not re-derive these) ────────────
    historical_mean: Optional[float] = None      # 30-day daily-avg mean
    historical_std: Optional[float] = None
    pct_deviation: Optional[float] = None        # (current - hist_mean) / hist_mean * 100
    change_magnitude: str = ""                   # e.g. "+18%", "-9%"
    detected_by: str = ""                        # "threshold" | "zscore" | "trend" | "threshold+zscore"
    # -- Seasonality / trend evidence (feeds the RCA engine) ------------------
    features: dict = field(default_factory=dict)  # within-day features (ratio to baseline, jumps, ...)
    history: dict = field(default_factory=dict)   # multi-day features (slopes, shape, seasonal baseline)
    baseline_source: str = ""                     # "weekday-hourly" | "weekday-daily" | "history" | ""

    def to_dict(self) -> dict:
        return {
            "metric":           self.metric,
            "status":           self.status,
            "current_value":    self.current_value,
            "daily_avg":        self.daily_avg,
            "daily_max":        self.daily_max,
            "daily_min":        self.daily_min,
            "trend_slope":      self.trend_slope,
            "trend_direction":  self.trend_direction,
            "anomaly_score":    self.anomaly_score,
            "hours_to_breach":  self.hours_to_breach,
            "threshold_warn":   self.threshold_warn,
            "threshold_crit":   self.threshold_crit,
            "direction":        self.direction,
            "note":             self.note,
            "historical_mean":  self.historical_mean,
            "historical_std":   self.historical_std,
            "pct_deviation":    self.pct_deviation,
            "change_magnitude": self.change_magnitude,
            "detected_by":      self.detected_by,
            "features":         self.features,
            "history":          self.history,
            "baseline_source":  self.baseline_source,
        }


class StatisticalEngine:
    def analyze_resource(self, resource_profile: dict) -> list[AlertResult]:
        """
        Analyze all metrics in a resource profile.
        Returns one AlertResult per metric that has data (status OK included).
        """
        resource_type = resource_profile.get("resource_type", "")
        metrics_data  = resource_profile.get("metrics") or {}
        config        = resource_profile.get("config") or {}
        results = []

        for canonical_metric, metric_data in metrics_data.items():
            if not isinstance(metric_data, dict):
                continue
            result = self._analyze_metric(
                resource_type, canonical_metric, metric_data, config
            )
            if result:
                results.append(result)

        return results

    def _analyze_metric(
        self,
        resource_type: str,
        canonical_metric: str,
        metric_data: dict,
        config: dict,
    ) -> Optional[AlertResult]:
        daily_avg = metric_data.get("daily_avg")
        daily_max = metric_data.get("daily_max")
        daily_min = metric_data.get("daily_min")

        if daily_avg is None and daily_max is None:
            return AlertResult(metric=canonical_metric, status="NO_DATA")

        values = F.hourly_values(metric_data)
        clean = [float(x) for x in values if x == x]

        threshold_cfg = get_threshold(resource_type, canonical_metric)
        if resource_type == "Storage_Disks":
            threshold_cfg = self._disk_dynamic_threshold(canonical_metric, config, threshold_cfg)
        if threshold_cfg is None:
            threshold_cfg = {"warn": None, "crit": None, "direction": "anomaly_only"}

        direction = threshold_cfg.get("direction", "anomaly_only")
        warn_val  = threshold_cfg.get("warn")
        crit_val  = threshold_cfg.get("crit")

        if direction == "upper":
            check_val = daily_max
        elif direction == "lower":
            check_val = daily_min
        elif direction == "nonzero":
            check_val = daily_max
        else:
            check_val = daily_avg

        # -- 1. static threshold ------------------------------------------------
        status = self._threshold_status(direction, check_val, warn_val, crit_val)

        # -- 2. within-day trend (kept for backward compatibility) ---------------
        trend_slope, trend_direction, hours_to_breach = None, "stable", None
        if len(clean) >= 3:
            trend_slope, trend_direction = self._compute_trend(clean)
            if trend_slope is not None and warn_val is not None and status in ("OK", "WARN"):
                hours_to_breach = self._predict_breach(clean, direction, warn_val, crit_val, trend_slope)
        note = ""
        if (PREDICTIVE_ALERTS_ENABLED and status == "OK" and hours_to_breach is not None
                and hours_to_breach <= TREND_HOURS_TO_BREACH_WARN):
            status = "WARN"
            note = f"Trending toward threshold -- breach in ~{hours_to_breach:.0f}h"
        elif not PREDICTIVE_ALERTS_ENABLED:
            hours_to_breach = None        # informational forecasts are not surfaced in reactive mode

        # -- 3. seasonality-aware baselines -------------------------------------
        b = metric_data.get("baseline_used") or None
        b_mean, b_scale = F.baseline_arrays(b, BASELINE_MIN_SAMPLES)
        feats = F.day_features(values, b_mean, b_scale)
        obs_date = metric_data.get("observation_date")
        hist = F.history_features(metric_data.get("daily_history") or [], obs_date, daily_avg)

        anomaly_score, hist_mean_val = F.robust_z(daily_avg, hist)
        hist_std_val = hist.get("seasonal_mad") if hist.get("n_same_weekday", 0) >= 4 else hist.get("hist_std")
        baseline_source = ("weekday-hourly" if b_mean is not None
                           else "weekday-daily" if hist.get("n_same_weekday", 0) >= 4
                           else "history" if hist.get("n_history_days", 0) >= 5 else "")

        anomalous = (
            (anomaly_score is not None and anomaly_score >= ANOMALY_ZSCORE_THRESHOLD)
            or (feats.get("resid_hours_high") or 0) >= 3
        )
        if anomalous and status == "OK":
            status = "ANOMALY"
            if (feats.get("resid_hours_high") or 0) >= 3:
                note = f"{feats['resid_hours_high']} hour(s) deviate >=3 sigma from the {baseline_source} baseline"
            else:
                note = f"robust z-score={anomaly_score:.1f} vs {baseline_source} baseline"

        detected_by = _build_detected_by(status, anomaly_score, hours_to_breach)
        pct_dev, change_mag = _compute_change(daily_avg, hist_mean_val)

        if anomalous and daily_avg is not None and hist_mean_val is not None:
            trend_direction = "spike" if daily_avg > hist_mean_val else "drop"

        return AlertResult(
            metric           = canonical_metric,
            status           = status,
            current_value    = check_val,
            daily_avg        = daily_avg,
            daily_max        = daily_max,
            daily_min        = daily_min,
            trend_slope      = trend_slope,
            trend_direction  = trend_direction,
            anomaly_score    = anomaly_score,
            hours_to_breach  = hours_to_breach,
            threshold_warn   = warn_val,
            threshold_crit   = crit_val,
            direction        = direction,
            note             = note,
            historical_mean  = hist_mean_val,
            historical_std   = hist_std_val,
            pct_deviation    = pct_dev,
            change_magnitude = change_mag,
            detected_by      = detected_by,
            features         = feats,
            history          = hist,
            baseline_source  = baseline_source,
        )

    @staticmethod
    def _threshold_status(direction, value, warn, crit) -> str:
        if value is None:
            return "NO_DATA"
        if direction == "upper":
            if crit is not None and value >= crit:
                return "CRIT"
            if warn is not None and value >= warn:
                return "WARN"
        elif direction == "lower":
            if crit is not None and value <= crit:
                return "CRIT"
            if warn is not None and value <= warn:
                return "WARN"
        elif direction == "nonzero":
            if value > 0:
                return "CRIT"  # any non-zero is immediately critical
        return "OK"

    @staticmethod
    def _compute_trend(values: list[float]):
        """Linear regression on evenly spaced hourly values. Returns (slope_per_hour, direction)."""
        n = len(values)
        x = np.arange(n, dtype=float)
        y = np.array(values, dtype=float)
        if np.std(y) < 1e-9:
            return 0.0, "stable"
        slope = float(np.polyfit(x, y, 1)[0])
        if slope > 0.05:
            direction = "rising"
        elif slope < -0.05:
            direction = "falling"
        else:
            direction = "stable"
        return slope, direction

    @staticmethod
    def _predict_breach(values, direction, warn_val, crit_val, slope_per_hour) -> Optional[float]:
        """Estimate hours until warn threshold is breached given current slope."""
        if slope_per_hour == 0:
            return None
        current = float(values[-1]) if values else None
        if current is None:
            return None
        target = warn_val
        if direction == "upper" and slope_per_hour > 0:
            if current >= target:
                return 0.0
            return (target - current) / slope_per_hour
        elif direction == "lower" and slope_per_hour < 0:
            if current <= target:
                return 0.0
            return (current - target) / abs(slope_per_hour)
        return None

    @staticmethod
    def _disk_dynamic_threshold(canonical_metric: str, config: dict, fallback: dict) -> dict:
        """Compute Storage_Disks thresholds from provisioned disk_iops / disk_mbps."""
        provisioned_iops = config.get("disk_iops")
        provisioned_mbps = config.get("disk_mbps")
        if canonical_metric in ("disk_read_ops_per_sec", "disk_write_ops_per_sec") and provisioned_iops:
            return {
                "warn":      provisioned_iops * 0.80,
                "crit":      provisioned_iops * 0.95,
                "direction": "upper",
            }
        if canonical_metric in ("disk_read_bytes_per_sec", "disk_write_bytes_per_sec") and provisioned_mbps:
            return {
                "warn":      provisioned_mbps * 1_000_000 * 0.80,
                "crit":      provisioned_mbps * 1_000_000 * 0.95,
                "direction": "upper",
            }
        return fallback or {"warn": None, "crit": None, "direction": "anomaly_only"}

    @staticmethod
    def overall_status(alert_results: list[AlertResult]) -> str:
        """Roll up a list of AlertResults to the worst single status."""
        rank = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}
        worst = "OK"
        for r in alert_results:
            if rank.get(r.status, 0) > rank.get(worst, 0):
                worst = r.status
        return worst

    @staticmethod
    def derive_cpu_from_idle(alert_results: list[AlertResult]) -> list[AlertResult]:  # noqa: C901
        """
        If cpu_idle_pct is present but cpu_pct is missing or NO_DATA,
        synthesise a cpu_pct AlertResult from cpu_idle_pct.
        """
        has_cpu = any(r.metric == "cpu_pct" and r.status != "NO_DATA" for r in alert_results)
        if has_cpu:
            return alert_results
        idle_result = next((r for r in alert_results if r.metric == "cpu_idle_pct"), None)
        if idle_result and idle_result.daily_avg is not None:
            derived_avg = 100.0 - idle_result.daily_avg
            derived_max = (100.0 - idle_result.daily_min) if idle_result.daily_min is not None else None
            # Determine status from cpu_pct thresholds
            from ..metrics.thresholds import get_threshold
            # We don't know resource_type here so use a generic rule
            warn, crit = 75, 90
            status = "OK"
            if derived_max and derived_max >= crit:
                status = "CRIT"
            elif derived_max and derived_max >= warn:
                status = "WARN"
            alert_results.append(AlertResult(
                metric="cpu_pct", status=status,
                current_value=derived_max, daily_avg=derived_avg,
                note="derived from cpu_idle_pct",
                detected_by="derived",
            ))
        return alert_results


# ── Module-level helpers (not part of the class) ──────────────────────────────

def _build_detected_by(status: str, anomaly_score, hours_to_breach) -> str:
    parts = []
    if status in ("WARN", "CRIT"):
        parts.append("threshold")
    if anomaly_score is not None:
        parts.append("zscore")
    if hours_to_breach is not None:
        parts.append("trend")
    return "+".join(parts) if parts else "threshold"


def _compute_change(
    current_avg: Optional[float], hist_mean: Optional[float]
) -> tuple[Optional[float], str]:
    """Return (pct_deviation, human-readable change string)."""
    if current_avg is None or hist_mean is None or hist_mean == 0:
        return None, ""
    pct = (current_avg - hist_mean) / abs(hist_mean) * 100
    sign = "+" if pct >= 0 else ""
    return pct, f"{sign}{pct:.1f}% vs seasonal baseline"
