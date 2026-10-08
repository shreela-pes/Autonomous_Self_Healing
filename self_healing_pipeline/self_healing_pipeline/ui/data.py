"""Data access for the UI - no Streamlit imports here, so it can be tested and reused."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from typing import Optional

import pandas as pd
import pymongo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.config import (MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION, RECOMMENDATIONS_COLLECTION,  # noqa: E402
                             RESOURCE_PROFILES_COLLECTION, DERIVED_COLLECTIONS)
from pipeline.ingestion.normalizer import parse_document  # noqa: E402
from pipeline.timeutil import as_utc  # noqa: E402

PRIORITY_ICON = {"P1": "🔴 P1", "P2": "🟠 P2", "P3": "🟢 P3"}


def get_client() -> pymongo.MongoClient:
    return pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000, tz_aware=True)


def get_db(client=None):
    return (client or get_client())[MONGO_DB_NAME]


def ping(db) -> Optional[str]:
    """None if reachable, else the error text."""
    try:
        db.client.admin.command("ping")
        return None
    except Exception as exc:                                    # pragma: no cover - message only
        return str(exc)[:300]


# ── recommendations ───────────────────────────────────────────────────────────

def load_recommendations(db) -> list[dict]:
    return list(db[RECOMMENDATIONS_COLLECTION].find({}))


def recs_frame(recs: list[dict]) -> pd.DataFrame:
    rows = []
    for r in recs:
        rows.append({
            "id": r["_id"],
            "priority": r["priority"], "status": r["status"], "cloud": r["provider"],
            "resource": r["resource_name"], "tier": r.get("tier"), "use case": r["use_case_title"],
            "root cause": r["root_cause"]["id"], "confidence": r["root_cause"]["confidence"],
            "alerts": len(r["alerts"]), "first alert": as_utc(r["first_alert_at"]),
            "resolved": as_utc(r.get("resolved_at")), "rev": r["revision"],
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["first alert"] = pd.to_datetime(df["first alert"], utc=True)
        df = df.sort_values("first alert", ascending=False).reset_index(drop=True)
    return df


def hypotheses_frame(rec: dict) -> pd.DataFrame:
    return pd.DataFrame([{"cause": h["id"], "score": h["score"]} for h in rec["root_cause"]["hypotheses"]])


def alerts_frame(rec: dict) -> pd.DataFrame:
    rows = [{"severity": a["severity"], "metric": a["metric"], "rule": a["rule_name"], "condition": a["op"],
             "threshold": a["threshold"], "observed": a["observed"],
             "fired": as_utc(a["fired_at"]), "resolved": as_utc(a.get("resolved_at"))} for a in rec["alerts"]]
    return pd.DataFrame(rows)


def timeline_frame(rec: dict) -> pd.DataFrame:
    return pd.DataFrame(rec["correlation"]["timeline"])


def trends_frame(rec: dict) -> pd.DataFrame:
    return pd.DataFrame(rec["statistics"]["trends"])


# ── source-log metric series ──────────────────────────────────────────────────

def resources(db) -> pd.DataFrame:
    rows = [{"resource_id": p["_id"], "name": p.get("resource_name"), "type": p.get("resource_type"),
             "tier": (p.get("tags") or {}).get("tier"), "app": (p.get("tags") or {}).get("app"),
             "cloud": p.get("service_name")} for p in db[RESOURCE_PROFILES_COLLECTION].find(
                 {}, {"resource_name": 1, "resource_type": 1, "tags": 1, "service_name": 1})]
    return pd.DataFrame(rows).sort_values(["cloud", "name"]).reset_index(drop=True) if rows else pd.DataFrame()


def native_metrics(db, resource_id: str) -> list[str]:
    return sorted(db[MONGO_COLLECTION].distinct("metric", {"resourceId": resource_id}))


def metric_series(db, resource_id: str, native_metric: str, start=None, end=None):
    """
    Hourly canonical values (e.g. Azure memory shown as % used) and the source alerts, parsed with the
    SAME normalizer the pipeline uses.  Returns (series_df, alerts_df, canonical_metric).
    """
    q = {"resourceId": resource_id, "metric": native_metric}
    if start or end:
        q["from_date"] = {k: v for k, v in (("$gte", start), ("$lte", end)) if v}
    pts, alerts, canon, seen = [], [], None, set()
    for raw in db[MONGO_COLLECTION].find(q).sort("from_date", 1):
        p = parse_document(raw)
        if p is None:
            continue
        canon = p.canonical_metric
        for pt in p.points:
            if pt.value is not None and pt.value == pt.value:
                pts.append({"time": pt.timestamp, "value": pt.value})
        for a in p.alerts:
            if a.alert_id in seen:
                continue
            seen.add(a.alert_id)
            alerts.append({"alert_id": a.alert_id, "severity": a.severity, "fired": a.fired_at,
                           "resolved": a.resolved_at, "rule": a.rule_name, "threshold": a.threshold})
    return pd.DataFrame(pts), pd.DataFrame(alerts), canon


def incident_window(rec: dict, pad_before_days=3, pad_after_days=2):
    a = as_utc(rec["first_alert_at"])
    b = as_utc(rec.get("resolved_at")) or as_utc(rec["last_alert_at"])
    return a - timedelta(days=pad_before_days), b + timedelta(days=pad_after_days)


# ── pipeline control (used by the UI buttons) ─────────────────────────────────

def counts(db) -> dict:
    out = {"source logs": db[MONGO_COLLECTION].estimated_document_count()}
    for name in DERIVED_COLLECTIONS:
        out[name] = db[name].estimated_document_count()
    return out


def pipeline_command(reset: bool, use_llm: bool) -> list[str]:
    cmd = [sys.executable, os.path.join(ROOT, "main.py")]
    if reset:
        cmd.append("--reset")
    if not use_llm:
        cmd.append("--no-llm")
    return cmd


def load_command() -> list[str]:
    return [sys.executable, os.path.join(ROOT, "tools", "load_dataset.py"), "--drop"]


def run_command(cmd: list[str], timeout: int = 3600) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + "\n" + p.stderr).strip()
