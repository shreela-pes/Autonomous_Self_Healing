"""
AlertCorrelator -- correlation of ALERTS (what fired, where, in what order) for intelligent RCA.

Three levels:

 1. Intra-resource   which metrics alerted together, which stayed quiet, which deviate without
                     alerting.  A CPU alert with quiet memory and a 4x network-in is a different
                     story from a CPU alert with quiet network.
 2. Cross-resource   topology is inferred from resource tags (`app` groups resources, `tier`
                     orders them web -> app -> worker/db).  Incidents of the same app that start
                     within CROSS_RESOURCE_WINDOW_HOURS of each other are linked; an upstream
                     traffic-type incident that precedes a downstream one is a propagation
                     candidate, same-tier incidents indicate a shared (tier-wide) cause.
 3. Domain rules     the rule table in analysis/correlation.py (EBS <-> EC2 latency, storage
                     account throttling <-> VM, ...) evaluated over the resources that currently
                     have an incident.

The output feeds analysis/rca.py (evidence + upstream attribution) and is attached verbatim to
the recommendation as `correlation`, together with a merged timeline of the correlated alerts.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from ..config import CROSS_RESOURCE_WINDOW_HOURS
from ..timeutil import as_utc
from .correlation import CorrelationEngine

TIER_ORDER = {"web": 0, "lb": 0, "gateway": 0, "app": 1, "api": 1, "worker": 2, "db": 2, "cache": 2}
TRAFFIC_ROOT_CAUSES = {"CPU_TRAFFIC_SURGE", "NETWORK_INGRESS_ANOMALY"}
_RANK = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}


def tier_of(profile: dict) -> Optional[str]:
    return ((profile or {}).get("tags") or {}).get("tier")


def app_of(profile: dict) -> Optional[str]:
    return ((profile or {}).get("tags") or {}).get("app")


class AlertCorrelator:
    def __init__(self):
        self._rules = CorrelationEngine()

    # ── level 1 ─────────────────────────────────────────────────────────────
    @staticmethod
    def intra_resource(incident: dict, results: dict) -> dict:
        alerting = sorted({a["metric"] for a in incident.get("alerts", [])})
        quiet, deviating = [], []
        for m, r in (results or {}).items():
            if m in alerting or r.get("status") in (None, "NO_DATA"):
                continue
            (deviating if _RANK.get(r.get("status"), 0) >= 1 else quiet).append(m)
        return {"alerting_metrics": alerting, "quiet_metrics": sorted(quiet),
                "deviating_without_alert": sorted(deviating)}

    # ── level 2 ─────────────────────────────────────────────────────────────
    def cross_resource(self, incident: dict, profile: dict, project_incidents: list[dict],
                       profiles_by_id: dict, local_rc: dict) -> dict:
        """
        `local_rc`: {incident_id: root_cause_id} local diagnoses computed so far for the project.
        Returns peers / upstream / downstream descriptions.
        """
        my_tier, my_app = tier_of(profile), app_of(profile)
        my_rank = TIER_ORDER.get(my_tier)
        opened = as_utc(incident.get("opened_at"))
        win = timedelta(hours=CROSS_RESOURCE_WINDOW_HOURS)

        same_tier_total = same_tier_alerting = 0
        upstream, downstream, peers = [], [], []
        for rid, p in profiles_by_id.items():
            if rid == incident["resource_id"] or app_of(p) != my_app or my_app is None:
                continue
            t = tier_of(p)
            rank = TIER_ORDER.get(t)
            if t == my_tier:
                same_tier_total += 1
            for other in project_incidents:
                if other["resource_id"] != rid or other["_id"] == incident["_id"]:
                    continue
                o_open = as_utc(other.get("opened_at"))
                if o_open is None or abs((o_open - opened).total_seconds()) > win.total_seconds():
                    continue
                info = {
                    "incident_id": other["_id"], "resource_id": rid,
                    "resource_name": p.get("resource_name") or rid, "tier": t,
                    "opened_at": o_open, "root_cause_id": local_rc.get(other["_id"]),
                    "metrics": sorted({a["metric"] for a in other.get("alerts", [])}),
                }
                if t == my_tier:
                    same_tier_alerting += 1
                    peers.append(info)
                elif rank is not None and my_rank is not None and rank < my_rank:
                    upstream.append(info)
                elif rank is not None and my_rank is not None and rank > my_rank:
                    downstream.append(info)
                break
        return {
            "same_tier_total": same_tier_total, "same_tier_alerting": same_tier_alerting,
            "peers": peers, "upstream": upstream, "downstream": downstream,
            "upstream_traffic": [u for u in upstream if u.get("root_cause_id") in TRAFFIC_ROOT_CAUSES],
        }

    # ── level 3 ─────────────────────────────────────────────────────────────
    def domain_rules(self, project_id: str, project_incidents: list[dict], profiles_by_id: dict) -> list[dict]:
        """Run the storage/compute rule table over resources that currently have an incident."""
        pseudo = []
        for inc in project_incidents:
            if inc.get("status") != "open":
                continue
            p = profiles_by_id.get(inc["resource_id"]) or {}
            pseudo.append({
                "_id": inc["resource_id"], "resource_type": inc.get("resource_type"),
                "category": p.get("category"), "resource_name": inc.get("resource_name"),
                "current_alerts": [{"metric": a["metric"], "status": "CRIT" if a["severity"] == "CRIT" else "WARN"}
                                   for a in inc.get("alerts", []) if a.get("resolved_at") is None],
            })
        if len(pseudo) < 2:
            return []
        try:
            return [cs.to_dict() for cs in self._rules.find_correlated_sets(pseudo)]
        except Exception:
            return []

    # ── timeline ─────────────────────────────────────────────────────────────
    @staticmethod
    def timeline(incidents: list[dict], names: dict) -> list[dict]:
        """Merged, time-ordered list of the correlated alerts (fired / resolved events)."""
        ev = []
        for inc in incidents:
            for a in inc.get("alerts", []):
                if a.get("fired_at"):
                    ev.append({"time": as_utc(a["fired_at"]), "resource": names.get(inc["resource_id"], inc["resource_id"]),
                               "event": "fired", "metric": a["metric"], "severity": a["severity"]})
                if a.get("resolved_at"):
                    ev.append({"time": as_utc(a["resolved_at"]), "resource": names.get(inc["resource_id"], inc["resource_id"]),
                               "event": "resolved", "metric": a["metric"], "severity": a["severity"]})
        ev.sort(key=lambda e: e["time"])
        return ev[:40]

    # ── signature ────────────────────────────────────────────────────────────
    @staticmethod
    def signature(incident: dict) -> str:
        parts = sorted({f"{a['metric']}:{a['op']}:{a['severity']}" for a in incident.get("alerts", [])})
        return f"{incident.get('resource_type')}|" + ",".join(parts)
