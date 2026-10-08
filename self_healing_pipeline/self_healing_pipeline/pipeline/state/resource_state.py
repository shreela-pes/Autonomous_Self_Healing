"""
ResourceStateManager -- maintains per-resource profiles in MongoDB.

Each document in resource_profiles represents ONE resource. It is built incrementally as
log documents for that resource arrive (one per metric per day).

Schema:
  _id               : resource_id
  project_id, resource_type, category, service_name, account_id, account_name,
  resource_name, location
  tags              : {app, tier, env, ...}  (lower-cased keys; used to infer topology)
  config            : merged config dict (instance type, disks, ...)
  operation_ids_seen
  metrics           : canonical_metric -> MetricState
      latest_points     : last 24 hourly points [{ts, value, max, min, avg}]
      observation_date  : the UTC day those points belong to
      daily_avg/max/min/std : of the latest day
      daily_history     : [{date, avg, max, min}]  last HISTORY_DAYS days (idempotent per date)
      hourly_baseline   : {"0".."6": {mean[24], scale[24], n}}  per weekday, learned on HEALTHY days only
      baseline_used     : the baseline the latest day was judged against {mean, scale, n} | null
      day_healthy       : whether the latest day fed the baseline
  alert_events      : [{alert_id, rule_id, metric, severity, state, fired_at, resolved_at, ...}]
                      (source alerts as they arrived; used for recurrence / flapping detection)
  current_alerts    : statistical status of every metric with a non-OK status (set by the engine)
"""

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pymongo

from ..config import (RESOURCE_PROFILES_COLLECTION, HISTORY_DAYS, BASELINE_ALPHA, BASELINE_MIN_SAMPLES)
from ..ingestion.normalizer import ParsedDoc
from ..analysis import features as F
from ..timeutil import as_utc

_MAX_ALERT_EVENTS = 400


