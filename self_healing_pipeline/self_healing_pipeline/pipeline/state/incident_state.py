"""
IncidentManager -- groups the cloud's raw alerts into incidents (event-time based).

Why: a real fault rarely raises one alert.  A memory leak raises a Warning, then a Critical,
then fires again every afternoon; a traffic surge raises CPU + NetworkIn + NetworkOut alerts;
a flapping rule raises the same alert six times.  Operators want ONE incident with ONE
diagnosis, not a page per alert.

Grouping rule (per resource, on event time -- never wall-clock time):
  * an alert joins the resource's most recent incident if that incident still has an unresolved
    alert, OR the gap since its last activity is
        <= INCIDENT_ANY_METRIC_GAP_HOURS      (any metric), or
        <= INCIDENT_SAME_METRIC_GAP_HOURS     (the same metric -> the same problem coming back)
  * otherwise it opens a new incident.
An incident is `open` while any of its alerts is unresolved and `resolved` once all are.

Schema (incidents collection):
  _id, project_id, resource_id, resource_type, resource_name, provider, status,
  opened_at, last_activity_at, closed_at, alerts[], anchor{metric: {...pre-incident stats}},
  root_cause_id, priority, revision, rec_id, created_batch, updated_batch
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import pymongo

from ..config import (INCIDENTS_COLLECTION, INCIDENT_ANY_METRIC_GAP_HOURS, INCIDENT_SAME_METRIC_GAP_HOURS)
from ..timeutil import as_utc

_FAR_PAST = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _alert_record(a) -> dict:
    """SourceAlert (or dict from alert_events) -> the compact record stored on the incident."""
    g = (lambda k: a.get(k)) if isinstance(a, dict) else (lambda k: getattr(a, k, None))
    return {
        "alert_id": g("alert_id"), "rule_id": g("rule_id"), "rule_name": g("rule_name"),
        "metric": g("metric"), "severity": g("severity"), "op": g("op"),
        "threshold": g("threshold"), "observed": g("observed"), "expected": g("expected"),
        "condition_type": g("condition_type"), "evaluation_periods": g("evaluation_periods") or 1,
        "fired_at": as_utc(g("fired_at")), "resolved_at": as_utc(g("resolved_at")),
    }


class IncidentManager:
    def __init__(self, db: pymongo.database.Database):
        self.col = db[INCIDENTS_COLLECTION]
        self.col.create_index([("project_id", 1), ("status", 1)])
        self.col.create_index([("resource_id", 1), ("opened_at", 1)])
        self.col.create_index("alerts.alert_id")

    # ── ingestion of alerts ───────────────────────────────────────────────────

    def sync(self, resource: dict, alerts: list, anchor_fn=None) -> list[dict]:
        """
        Attach `alerts` (SourceAlert list for ONE resource) to incidents.
        Returns [{incident, is_new, new_alert_ids, changed}] for every incident touched.
        `anchor_fn(first_alert_time) -> dict` computes the pre-incident anchor for new incidents.
        """
        touched: dict[str, dict] = {}
        rid = resource["_id"]
        for a in sorted(alerts, key=lambda x: as_utc(x.fired_at) or _FAR_PAST):
            rec = _alert_record(a)
            existing = self.col.find_one({"resource_id": rid, "alerts.alert_id": rec["alert_id"]})
            if existing:
                changed = _update_alert_in_place(existing, rec)
                if changed:
                    _refresh(existing)
                    self.col.replace_one({"_id": existing["_id"]}, existing)
                t = touched.setdefault(existing["_id"], dict(incident=existing, is_new=False,
                                                              new_alert_ids=[], changed=False))
                t["incident"] = existing
                t["changed"] = t["changed"] or changed
                continue

            inc = self._find_joinable(rid, rec)
            if inc is None:
                inc = {
                    "_id": str(uuid.uuid4()),
                    "project_id": resource.get("project_id"),
                    "resource_id": rid,
                    "resource_type": resource.get("resource_type"),
                    "resource_name": resource.get("resource_name"),
                    "provider": resource.get("service_name"),
                    "status": "open",
                    "opened_at": rec["fired_at"],
                    "alerts": [],
                    "anchor": (anchor_fn(rec["fired_at"]) if anchor_fn else {}),
                    "root_cause_id": None, "priority": None, "revision": 0, "rec_id": None,
                }
                is_new = True
            else:
                is_new = False
            inc["alerts"].append(rec)
            _refresh(inc)
            self.col.replace_one({"_id": inc["_id"]}, inc, upsert=True)
            t = touched.setdefault(inc["_id"], dict(incident=inc, is_new=is_new,
                                                    new_alert_ids=[], changed=True))
            t["incident"] = inc
            t["is_new"] = t["is_new"] or is_new
            t["new_alert_ids"].append(rec["alert_id"])
            t["changed"] = True
        return list(touched.values())

    def _find_joinable(self, resource_id: str, rec: dict) -> Optional[dict]:
        # incidents are few per resource; scan the latest few for the best candidate
        cands = list(self.col.find({"resource_id": resource_id}).sort("last_activity_at", -1).limit(3))
        f = rec["fired_at"]
        for inc in cands:
            if any(x.get("resolved_at") is None for x in inc["alerts"]):
                if f is None or as_utc(inc["opened_at"]) <= f:
                    return inc
            last_act = as_utc(inc.get("last_activity_at")) or as_utc(inc["opened_at"])
            gap_h = (f - last_act).total_seconds() / 3600.0 if f else 0.0
            same_metric = any(x["metric"] == rec["metric"] for x in inc["alerts"])
            if gap_h <= INCIDENT_ANY_METRIC_GAP_HOURS or (same_metric and gap_h <= INCIDENT_SAME_METRIC_GAP_HOURS):
                return inc
        return None

    # ── queries / updates ────────────────────────────────────────────────────

    def get(self, incident_id: str) -> Optional[dict]:
        return self.col.find_one({"_id": incident_id})

    def open_for_project(self, project_id: str) -> list[dict]:
        return list(self.col.find({"project_id": project_id, "status": "open"}))

    def for_project(self, project_id: str) -> list[dict]:
        return list(self.col.find({"project_id": project_id}))

    def recent_for_resource(self, resource_id: str, limit: int = 20) -> list[dict]:
        return list(self.col.find({"resource_id": resource_id}).sort("opened_at", -1).limit(limit))

    def set_fields(self, incident_id: str, **fields) -> None:
        self.col.update_one({"_id": incident_id}, {"$set": fields})


# ── helpers ────────────────────────────────────────────────────────────────────

def _update_alert_in_place(inc: dict, rec: dict) -> bool:
    for x in inc["alerts"]:
        if x["alert_id"] == rec["alert_id"]:
            if rec["resolved_at"] is not None and as_utc(x.get("resolved_at")) != rec["resolved_at"]:
                x["resolved_at"] = rec["resolved_at"]
                return True
            # severity/observed may worsen while the alert is active
            if rec["observed"] is not None and x.get("observed") != rec["observed"] and x.get("resolved_at") is None:
                x["observed"] = rec["observed"]
    return False


def _refresh(inc: dict) -> None:
    """Recompute status / activity timestamps from the alert list."""
    alerts = inc["alerts"]
    unresolved = [a for a in alerts if a.get("resolved_at") is None]
    times = [as_utc(a["fired_at"]) for a in alerts if a.get("fired_at")]
    times += [as_utc(a["resolved_at"]) for a in alerts if a.get("resolved_at")]
    inc["last_activity_at"] = max(times) if times else inc.get("opened_at")
    if inc.get("opened_at") is None or (times and min(times) < as_utc(inc["opened_at"])):
        inc["opened_at"] = min(times) if times else inc.get("opened_at")
    if unresolved:
        inc["status"] = "open"
        inc["closed_at"] = None
    else:
        inc["status"] = "resolved"
        inc["closed_at"] = max(as_utc(a["resolved_at"]) for a in alerts)
