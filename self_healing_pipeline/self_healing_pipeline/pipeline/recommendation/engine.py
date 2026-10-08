"""
RecommendationEngine -- orchestrates the REAL-TIME, alert-gated self-healing pipeline.

    log documents (one day of one metric of one resource, with `alerts[]` when the cloud fired any)
        |
        v  1 ingest      state update: time-series, seasonal baselines (healthy days only), alert events
        v  2 enrich      statistics (seasonality-aware, trend/shape) + light ML (Isolation Forest) per resource
        v  3 gate        ONLY resources whose logs carry a fired source alert continue
        v  4 incident    raw alerts grouped into incidents on event time (one incident = one diagnosis)
        v  5 correlate   intra-resource (which metrics alert / stay quiet), cross-resource (topology from tags),
        |                domain rules
        v  6 RCA         evidence-scored hypotheses -> root cause, confidence, why-not-the-others
        v  7 playbook    root cause -> ordered, HUMAN-EXECUTED recommendations (nothing is auto-remediated)
        v  8 explain     LLM (optional) narrates the finished decision; template fallback; never alters it
        v  9 persist     one recommendation per incident, versioned when the diagnosis/priority/alert set changes

Processing is done in BATCHES (all documents of one day): every metric of a resource for that day is
ingested before any diagnosis is made, so a CPU alert is diagnosed with the same day's network and
memory data - independent of the order in which documents arrived.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import pymongo

from ..analysis.alert_correlation import AlertCorrelator, tier_of
from ..analysis.ml_engine import HierarchicalMLEngine
from ..analysis.pattern_store import PatternStore
from ..analysis.project_correlation import ProjectCorrelationEngine
from ..analysis.rca import RCAContext, RootCauseAnalyzer, ROOT_CAUSE_LABELS
from ..analysis.statistical import StatisticalEngine
from ..config import (RECOMMENDATIONS_COLLECTION, RESOURCE_TYPE_TO_PROVIDER, USE_LLM, REQUIRE_SOURCE_ALERT)
from ..ingestion.normalizer import ParsedDoc
from ..llm.explainer import Explainer
from ..metrics.feature_normalizer import normalize
from ..state.incident_state import IncidentManager
from ..state.project_state import ProjectStateManager
from ..state.resource_state import ResourceStateManager
from ..timeutil import as_utc
from .playbooks import build_recommendation_body, decide_priority, make_pb

logger = logging.getLogger(__name__)

_RANK = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}
_USE_CASE_TITLES = {
    "UC1": "CPU saturation", "UC2": "Memory pressure", "UC3": "Burst-credit exhaustion",
    "UC4": "Disk capacity", "UC5": "Network anomaly", "X": "Cross-cutting",
}
_KEY_METRICS = ("cpu_pct", "memory_used_pct", "cpu_credit_balance", "cpu_scheduler_wait_sec",
                "disk_used_pct", "disk_write_bytes", "network_in_bytes", "network_out_bytes")


class _Cached:
    """Per-batch analysis of one resource."""
    __slots__ = ("profile", "results", "by_metric", "ml", "norm", "obs_date")


class RecommendationEngine:
    def __init__(self, db: pymongo.database.Database, ollama_client=None, use_llm: bool = USE_LLM):
        self.db = db
        self.rec_col = db[RECOMMENDATIONS_COLLECTION]
        self.rec_col.create_index([("project_id", 1), ("status", 1)])
        self.rec_col.create_index("resource_id")
        self.rec_col.create_index("root_cause.id")

        self.resource_mgr = ResourceStateManager(db)
        self.project_mgr = ProjectStateManager(db)
        self.incidents = IncidentManager(db)
        self.pattern_store = PatternStore(db)
        self.stat_engine = StatisticalEngine()
        self.ml_engine = HierarchicalMLEngine()
        self.project_corr = ProjectCorrelationEngine()
        self.correlator = AlertCorrelator()
        self.rca = RootCauseAnalyzer()
        self.explainer = Explainer(ollama_client, use_llm=use_llm)
        self.stats = defaultdict(int)

    # ── public entry points ───────────────────────────────────────────────────

    def process_document(self, parsed: ParsedDoc) -> Optional[dict]:
        out = self.process_batch([parsed])
        return out[0] if out else None

    def process_batch(self, docs: list[ParsedDoc]) -> list[dict]:
        docs = [d for d in docs if d is not None]
        if not docs:
            return []
        self.stats["documents"] += len(docs)
        self.stats["batches"] += 1

        # 1 ── ingest -------------------------------------------------------------------
        touched: dict[str, dict] = {}
        for d in docs:
            try:
                self.resource_mgr.update(d)
            except Exception as exc:
                logger.error("State update failed for %s: %s", d.resource_id, exc, exc_info=True)
                continue
            t = touched.setdefault(d.resource_id, dict(doc=d, alerts=[], obs=d.from_date))
            t["alerts"].extend(d.alerts)
            if d.from_date and (t["obs"] is None or d.from_date > t["obs"]):
                t["obs"] = d.from_date

        # 2 ── enrich (stats + light ML), once per resource per batch --------------------
        cache: dict[str, _Cached] = {}
        for rid, t in touched.items():
            try:
                cache[rid] = self._analyse_resource(rid, t["obs"], update_ml=True)
            except Exception as exc:
                logger.error("Analysis failed for %s: %s", rid, exc, exc_info=True)

        # 3/4 ── gate + incidents ---------------------------------------------------------
        by_project: dict[str, dict] = defaultdict(lambda: dict(resources=[], sync=[]))
        for rid, t in touched.items():
            c = cache.get(rid)
            if c is None:
                continue
            pid = t["doc"].project_id
            by_project[pid]["resources"].append(rid)
            alerts = t["alerts"]
            if not alerts:
                # no source alert -> nothing to recommend, even if the statistics see an anomaly
                if any(_RANK.get(r["status"], 0) >= 1 for r in c.by_metric.values()):
                    self.stats["anomaly_without_alert"] += 1
                if REQUIRE_SOURCE_ALERT:
                    continue
            resource = {"_id": rid, "project_id": pid, "resource_type": t["doc"].resource_type,
                        "resource_name": t["doc"].resource_name, "service_name": t["doc"].service_name}
            synced = self.incidents.sync(resource, alerts,
                                         anchor_fn=lambda first, p=c.profile: _anchor(p, first))
            by_project[pid]["sync"].extend(synced)

        written = []
        for pid, info in by_project.items():
            if not info["sync"] and not self.incidents.open_for_project(pid):
                continue
            written.extend(self._evaluate_project(pid, info["sync"], cache))
        return written

    # ── stage 2 ───────────────────────────────────────────────────────────────

    def _analyse_resource(self, rid: str, obs_date, update_ml: bool) -> _Cached:
        profile = self.resource_mgr.get(rid)
        results = self.stat_engine.derive_cpu_from_idle(self.stat_engine.analyze_resource(profile))
        by_metric = {r.metric: r.to_dict() for r in results if r.status != "NO_DATA"}
        active = [r.to_dict() for r in results if _RANK.get(r.status, 0) >= 1]
        self.resource_mgr.update_alerts(rid, active)
        try:
            self.project_mgr.update_resource_status(
                profile.get("project_id"), rid, profile.get("resource_type"), profile.get("category"),
                self.stat_engine.overall_status(results), active)
        except Exception as exc:
            logger.debug("Project snapshot update failed for %s: %s", rid, exc)

        cfg = dict(profile.get("config") or {})
        cfg["_tier"] = (profile.get("tags") or {}).get("tier")
        ml_res = None
        alert_dicts = list(by_metric.values())
        try:
            ml_res = self.ml_engine.predict(rid, profile.get("resource_type"), cfg, alert_dicts)
            if update_ml:
                key = obs_date.strftime("%Y-%m-%d") if obs_date else ""
                self.ml_engine.update(rid, profile.get("resource_type"), cfg, alert_dicts, obs_key=key)
        except Exception as exc:
            logger.debug("ML step skipped for %s: %s", rid, exc)

        c = _Cached()
        c.profile, c.results, c.by_metric, c.ml = profile, results, by_metric, ml_res
        c.norm = normalize(profile.get("resource_type"), profile.get("config") or {})
        c.obs_date = obs_date or _latest_obs(profile)
        return c

    # ── stages 4-9 for one project ─────────────────────────────────────────────

    def _evaluate_project(self, pid: str, synced: list[dict], cache: dict) -> list[dict]:
        sync_by_id = {s["incident"]["_id"]: s for s in synced}
        incidents = {i["_id"]: i for i in self.incidents.open_for_project(pid)}
        for iid, s in sync_by_id.items():
            incidents[iid] = s["incident"]                       # includes just-resolved incidents
        if not incidents:
            return []
        project_incidents = list(incidents.values())
        index = self.resource_mgr.get_project_index(pid)
        names = {rid: v.get("resource_name") or rid for rid, v in index.items()}

        # local RCA for every incident of the project ------------------------------------
        ctxs: dict[str, RCAContext] = {}
        local: dict[str, object] = {}
        for iid, inc in incidents.items():
            rid = inc["resource_id"]
            c = cache.get(rid)
            if c is None:
                try:
                    c = cache[rid] = self._analyse_resource(rid, None, update_ml=False)
                except Exception as exc:
                    logger.error("Analysis failed for %s: %s", rid, exc)
                    continue
            peers = self.correlator.cross_resource(inc, c.profile, project_incidents, index, {})
            ctx = RCAContext(incident=inc, profile=c.profile, results=c.by_metric, norm=c.norm,
                             batch_date=c.obs_date, ml=c.ml, peers=peers,
                             pattern=self.pattern_store.get(self.correlator.signature(inc)))
            ctxs[iid] = ctx
            prev_rec = self.rec_col.find_one({"_id": iid}, {"root_cause.id": 1, "status": 1})
            if prev_rec and inc["status"] == "resolved":
                # Post-recovery data is a poor basis for diagnosis: freeze the diagnosis made while the
                # problem was live and only close the incident out.
                self._close_out(inc, prev_rec["_id"], cache[rid], sync_by_id.get(iid, {}))
                continue
            local[iid] = self.rca.analyze_local(ctx, prefer=inc.get("root_cause_id"))

        # cross-resource pass (needs the local diagnoses of the other incidents) -----------
        local_rc = {iid: r.root_cause_id for iid, r in local.items()}
        domain_rules = self.correlator.domain_rules(pid, project_incidents, index)
        written = []
        for iid, inc in incidents.items():
            ctx, res = ctxs.get(iid), local.get(iid)
            if ctx is None or res is None:
                continue
            c = cache[inc["resource_id"]]
            peers = self.correlator.cross_resource(inc, c.profile, project_incidents, index, local_rc)
            ctx.peers = peers
            is_new = bool(sync_by_id.get(iid, {}).get("is_new"))
            changed_alerts = bool(sync_by_id.get(iid, {}).get("changed"))
            if is_new or changed_alerts or peers["upstream_traffic"]:
                ctx.ml_corrs = self._learned_correlations(pid, inc["resource_id"], c.obs_date)
            upstream = [{"resource_id": u["resource_id"], "resource_name": u["resource_name"], "tier": u["tier"],
                         "root_cause_id": u["root_cause_id"], "opened_at": u["opened_at"]}
                        for u in peers["upstream_traffic"]]
            res = self.rca.apply_upstream(res, ctx, upstream)

            rec = self._maybe_write(inc, ctx, res, peers, domain_rules, project_incidents, names, is_new, changed_alerts)
            if rec:
                written.append(rec)
        return written

    def _close_out(self, inc: dict, rec_id: str, c: _Cached, sync_info: dict) -> None:
        """Incident resolved: keep the diagnosis, update state / priority / alert states, learn the duration."""
        prev = self.rec_col.find_one({"_id": rec_id})
        if not prev or (prev.get("status") == "resolved" and not sync_info.get("changed")):
            return
        rc_id = prev["root_cause"]["id"]
        priority, why = decide_priority(rc_id, {a["severity"] for a in inc["alerts"]}, True)
        now = datetime.now(timezone.utc)
        revs = list(prev.get("revisions") or [])
        revision = (prev.get("revision") or 0) + 1
        revs.append({"revision": revision, "at": now, "root_cause_id": rc_id, "priority": priority,
                     "n_alerts": len(inc["alerts"]), "status": "resolved", "reason": "incident resolved"})
        self.rec_col.update_one({"_id": rec_id}, {"$set": {
            "status": "resolved", "priority": priority, "priority_reason": why,
            "alerts": [_alert_out(a) for a in sorted(inc["alerts"], key=lambda a: as_utc(a["fired_at"]))],
            "resolved_at": as_utc(inc.get("closed_at")), "updated_at": now, "revision": revision,
            "revisions": revs[-20:],
        }})
        self.stats["recommendations_written"] += 1
        self.stats["incidents_closed"] += 1
        if prev.get("status") != "resolved" and inc.get("closed_at"):
            hrs = (as_utc(inc["closed_at"]) - as_utc(inc["opened_at"])).total_seconds() / 3600.0
            self.pattern_store.record_close(self.correlator.signature(inc), hrs)
        self.incidents.set_fields(inc["_id"], revision=revision, priority=priority)

    def _learned_correlations(self, pid, rid, as_of) -> list[dict]:
        try:
            corrs = self.project_corr.get_correlations_for_resource(
                pid, rid, lambda: self.resource_mgr.get_project_resources(pid), as_of=as_utc(as_of))
            return [c.to_dict() if hasattr(c, "to_dict") else c for c in corrs]
        except Exception as exc:
            logger.debug("learned correlation skipped: %s", exc)
            return []

    # ── stage 7-9 ─────────────────────────────────────────────────────────────

    def _maybe_write(self, inc, ctx, res, peers, domain_rules, project_incidents, names, is_new, changed_alerts):
        all_resolved = inc["status"] == "resolved"
        severities = {a["severity"] for a in inc["alerts"]}
        priority, why = decide_priority(res.root_cause_id, severities, all_resolved)
        prev = self.rec_col.find_one({"_id": inc["_id"]})
        rc_changed = (prev or {}).get("root_cause", {}).get("id") != res.root_cause_id
        pri_changed = (prev or {}).get("priority") != priority
        state_changed = (prev or {}).get("status") != inc["status"]
        def _shape(alerts):      # a new alert only matters if it adds a metric / severity level
            return {(a["metric"], a["severity"]) for a in alerts}
        n_alerts_changed = _shape((prev or {}).get("alerts") or []) != _shape(inc["alerts"])
        if prev and not (rc_changed or pri_changed or state_changed or n_alerts_changed):
            return None                                             # nothing new to tell the operator

        provider = RESOURCE_TYPE_TO_PROVIDER.get(inc.get("resource_type"), inc.get("provider"))
        pb = make_pb(ctx.profile, provider, res.facts)
        body = build_recommendation_body(res.root_cause_id, pb)

        # correlation section ------------------------------------------------------------
        related = [i for i in project_incidents
                   if i["_id"] != inc["_id"] and i["resource_id"] in
                   {p["resource_id"] for p in peers["peers"] + peers["upstream"] + peers["downstream"]}]
        timeline = self.correlator.timeline([inc] + related, names)
        intra = self.correlator.intra_resource(inc, ctx.results)
        corr_summary = _correlation_sentence(inc, res, peers, intra)

        alerts_out = [_alert_out(a) for a in sorted(inc["alerts"], key=lambda a: as_utc(a["fired_at"]))]
        d = {
            "resource_name": inc.get("resource_name"), "provider": provider, "priority": priority,
            "root_cause_label": res.label, "confidence": res.confidence, "summary": body["summary"],
            "alerts": [{"metric": a["metric"], "severity": a["severity"], "fired_at": str(a["fired_at"])[:16]}
                       for a in alerts_out],
            "all_resolved": all_resolved, "evidence": res.evidence, "counter_evidence": res.counter_evidence,
            "alternatives": res.alternatives, "actions": body["actions"], "do_not": body["do_not"],
            "verify": body["verify"], "correlation_summary": corr_summary,
        }

        explanation = (prev or {}).get("explanation")
        if explanation is None or rc_changed or pri_changed:
            explanation = self.explainer.explain(d)
            self.stats["llm_explanations" if explanation["source"] == "llm" else "template_explanations"] += 1

        root_res_name = names.get(res.root_resource_id) if res.root_resource_id else None
        now = datetime.now(timezone.utc)
        revision = ((prev or {}).get("revision") or 0) + 1
        revisions = list((prev or {}).get("revisions") or [])
        revisions.append({"revision": revision, "at": now, "root_cause_id": res.root_cause_id, "priority": priority,
                          "n_alerts": len(inc["alerts"]), "status": inc["status"],
                          "reason": ("new incident" if not prev else
                                     "diagnosis changed" if rc_changed else "priority changed" if pri_changed else
                                     "incident resolved" if state_changed else "new alert joined the incident")})
        rec = {
            "_id": inc["_id"], "incident_id": inc["_id"], "project_id": inc["project_id"],
            "resource_id": inc["resource_id"], "resource_name": inc.get("resource_name"),
            "resource_type": inc.get("resource_type"), "provider": provider,
            "tier": tier_of(ctx.profile), "app": (ctx.profile.get("tags") or {}).get("app"),
            "use_case": res.use_case, "use_case_title": _USE_CASE_TITLES.get(res.use_case, res.use_case),
            "status": inc["status"], "priority": priority, "priority_reason": why,
            "title": body["title"], "summary": body["summary"],
            "root_cause": {
                "id": res.root_cause_id, "label": res.label, "confidence": res.confidence,
                "confidence_parts": res.confidence_parts, "evidence": res.evidence,
                "counter_evidence": res.counter_evidence, "alternatives": res.alternatives,
                "hypotheses": res.hypotheses, "root_resource_id": res.root_resource_id,
                "root_resource_name": root_res_name,
            },
            "alerts": alerts_out,
            "correlation": {
                "summary": corr_summary, "intra_resource": intra,
                "same_tier_peers": [_peer_out(p) for p in peers["peers"]],
                "upstream": [_peer_out(p) for p in peers["upstream"]],
                "downstream": [_peer_out(p) for p in peers["downstream"]],
                "domain_rules": domain_rules,
                "learned_correlations": [c for c in (ctx.ml_corrs or [])][:5],
                "timeline": [{**e, "time": e["time"]} for e in timeline],
            },
            "statistics": _statistics_block(ctx, res),
            "ml": ({"anomaly_score": ctx.ml.anomaly_score, "is_anomaly": ctx.ml.is_anomaly, "model_level": ctx.ml.level_used,
                    "training_samples": ctx.ml.n_training_samples} if ctx.ml else None),
            "actions": body["actions"],
            "immediate_actions": [a for a in body["actions"] if a["phase"] == "now"],
            "corrective_actions": [a for a in body["actions"] if a["phase"] == "fix"],
            "preventive_actions": [a for a in body["actions"] if a["phase"] == "prevent"],
            "do_not_do": body["do_not"], "verification": body["verify"], "risk_if_ignored": body["risk"],
            "explanation": explanation,
            "automated_remediation": False, "requires_human_approval": True,
            "analysis_mode": "reactive (alert-gated); statistics/ML/correlation enrich, never trigger",
            "observation_date": as_utc(ctx.batch_date),
            "first_alert_at": min(as_utc(a["fired_at"]) for a in inc["alerts"]),
            "last_alert_at": max(as_utc(a["fired_at"]) for a in inc["alerts"]),
            "resolved_at": as_utc(inc.get("closed_at")),
            "created_at": (prev or {}).get("created_at") or now, "updated_at": now,
            "revision": revision, "revisions": revisions[-20:],
        }
        self.rec_col.replace_one({"_id": rec["_id"]}, rec, upsert=True)
        self.stats["recommendations_written"] += 1

        # learning + bookkeeping ---------------------------------------------------------
        sig = self.correlator.signature(inc)
        if is_new:
            self.stats["incidents_opened"] += 1
            self.pattern_store.record_open(sig, inc.get("resource_type"), as_utc(inc["opened_at"]))
        if rc_changed:
            self.pattern_store.record_diagnosis(sig, res.root_cause_id)
        if state_changed and inc["status"] == "resolved" and inc.get("closed_at"):
            hrs = (as_utc(inc["closed_at"]) - as_utc(inc["opened_at"])).total_seconds() / 3600.0
            self.pattern_store.record_close(sig, hrs)
        self.incidents.set_fields(inc["_id"], root_cause_id=res.root_cause_id, priority=priority,
                                  revision=revision, rec_id=rec["_id"])
        if (is_new or rc_changed) and (peers["peers"] or peers["upstream"] or peers["downstream"]):
            try:
                self.project_mgr.add_correlated_set(inc["project_id"], {
                    "rule_name": "alert_correlation:" + res.root_cause_id,
                    "root_cause_resource_id": res.root_resource_id or inc["resource_id"],
                    "root_cause_resource_type": inc.get("resource_type"), "root_cause_category": "Compute",
                    "dependent_resource_ids": [p["resource_id"] for p in peers["downstream"] + peers["peers"]],
                    "triggered_metrics": intra["alerting_metrics"], "root_cause_description": corr_summary,
                    "do_not_recommend": "; ".join(body["do_not"][:1]), "confidence": res.confidence,
                    "causal_order": [p["tier"] for p in peers["upstream"]] + [tier_of(ctx.profile) or "resource"],
                })
            except Exception as exc:
                logger.debug("correlated set not stored: %s", exc)
        return rec


# ── helpers ────────────────────────────────────────────────────────────────────

def _latest_obs(profile: dict):
    dates = [as_utc(m.get("observation_date")) for m in (profile.get("metrics") or {}).values()
             if m.get("observation_date")]
    return max(dates) if dates else datetime.now(timezone.utc)


def _anchor(profile: dict, first_alert_time) -> dict:
    """Pre-incident level of every metric: mean of the 7 daily points BEFORE the first alert day."""
    first = as_utc(first_alert_time)
    out = {}
    for m, md in (profile.get("metrics") or {}).items():
        rows = [h for h in (md.get("daily_history") or [])
                if h.get("avg") is not None and as_utc(h["date"]).date() < first.date()]
        rows = rows[-7:]
        if rows:
            out[m] = {"pre_avg": sum(h["avg"] for h in rows) / len(rows),
                      "pre_max": max(h["max"] for h in rows if h.get("max") is not None) if any(h.get("max") is not None for h in rows) else None,
                      "n": len(rows)}
    return out


def _alert_out(a: dict) -> dict:
    return {k: a.get(k) for k in ("alert_id", "rule_name", "metric", "severity", "op", "threshold", "observed",
                                  "expected", "condition_type", "fired_at", "resolved_at")}


def _peer_out(p: dict) -> dict:
    return {"resource_id": p["resource_id"], "resource_name": p["resource_name"], "tier": p["tier"],
            "opened_at": p["opened_at"], "local_root_cause": p.get("root_cause_id"), "metrics": p.get("metrics")}


def _correlation_sentence(inc, res, peers, intra) -> str:
    bits = []
    if intra["alerting_metrics"]:
        bits.append(f"alerts on {', '.join(intra['alerting_metrics'])}")
    if intra["quiet_metrics"]:
        bits.append(f"quiet metrics: {', '.join(intra['quiet_metrics'])}")
    s = "Same resource: " + "; ".join(bits) + "." if bits else ""
    if res.root_cause_id == "UPSTREAM_PROPAGATION":
        s += (f" Upstream {res.facts.get('upstream_resource_name')} alerted first "
              f"({res.facts.get('upstream_root_cause')}); this resource is downstream of it.")
    else:
        if peers["peers"]:
            s += f" {len(peers['peers'])} peer node(s) of the same tier alerted in the same window (shared cause likely)."
        if peers["downstream"]:
            s += (" Downstream resources alerting at the same time: "
                  + ", ".join(p["resource_name"] for p in peers["downstream"]) + ".")
    return s.strip()


def _statistics_block(ctx: RCAContext, res) -> dict:
    metrics = {}
    trends = []
    for m in _KEY_METRICS:
        r = ctx.results.get(m)
        if not r:
            continue
        f, h = r.get("features") or {}, r.get("history") or {}
        metrics[m] = {"status": r.get("status"), "daily_avg": r.get("daily_avg"), "daily_max": r.get("daily_max"),
                      "daily_min": r.get("daily_min"), "baseline_avg": f.get("baseline_avg"),
                      "ratio_to_baseline_max": f.get("ratio_max"), "robust_z": r.get("anomaly_score")}
        sh = (h.get("shape10") or {})
        trends.append({"metric": m, "days_of_history": h.get("n_history_days"), "slope_7d_per_day": h.get("slope_7d"),
                       "slope_30d_per_day": h.get("slope_30d"), "shape_last_10d": sh.get("shape"),
                       "same_weekday_median": h.get("seasonal_median"), "baseline_source": r.get("baseline_source")})
    return {"metrics": metrics, "trends": trends}