class ResourceStateManager:
    def __init__(self, db: pymongo.database.Database):
        self.col = db[RESOURCE_PROFILES_COLLECTION]
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.col.create_index("project_id")
        self.col.create_index("resource_type")
        self.col.create_index("category")
        self.col.create_index([("project_id", 1), ("category", 1)])

    # ── write path ───────────────────────────────────────────────────────────

    def update(self, parsed: ParsedDoc) -> None:
        """Merge one parsed log document into the resource profile."""
        rid = parsed.resource_id
        now = datetime.now(timezone.utc)
        metric_key = parsed.canonical_metric

        prev = self.col.find_one(
            {"_id": rid},
            {f"metrics.{metric_key}": 1, "alert_events": 1} if metric_key else {"alert_events": 1},
        ) or {}
        prev_metric = ((prev.get("metrics") or {}).get(metric_key) or {}) if metric_key else {}

        sets = {
            "project_id":    parsed.project_id,
            "resource_type": parsed.resource_type,
            "category":      parsed.category,
            "service_name":  parsed.service_name,
            "account_id":    parsed.account_id,
            "account_name":  parsed.account_name,
            "resource_name": parsed.resource_name,
            "location":      parsed.location,
            "last_updated":  now,
        }
        tags = _tags_to_dict(parsed.tags)
        if tags:
            sets["tags"] = tags
        for k, v in parsed.config.items():
            if v is not None:
                sets[f"config.{k}"] = v

        update: dict = {"$set": sets}
        if parsed.operation_id:
            update["$addToSet"] = {"operation_ids_seen": parsed.operation_id}

        # ── source alerts -> alert_events (merged by alert_id) ────────────────
        if parsed.alerts:
            sets["alert_events"] = _merge_alert_events(prev.get("alert_events") or [], parsed.alerts)

        # ── metric time-series ────────────────────────────────────────────────
        if metric_key and parsed.points:
            values = np.array(
                [p.value if (p.value is not None and p.value == p.value) else np.nan for p in parsed.points],
                dtype=float,
            )
            finite = values[~np.isnan(values)]
            daily_avg = float(finite.mean()) if finite.size else None
            daily_max = float(finite.max()) if finite.size else None
            daily_min = float(finite.min()) if finite.size else None
            daily_std = float(finite.std()) if finite.size else None
            obs_date = parsed.from_date

            # baseline this day is judged against = weekday baseline learned BEFORE this day
            dow = str(obs_date.weekday())
            wb_prev = (prev_metric.get("hourly_baseline") or {}).get(dow)
            b_mean, b_scale = F.baseline_arrays(wb_prev, BASELINE_MIN_SAMPLES)
            feats = F.day_features(values, b_mean, b_scale)

            has_alert = any(True for _ in parsed.alerts)
            anomalous = (feats.get("resid_hours_high") or 0) > 2
            healthy = finite.size >= 18 and not has_alert and not anomalous
            already = as_utc(prev_metric.get("baseline_last_date")) == as_utc(obs_date)

            serialized_points = [
                {"ts": p.timestamp, "value": p.value if (p.value is not None and p.value == p.value) else None,
                 "max": p.daily_max, "min": p.daily_min, "avg": p.daily_avg}
                for p in parsed.points
            ]
            sets.update({
                f"metrics.{metric_key}.latest_points":     serialized_points,
                f"metrics.{metric_key}.observation_date":  obs_date,
                f"metrics.{metric_key}.daily_avg":         daily_avg,
                f"metrics.{metric_key}.daily_max":         daily_max,
                f"metrics.{metric_key}.daily_min":         daily_min,
                f"metrics.{metric_key}.daily_std":         daily_std,
                f"metrics.{metric_key}.last_updated":      now,
                f"metrics.{metric_key}.day_healthy":       bool(healthy),
                f"metrics.{metric_key}.baseline_used":
                    ({"mean": [None if x != x else float(x) for x in b_mean],
                      "scale": [None if x != x else float(x) for x in b_scale],
                      "n": int(wb_prev.get("n", 0))} if b_mean is not None else None),
            })
            if healthy and not already:
                sets[f"metrics.{metric_key}.hourly_baseline.{dow}"] = F.update_hourly_baseline(
                    wb_prev, values, BASELINE_ALPHA)
                sets[f"metrics.{metric_key}.baseline_last_date"] = obs_date

            # idempotent rolling daily history (re-delivered docs replace, never duplicate)
            if daily_avg is not None:
                okey = obs_date.strftime("%Y-%m-%d")
                hist = [h for h in (prev_metric.get("daily_history") or [])
                        if h.get("date") is not None and as_utc(h["date"]).strftime("%Y-%m-%d") != okey]
                hist.append({"date": obs_date, "avg": daily_avg, "max": daily_max, "min": daily_min})
                hist.sort(key=lambda h: as_utc(h["date"]))
                sets[f"metrics.{metric_key}.daily_history"] = hist[-HISTORY_DAYS:]

        self.col.update_one({"_id": rid}, update, upsert=True)

    def update_alerts(self, resource_id: str, alerts: list) -> None:
        self.col.update_one(
            {"_id": resource_id},
            {"$set": {"current_alerts": alerts, "last_alert_update": datetime.now(timezone.utc)}},
        )

    # ── read path ────────────────────────────────────────────────────────────

    def get(self, resource_id: str) -> Optional[dict]:
        return self.col.find_one({"_id": resource_id})

    def get_project_resources(self, project_id: str) -> list[dict]:
        return list(self.col.find({"project_id": project_id}))

    def get_project_index(self, project_id: str) -> dict:
        """{resource_id: {tags, resource_name, resource_type, category}} - cheap topology lookup."""
        out = {}
        for d in self.col.find({"project_id": project_id},
                               {"tags": 1, "resource_name": 1, "resource_type": 1, "category": 1}):
            out[d["_id"]] = d
        return out

    def iter_all(self):
        return self.col.find({})


# ── helpers ────────────────────────────────────────────────────────────────────

def _tags_to_dict(tags) -> dict:
    out = {}
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict) and t.get("key") is not None:
                out[str(t["key"]).lower()] = t.get("value")
    elif isinstance(tags, dict):
        out = {str(k).lower(): v for k, v in tags.items()}
    return out


def _merge_alert_events(existing: list, alerts: list) -> list:
    by_id = {e["alert_id"]: e for e in existing if e.get("alert_id")}
    for a in alerts:
        prev = by_id.get(a.alert_id, {})
        by_id[a.alert_id] = {
            "alert_id": a.alert_id, "rule_id": a.rule_id, "rule_name": a.rule_name,
            "metric": a.metric, "severity": a.severity, "op": a.op,
            "threshold": a.threshold, "observed": a.observed, "expected": a.expected,
            "condition_type": a.condition_type,
            "fired_at": a.fired_at,
            # a later doc may add the resolution time; never lose it once known
            "resolved_at": a.resolved_at or prev.get("resolved_at"),
            "state": "Resolved" if (a.resolved_at or prev.get("resolved_at")) else a.state,
        }
    events = sorted(by_id.values(), key=lambda e: as_utc(e.get("fired_at")) or datetime.min.replace(tzinfo=timezone.utc))
    return events[-_MAX_ALERT_EVENTS:]
