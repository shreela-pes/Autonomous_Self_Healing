"""
RootCauseAnalyzer -- transparent, evidence-scored root-cause analysis for one incident.

The analyzer answers: "given the alerts that fired and EVERYTHING else we know about this
resource (metrics that did not alert, baselines, trends, config, peers), what is the most
likely cause?"  It is deterministic and every conclusion is traceable:

  * each candidate cause is a small list of weighted CHECKS (a check = one measurable fact,
    e.g. "network-in was 4.1x its same-hour baseline during the CPU-high hours");
  * a `required` check that fails rules the hypothesis out (score 0);
  * score = weighted share of applicable checks that passed; unavailable data is excluded
    from the score (and reduces confidence);
  * the winner, the ranked runners-up, and the failed checks ("why not X?") are all returned.

Confidence is NOT a language-model opinion; it is
    0.30 + 0.50*top_score + 0.12*margin_over_runner_up
         + 0.05  if the multivariate ML model also flags the day as unusual   (-0.04 if it does not)
         + 0.04  if the same alert pattern earlier produced the same diagnosis
         + 0.04  if learned cross-metric correlations support the diagnosis
         - 0.08  if a large part of the evidence was unavailable
clamped to [0.25, 0.95].

Use cases covered (see recommendation/playbooks.py for the matching actions):
  UC1 CPU saturation        CPU_TRAFFIC_SURGE | CPU_RUNAWAY_PROCESS | CPU_RECURRING_LOAD | UPSTREAM_PROPAGATION
  UC2 Memory pressure       MEMORY_LEAK | MEMORY_STEP_CHANGE
  UC3 Burst-credit          CREDIT_EXHAUSTION
  UC4 Disk capacity         DISK_LOG_GROWTH | DISK_SUDDEN_FILL
  UC5 Network anomaly       NETWORK_INGRESS_ANOMALY | NETWORK_EGRESS_ANOMALY | NETWORK_TRAFFIC_LOSS
  cross-cutting             TRANSIENT_SPIKE | ALERT_FLAPPING | UNDETERMINED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import numpy as np

from . import features as F
from ..config import (RECURRENCE_MIN_EPISODES, RECURRENCE_HOUR_TOLERANCE, FLAPPING_MIN_EPISODES,
                      FLAPPING_WINDOW_HOURS, TRANSIENT_MAX_HOURS, CROSS_RESOURCE_WINDOW_HOURS)
from ..timeutil import as_utc

CPU, MEM, DISK = "cpu_pct", "memory_used_pct", "disk_used_pct"
CREDIT, WAIT = "cpu_credit_balance", "cpu_scheduler_wait_sec"
NIN, NOUT, DWRITE = "network_in_bytes", "network_out_bytes", "disk_write_bytes"

ROOT_CAUSE_LABELS = {
    "CPU_TRAFFIC_SURGE":       ("UC1", "CPU saturated by a traffic surge (load-driven)"),
    "CPU_RUNAWAY_PROCESS":     ("UC1", "CPU saturated by a runaway process / job (traffic is normal)"),
    "CPU_RECURRING_LOAD":      ("UC1", "Recurring scheduled load saturates CPU (seasonal pattern)"),
    "UPSTREAM_PROPAGATION":    ("UC1", "Symptom propagated from an upstream tier - the cause is not on this resource"),
    "MEMORY_LEAK":             ("UC2", "Progressive memory growth (leak-like)"),
    "MEMORY_STEP_CHANGE":      ("UC2", "Step increase in steady-state memory (release / config change)"),
    "CREDIT_EXHAUSTION":       ("UC3", "Burstable CPU credits exhausted - instance throttled to baseline"),
    "DISK_LOG_GROWTH":         ("UC4", "Steady disk growth (logs / temp / data accumulation)"),
    "DISK_SUDDEN_FILL":        ("UC4", "Sudden disk fill (dump / export / runaway writer)"),
    "NETWORK_INGRESS_ANOMALY": ("UC5", "Abrupt inbound-traffic anomaly (attack / scan / misbehaving client)"),
    "NETWORK_EGRESS_ANOMALY":  ("UC5", "Outbound-traffic spike with normal inbound (bulk transfer / exfiltration-like)"),
    "NETWORK_TRAFFIC_LOSS":    ("UC5", "Traffic vanished while the VM is alive (upstream routing / LB / DNS / NSG issue)"),
    "TRANSIENT_SPIKE":         ("X",   "Short self-resolving spike with no corroborating deviation"),
    "ALERT_FLAPPING":          ("X",   "Alert rule flapping around its threshold (rule tuning issue, not a capacity issue)"),
    "UNDETERMINED":            ("X",   "Alert confirmed but evidence does not single out a cause"),
}


STICKY_MARGIN = 0.15
_GENERIC = {"TRANSIENT_SPIKE", "ALERT_FLAPPING"}


# ── data structures ──────────────────────────────────────────────────────────

@dataclass
class Check:
    label: str
    passed: Optional[bool]       # None => data not available
    weight: float
    detail: str = ""
    required: bool = False


def ev_pass(c: "Check") -> str:
    """A met check reads as a plain statement of the measured fact."""
    return c.detail or c.label


def ev_fail(c: "Check") -> str:
    """A failed check says what was expected and what was actually measured."""
    return f"expected {c.label}" + (f", but {c.detail}" if c.detail and c.detail != c.label else "")


@dataclass
class Hypothesis:
    id: str
    score: float
    checks: list = field(default_factory=list)

    @property
    def supports(self):
        return [c for c in self.checks if c.passed and c.weight > 0]

    @property
    def against(self):
        return [c for c in self.checks if c.passed is False]

    @property
    def missing(self):
        return [c for c in self.checks if c.passed is None]

    def to_dict(self):
        return {
            "id": self.id, "label": ROOT_CAUSE_LABELS[self.id][1], "score": round(self.score, 3),
            "supporting": [ev_pass(c) for c in self.supports],
            "contradicting": [ev_fail(c) for c in self.against if c.weight > 0 or c.required],
            "unavailable": [c.label for c in self.missing if c.weight > 0],
        }


@dataclass
class RCAResult:
    root_cause_id: str
    label: str
    use_case: str
    confidence: float
    top_score: float
    hypotheses: list                       # ranked list[dict]
    evidence: list                         # supporting evidence lines for the winner
    counter_evidence: list                 # facts that argue against the winner
    alternatives: list                     # runner-up summaries
    root_resource_id: Optional[str] = None # where the cause lives (cross-resource)
    downstream_resource_ids: list = field(default_factory=list)
    confidence_parts: dict = field(default_factory=dict)
    primary_metrics: list = field(default_factory=list)
    incident_hours: Optional[float] = None
    facts: dict = field(default_factory=dict)   # headline numbers reused by playbooks / explanation

    def to_dict(self):
        return {
            "root_cause_id": self.root_cause_id, "label": self.label, "use_case": self.use_case,
            "confidence": self.confidence, "top_score": self.top_score,
            "hypotheses": self.hypotheses, "evidence": self.evidence,
            "counter_evidence": self.counter_evidence, "alternatives": self.alternatives,
            "root_resource_id": self.root_resource_id,
            "downstream_resource_ids": self.downstream_resource_ids,
            "confidence_parts": self.confidence_parts, "primary_metrics": self.primary_metrics,
            "incident_hours": self.incident_hours, "facts": self.facts,
        }


@dataclass
class RCAContext:
    incident: dict
    profile: dict
    results: dict                    # metric -> AlertResult.to_dict()
    norm: object                     # NormalizedProfile
    batch_date: datetime
    ml: Optional[object] = None      # MLAnomalyResult
    ml_corrs: list = field(default_factory=list)
    pattern: Optional[dict] = None   # historical pattern stats for this alert signature
    peers: dict = field(default_factory=dict)


def _fmt(x, nd=1):
    if x is None:
        return "n/a"
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:.2f}G"
    if ax >= 1e6:
        return f"{x / 1e6:.1f}M"
    if ax >= 1e4:
        return f"{x / 1e3:.1f}k"
    return f"{x:.{nd}f}"


# ── the analyzer ─────────────────────────────────────────────────────────────

class RootCauseAnalyzer:

    def analyze_local(self, ctx: RCAContext, prefer: Optional[str] = None) -> RCAResult:
        """
        `prefer`: the diagnosis already reported for this incident.  It is kept unless another cause
        beats it by at least STICKY_MARGIN - a diagnosis should not flip-flop day to day.
        """
        s = _Signals(ctx)
        hyps: list[Hypothesis] = []
        for hid, fn in _HYPOTHESES.items():
            checks = fn(s)
            sc = _score(checks)
            if hid in _GENERIC:           # generic explanations lose ties against specific ones
                sc *= 0.98
            hyps.append(Hypothesis(hid, sc, checks))
        hyps.sort(key=lambda h: h.score, reverse=True)
        if prefer and hyps and hyps[0].id != prefer:
            cur = next((h for h in hyps if h.id == prefer), None)
            if cur is not None and cur.score >= 0.55 and hyps[0].score - cur.score < STICKY_MARGIN:
                hyps.remove(cur)
                hyps.insert(0, cur)
        return self._finalise(ctx, s, hyps)

    # -- cross-resource pass ---------------------------------------------------

    def apply_upstream(self, result: RCAResult, ctx: RCAContext, upstream: list[dict]) -> RCAResult:
        """
        `upstream`: [{resource_id, resource_name, tier, root_cause_id, opened_at, ...}] of incidents on
        upstream-tier resources of the same app whose local diagnosis is traffic-type.
        A downstream symptom that is fully explained by an upstream cause is attributed upstream
        (one cause, many symptoms) - the downstream operator is told NOT to chase it locally.
        """
        if not upstream or result.root_cause_id in ("UPSTREAM_PROPAGATION", "TRANSIENT_SPIKE", "ALERT_FLAPPING"):
            return result
        if result.root_cause_id.startswith(("MEMORY", "DISK", "CREDIT")):
            return result
        s = _Signals(ctx)
        opened = as_utc(ctx.incident.get("opened_at"))
        first_up = min(upstream, key=lambda u: as_utc(u["opened_at"]))
        lead_h = (opened - as_utc(first_up["opened_at"])).total_seconds() / 3600.0
        nin = s.net_ratio_mean_during_alert()
        checks = [
            Check("upstream traffic incident exists", True, 0, required=True,
                  detail=f"the upstream {first_up['tier']}-tier resource '{first_up['resource_name']}' has an open "
                         f"{first_up['root_cause_id']} incident"),
            Check("the upstream alert to fire first (or at the same time)", lead_h >= -0.5, 3,
                  detail=f"the upstream alert fired {abs(lead_h):.1f}h {'before' if lead_h >= 0 else 'after'} this one"),
            Check("elevated traffic on this resource too", None if nin is None else nin >= 1.4, 2,
                  detail=f"network-in here ran at {_fmt(nin)}x its baseline"),
            Check("more than one upstream node affected (tier-wide)", len(upstream) >= 2, 1,
                  detail=f"{len(upstream)} upstream node(s) alerted in the same window"),
            Check("a learned correlation between the two resources", _has_learned_corr(ctx, first_up["resource_id"]) or None, 1.5,
                  detail="the ML-learned daily correlation links the upstream traffic and this resource's load"),
        ]
        # a lone traffic-surge local diagnosis is the same physical event -> attribute upstream
        score = _score(checks)
        if score < 0.6:
            return result
        up = Hypothesis("UPSTREAM_PROPAGATION", score, checks)
        local = result.hypotheses[0] if result.hypotheses else None
        hyps = [up.to_dict()] + [h for h in result.hypotheses if h["id"] != "UPSTREAM_PROPAGATION"]
        # margin is measured against the best explanation that is NOT the local view of the same event
        others = [h for h in result.hypotheses if h["id"] != (local or {}).get("id")]
        runner = Hypothesis(others[0]["id"], others[0]["score"], []) if others else None
        conf, parts = _confidence(up, runner, ctx, s, missing_frac=0.0, boost_peer=True)
        result.alternatives = [
            f"{local['label']} (local view, score {local['score']:.2f}) - same symptoms, but an upstream cause "
            f"explains them with earlier timing" if local else ""
        ] + result.alternatives
        result.root_cause_id = "UPSTREAM_PROPAGATION"
        result.label = ROOT_CAUSE_LABELS["UPSTREAM_PROPAGATION"][1]
        result.use_case = "UC1"
        result.hypotheses = hyps
        result.evidence = [ev_pass(c) for c in up.supports]
        result.counter_evidence = [ev_fail(c) for c in up.against if c.weight > 0]
        result.confidence, result.confidence_parts, result.top_score = conf, parts, up.score
        result.root_resource_id = first_up["resource_id"]
        result.facts["upstream_resource_name"] = first_up["resource_name"]
        result.facts["upstream_root_cause"] = first_up["root_cause_id"]
        result.facts["upstream_nodes"] = [u["resource_name"] for u in upstream]
        return result

    # -- assembling ------------------------------------------------------------

    def _finalise(self, ctx: RCAContext, s: "_Signals", hyps: list[Hypothesis]) -> RCAResult:
        top = hyps[0]
        second = hyps[1] if len(hyps) > 1 else None
        if top.score < 0.55:
            und = Hypothesis("UNDETERMINED", 0.25, [Check("no hypothesis scored >= 0.55", True, 1,
                             detail=f"best candidate was {top.id} at {top.score:.2f}")])
            hyps = [und] + hyps
            top, second = und, top
        missing_frac = _missing_frac(top)
        conf, parts = _confidence(top, second, ctx, s, missing_frac)
        uc, label = ROOT_CAUSE_LABELS[top.id]
        return RCAResult(
            root_cause_id=top.id, label=label, use_case=uc, confidence=conf, top_score=top.score,
            hypotheses=[h.to_dict() for h in hyps[:5]],
            evidence=[ev_pass(c) for c in top.supports],
            counter_evidence=[ev_fail(c) for c in top.against if c.weight > 0],
            alternatives=[f"{ROOT_CAUSE_LABELS[h.id][1]} (score {h.score:.2f}) - argued against by: "
                          + ("; ".join(ev_fail(c) for c in h.against if c.weight > 0 or c.required)[:300] or "insufficient support")
                          for h in hyps[1:3] if h.score > 0.15],
            confidence_parts=parts,
            primary_metrics=sorted(s.alert_metrics),
            incident_hours=s.incident_hours,
            facts=s.headline_facts(),
        )


# ── scoring helpers ──────────────────────────────────────────────────────────

def _score(checks: list) -> float:
    """
    Weighted share of checks that passed.  Checks whose data is unavailable count HALF against the
    hypothesis, so a cause that can only be "confirmed" on a fraction of its evidence cannot outrank
    one that is fully confirmed (a resource without network metrics never looks like a traffic surge).
    """
    for c in checks:
        if c.required and c.passed is not True:
            return 0.0
    num = den = miss = 0.0
    for c in checks:
        if c.weight <= 0:
            continue
        if c.passed is None:
            miss += c.weight
            continue
        den += c.weight
        if c.passed:
            num += c.weight
    total = den + 0.5 * miss
    return num / total if total > 0 else 0.0


def _missing_frac(h: Hypothesis) -> float:
    tot = sum(c.weight for c in h.checks if c.weight > 0)
    miss = sum(c.weight for c in h.checks if c.weight > 0 and c.passed is None)
    return miss / tot if tot else 0.0


def _has_learned_corr(ctx: RCAContext, other_rid: str) -> bool:
    for c in ctx.ml_corrs or []:
        if other_rid in (c.get("resource_a_id"), c.get("resource_b_id")) and c.get("confidence") in ("medium", "high"):
            return True
    return False


def _confidence(top: Hypothesis, second: Optional[Hypothesis], ctx: RCAContext, s, missing_frac: float,
                boost_peer: bool = False):
    margin = min(1.0, max(0.0, (top.score - (second.score if second else 0.0)) / 0.4))
    parts = {"base": 0.30, "evidence_score": round(0.50 * top.score, 3), "margin": round(0.12 * margin, 3)}
    c = 0.30 + 0.50 * top.score + 0.12 * margin
    if ctx.ml is not None:
        if getattr(ctx.ml, "is_anomaly", False):
            c += 0.05
            parts["ml_agrees"] = 0.05
        else:
            c -= 0.04
            parts["ml_sees_normal"] = -0.04
    p = ctx.pattern or {}
    if p.get("root_cause_counts", {}).get(top.id, 0) >= 2:
        c += 0.04
        parts["history_consistent"] = 0.04
    if boost_peer or _corr_supports(ctx, top.id):
        c += 0.04
        parts["correlation_support"] = 0.04
    if missing_frac > 0.3:
        c -= 0.08
        parts["missing_data"] = -0.08
    return round(float(min(max(c, 0.25), 0.95)), 2), parts


def _corr_supports(ctx: RCAContext, rc_id: str) -> bool:
    if rc_id not in ("CPU_TRAFFIC_SURGE", "NETWORK_INGRESS_ANOMALY", "NETWORK_EGRESS_ANOMALY"):
        return False
    rid = ctx.profile.get("_id")
    for c in ctx.ml_corrs or []:
        if c.get("resource_a_id") == rid and c.get("resource_b_id") == rid and c.get("confidence") in ("medium", "high"):
            pair = {c.get("resource_a_metric"), c.get("resource_b_metric")}
            if CPU in pair and (NIN in pair or NOUT in pair):
                return True
    return False


# ── signal extraction ────────────────────────────────────────────────────────

class _Signals:
    """All the measurable facts about one incident, computed once."""

    def __init__(self, ctx: RCAContext):
        self.ctx = ctx
        self.res = ctx.results
        self.alerts = ctx.incident.get("alerts") or []
        self.alert_metrics = {a["metric"] for a in self.alerts}
        self.anchor = ctx.incident.get("anchor") or {}
        self.norm = ctx.norm
        self.cfg = ctx.profile.get("config") or {}
        self._hourly = {}
        self._episodes = self._episode_list()
        self.incident_hours = self._incident_hours()
        self.all_resolved = all(a.get("resolved_at") is not None for a in self.alerts)

    # -- raw access ------------------------------------------------------------
    def has(self, m):       return m in self.res and self.res[m].get("status") != "NO_DATA"
    def r(self, m):         return self.res.get(m) or {}
    def f(self, m):         return self.r(m).get("features") or {}
    def h(self, m):         return self.r(m).get("history") or {}
    def alerted(self, m):   return m in self.alert_metrics

    def series(self, m) -> np.ndarray:
        if m not in self._hourly:
            self._hourly[m] = F.hourly_values((self.ctx.profile.get("metrics") or {}).get(m) or {})
        return self._hourly[m]

    def ratio_series(self, m) -> np.ndarray:
        md = (self.ctx.profile.get("metrics") or {}).get(m) or {}
        b = md.get("baseline_used")
        bm, _ = F.baseline_arrays(b, 1)
        return F.hourly_ratio(self.series(m), bm)

    def anchored_shift(self, m) -> Optional[float]:
        a = self.anchor.get(m)
        avg = self.r(m).get("daily_avg")
        if not a or a.get("pre_avg") is None or avg is None:
            return None
        return avg - a["pre_avg"]

    # -- alert-derived ----------------------------------------------------------
    def _episode_list(self):
        """One entry per alert with violating-hours estimate."""
        eps = []
        for a in self.alerts:
            f, r = as_utc(a.get("fired_at")), as_utc(a.get("resolved_at"))
            ev = 1
            hrs = None
            if f and r:
                hrs = (r - f).total_seconds() / 3600.0
            eps.append({"alert": a, "fired": f, "resolved": r, "hours": hrs})
        return eps

    def _incident_hours(self) -> Optional[float]:
        fired = [e["fired"] for e in self._episodes if e["fired"]]
        if not fired:
            return None
        start = min(fired)
        ends = [e["resolved"] for e in self._episodes if e["resolved"]]
        if any(e["resolved"] is None for e in self._episodes):
            end = as_utc(self.ctx.batch_date) + timedelta(days=1)
        else:
            end = max(ends)
        return (end - start).total_seconds() / 3600.0

    def episode_hours(self, e) -> Optional[float]:
        """Violating hours of one alert episode ~ (resolve - fire) + (evaluation_periods - 1)."""
        if e["hours"] is None:
            return None
        return e["hours"] + max(int(e["alert"].get("evaluation_periods") or 1) - 1, 0)

    def max_episode_hours(self) -> Optional[float]:
        hs = [self.episode_hours(e) for e in self._episodes]
        return None if any(h is None for h in hs) else (max(hs) if hs else None)

    def rule_episode_counts(self) -> dict:
        out: dict = {}
        for a in self.alerts:
            out.setdefault(a.get("rule_id") or a.get("rule_name"), []).append(as_utc(a.get("fired_at")))
        return out

    def flapping_episodes(self) -> int:
        best = 0
        for times in self.rule_episode_counts().values():
            ts = sorted(t for t in times if t)
            for i, t in enumerate(ts):
                n = sum(1 for u in ts[i:] if (u - t).total_seconds() <= FLAPPING_WINDOW_HOURS * 3600)
                best = max(best, n)
        return best

    def recurrence_count(self, metric: str) -> int:
        """Earlier (distinct) episodes of the same metric at the same weekday & hour (+ this one)."""
        events = self.ctx.profile.get("alert_events") or []
        this = [as_utc(a.get("fired_at")) for a in self.alerts if a["metric"] == metric and a.get("fired_at")]
        if not this:
            return 0
        anchor = min(this)
        ids_now = {a["alert_id"] for a in self.alerts}
        prev_days = set()
        for e in events:
            if e.get("metric") != metric or e.get("alert_id") in ids_now:
                continue
            t = as_utc(e.get("fired_at"))
            if not t or t >= anchor - timedelta(hours=20):
                continue
            dh = abs(t.hour - anchor.hour)
            dh = min(dh, 24 - dh)
            if t.weekday() == anchor.weekday() and dh <= RECURRENCE_HOUR_TOLERANCE:
                prev_days.add(t.date())
        return len(prev_days) + 1

    def prior_alert_free_days(self, metric: str, days: int = 7) -> bool:
        events = self.ctx.profile.get("alert_events") or []
        ids_now = {a["alert_id"] for a in self.alerts}
        first = min((as_utc(a["fired_at"]) for a in self.alerts if a.get("fired_at")), default=None)
        if not first:
            return True
        for e in events:
            if e.get("alert_id") in ids_now or e.get("metric") != metric:
                continue
            t = as_utc(e.get("fired_at"))
            if t and 0 < (first - t).total_seconds() <= days * 86400:
                return False
        return True

    # -- metric-derived ---------------------------------------------------------
    def high_mask(self, m, thr):
        v = self.series(m)
        return np.where(np.isnan(v), False, v >= thr)

    def net_ratio_during(self, mask, m=NIN) -> Optional[float]:
        if not self.has(m):
            return None
        rt = self.ratio_series(m)
        if np.isfinite(rt).any() and mask.any():
            sel = rt[mask & np.isfinite(rt)]
            if sel.size:
                return float(np.mean(sel))
        v = self.series(m)
        if mask.any() and (~mask).any():
            a, b = np.nanmean(v[mask]), np.nanmean(v[~mask])
            return float(a / b) if b and b > 0 else None
        return None

    def cpu_high_mask(self):
        m = self.high_mask(CPU, 75.0)
        if not m.any():
            v = self.series(CPU)
            if np.isfinite(v).any():
                k = max(int(np.isfinite(v).sum() // 6), 2)
                thr = np.sort(v[np.isfinite(v)])[-k]
                m = np.where(np.isnan(v), False, v >= thr)
        return m

    def net_ratio_mean_during_alert(self) -> Optional[float]:
        return self.net_ratio_during(self.cpu_high_mask() if self.has(CPU) else np.ones(24, bool))

    def corr(self, a, b) -> Optional[float]:
        if not (self.has(a) and self.has(b)):
            return None
        return F.pearson(self.series(a), self.series(b))

    def peers_alerting(self) -> Optional[bool]:
        p = self.ctx.peers or {}
        if "same_tier_total" not in p or p["same_tier_total"] == 0:
            return None
        return p.get("same_tier_alerting", 0) > 0

    def headline_facts(self) -> dict:
        facts = {}
        for m in (CPU, MEM, DISK, CREDIT, WAIT, NIN, NOUT, DWRITE):
            r = self.r(m)
            if r and r.get("daily_avg") is not None:
                facts[m] = {"avg": r.get("daily_avg"), "max": r.get("daily_max"), "min": r.get("daily_min"),
                            "baseline_avg": (r.get("features") or {}).get("baseline_avg"),
                            "ratio_max": (r.get("features") or {}).get("ratio_max"),
                            "slope_7d": (r.get("history") or {}).get("slope_7d"),
                            "status": r.get("status")}
        facts["incident_hours"] = self.incident_hours
        return facts


# ── hypothesis definitions ───────────────────────────────────────────────────
# Each returns a list[Check].  `s` is a _Signals.

def _c(label, passed, weight, detail="", required=False):
    return Check(label, passed, weight, detail or label, required)


def h_cpu_traffic_surge(s: _Signals):
    if not s.has(CPU):
        return [_c("cpu data", False, 1, required=True)]
    mask = s.cpu_high_mask()
    ratio = s.net_ratio_during(mask)
    corr = s.corr(CPU, NIN)
    up = s.f(NIN).get("max_up_ratio")
    mem_max = s.r(MEM).get("daily_max") if s.has(MEM) else None
    rec = s.recurrence_count(CPU)
    peers = s.peers_alerting()
    return [
        _c("a CPU alert", s.alerted(CPU), 0, required=True),
        _c("network-in data to judge traffic", ratio is not None, 0, required=True),
        _c("network-in elevated during the CPU-high hours", None if ratio is None else ratio >= 1.8, 3,
           f"network-in averaged {_fmt(ratio)}x its same-hour baseline while CPU was high"),
        _c("CPU to follow network-in hour by hour", None if corr is None else corr >= 0.6, 2,
           f"the hourly correlation of CPU with network-in is r={_fmt(corr, 2)}"),
        _c("a gradual (ramp-like) onset", None if up is None else up <= 3.5, 1.5,
           f"the largest hour-to-hour network-in jump is x{_fmt(up)}"),
        _c("memory not to be the limiting factor", None if mem_max is None else mem_max < 90, 1,
           f"memory peaked at {_fmt(mem_max)}%"),
        _c("no repeating schedule", rec < RECURRENCE_MIN_EPISODES, 1,
           f"{rec - 1} earlier alert(s) at this weekday/hour" if rec > 1 else "no earlier alert at this weekday/hour"),
        _c("peer nodes of the same tier to alert too (shared traffic source)", peers, 1,
           "peer nodes of the same tier show the same alert" if peers else "no peer node of the same tier alerts"),
    ]


def h_cpu_runaway(s: _Signals):
    if not s.has(CPU):
        return [_c("cpu data", False, 1, required=True)]
    mask = s.cpu_high_mask()
    ratio = s.net_ratio_during(mask)
    corr = s.corr(CPU, NIN)
    cpu = s.series(CPU)
    hi = cpu[mask & ~np.isnan(cpu)]
    flat = None if hi.size < 3 else float(np.std(hi)) <= 3.5
    jump = s.f(CPU).get("max_up_jump")
    mem_max = s.r(MEM).get("daily_max") if s.has(MEM) else None
    rec = s.recurrence_count(CPU)
    hi_txt = (f"CPU sat at {_fmt(float(np.mean(hi)))}% with a standard deviation of {_fmt(float(np.std(hi)))} across "
              f"{hi.size} high hours") if hi.size else "too few high-CPU hours to judge"
    return [
        _c("a CPU alert", s.alerted(CPU), 0, required=True),
        _c("a sustained (not transient) episode",
           (s.max_episode_hours() is None) or s.max_episode_hours() > TRANSIENT_MAX_HOURS or not s.all_resolved, 0,
           required=True),
        _c("no credit / memory / disk alert explaining it",
           not (s.alerted(CREDIT) or s.alerted(WAIT) or s.alerted(MEM) or s.alerted(DISK)), 0, required=True),
        _c("normal traffic while CPU is high", None if ratio is None else ratio <= 1.3, 3,
           f"network-in averaged {_fmt(ratio)}x its baseline during the CPU-high hours"),
        _c("a flat CPU plateau", flat, 2, hi_txt),
        _c("an abrupt onset", None if jump is None else jump >= 20, 1.5,
           f"CPU rose {_fmt(jump)} points within a single hour"),
        _c("CPU not to follow network-in", None if corr is None else corr < 0.5, 1,
           f"the hourly correlation of CPU with network-in is r={_fmt(corr, 2)}"),
        _c("normal memory", None if mem_max is None else mem_max < 85, 1, f"memory peaked at {_fmt(mem_max)}%"),
        _c("no repeating schedule", rec < RECURRENCE_MIN_EPISODES, 2,
           f"{rec - 1} earlier alert(s) at this weekday/hour" if rec > 1 else "no earlier alert at this weekday/hour"),
    ]


def h_cpu_recurring(s: _Signals):
    rec = s.recurrence_count(CPU)
    ratio = s.net_ratio_during(s.cpu_high_mask()) if s.has(CPU) else None
    hi = s.series(CPU)[s.cpu_high_mask()] if s.has(CPU) else np.array([])
    hi = hi[~np.isnan(hi)] if hi.size else hi
    flat = None if hi.size < 3 else float(np.std(hi)) <= 3.5
    return [
        _c("a CPU alert", s.alerted(CPU), 0, required=True),
        _c("earlier alerts at the same weekday and hour", rec >= RECURRENCE_MIN_EPISODES, 4,
           f"this is the {rec}{_ord(rec)} alert on this weekday/hour - a schedule, not a one-off incident", required=True),
        _c("normal traffic", None if ratio is None else ratio <= 1.5, 1, f"network-in averaged {_fmt(ratio)}x baseline"),
        _c("a flat, job-like plateau", flat, 1,
           f"CPU plateau standard deviation is {_fmt(float(np.std(hi)) if hi.size else None)}"),
    ]


def _ord(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def h_alert_flapping(s: _Signals):
    n = s.flapping_episodes()
    mx = s.max_episode_hours()
    peak_over = None
    for a in s.alerts:
        if a.get("observed") is not None and a.get("threshold") and a.get("op") == ">":
            over = (a["observed"] - a["threshold"]) / abs(a["threshold"])
            peak_over = over if peak_over is None else max(peak_over, over)
    return [
        _c("the same alert rule to fire repeatedly", n >= FLAPPING_MIN_EPISODES, 3,
           f"the same alert rule fired {n} time(s) within {FLAPPING_WINDOW_HOURS}h", required=True),
        _c("every episode to be short", None if mx is None else mx <= 3.5, 1.5,
           f"the longest episode lasted {_fmt(mx)}h", required=mx is not None),
        _c("the metric to hover just above the threshold", None if peak_over is None else peak_over <= 0.12, 2,
           f"observed values were at most {_fmt((peak_over or 0) * 100)}% above the threshold", required=peak_over is not None),
        _c("no other metric to deviate", not _others_anomalous(s), 1, "another metric deviates from its baseline"
           if _others_anomalous(s) else "no other metric deviates from its baseline"),
    ]


def _others_anomalous(s: _Signals) -> bool:
    # credit / scheduler metrics are CONSEQUENCES of a CPU burst, not independent evidence
    ignore = set(s.alert_metrics)
    if CPU in s.alert_metrics:
        ignore |= {CREDIT, WAIT}
    for m, r in s.res.items():
        if m in ignore or r.get("status") in (None, "NO_DATA", "OK"):
            continue
        return True
    return False


def h_transient(s: _Signals):
    mx = s.max_episode_hours()
    cpu_rec = s.recurrence_count(CPU) if s.alerted(CPU) else 1
    return [
        _c("the alert to self-resolve", s.all_resolved, 0, required=True),
        _c("a short episode", None if mx is None else mx <= TRANSIENT_MAX_HOURS, 0, f"the episode lasted {_fmt(mx)}h",
           required=True),
        _c("no repeating schedule", cpu_rec < RECURRENCE_MIN_EPISODES, 0, required=True),
        _c("no flapping", s.flapping_episodes() < FLAPPING_MIN_EPISODES, 0, required=True),
        _c("a single short episode", True, 3, f"one episode of about {_fmt(mx)}h that resolved by itself"),
        _c("no other metric to deviate", not _others_anomalous(s), 2,
           "another metric deviates from its baseline" if _others_anomalous(s) else "no other metric deviated from its baseline"),
        _c("no earlier alert on this metric in the previous 7 days", all(s.prior_alert_free_days(m) for m in s.alert_metrics), 1.5,
           "an earlier alert on this metric exists within 7 days" if not all(s.prior_alert_free_days(m) for m in s.alert_metrics)
           else "no earlier alert on this metric in the previous 7 days"),
    ]


def h_memory_leak(s: _Signals):
    if not s.has(MEM):
        return [_c("memory data", False, 1, required=True)]
    h = s.h(MEM)
    slope, r2 = h.get("slope_7d"), h.get("r2_7d")
    shape = (h.get("shape10") or {}).get("shape")
    jump = s.f(MEM).get("max_up_jump")
    lin = None if slope is None else (slope >= 0.6 and (r2 or 0) >= 0.7)
    return [
        _c("a memory alert", s.alerted(MEM), 0, required=True),
        _c("steady linear growth over days", lin, 3,
           f"memory grew {_fmt(slope, 2)} points/day over the last 7 days (linear fit r2={_fmt(r2, 2)})"),
        _c("a ramp rather than a step", None if shape in (None, "unknown") else shape != "step", 2,
           f"the multi-day shape is '{shape}'"),
        _c("no abrupt hourly jump", None if jump is None else jump < 8, 1.5, f"the largest hourly rise is {_fmt(jump)} points"),
        _c("a rising 10-day daily-average line", None if shape in (None, "unknown") else shape == "linear_up", 1.5,
           f"the 10-day shape is '{shape}'"),
    ]


def h_memory_step(s: _Signals):
    if not s.has(MEM):
        return [_c("memory data", False, 1, required=True)]
    h = s.h(MEM)
    shape = (h.get("shape10") or {}).get("shape")
    slope, r2 = h.get("slope_7d"), h.get("r2_7d")
    shift = s.anchored_shift(MEM)
    jump = s.f(MEM).get("max_up_jump")
    rising = (slope is not None and slope >= 0.6 and (r2 or 0) >= 0.7 and shape == "linear_up")
    return [
        _c("a memory alert", s.alerted(MEM), 0, required=True),
        _c("the level to sit well above its pre-incident level", None if shift is None else shift >= 10, 3,
           f"average memory is {_fmt(shift)} points above its pre-incident level"),
        _c("a step change (or an hourly jump of 8+ points)", None if shape in (None, "unknown") and jump is None
           else (shape == "step" or (jump or 0) >= 8), 2.5,
           f"the daily series shape is '{shape}' and the largest hourly jump is {_fmt(jump)} points"),
        _c("memory to have stopped climbing", None if slope is None else not rising, 2,
           f"the 7-day slope is {_fmt(slope, 2)} points/day"),
    ]


def h_credit_exhaustion(s: _Signals):
    bc = getattr(s.norm, "burst_context", None)
    burstable = bool(bc and bc.is_burstable)
    base = getattr(bc, "baseline_cpu_pct", None) if bc else None
    checks = [
        _c("a credit or scheduler-wait alert", s.alerted(CREDIT) or s.alerted(WAIT), 0, required=True),
        _c("a burstable / shared-core instance", burstable, 0, "the instance type is not burstable", required=True),
    ]
    cpu_max = s.r(CPU).get("daily_max") if s.has(CPU) else None
    cpu_avg = s.r(CPU).get("daily_avg") if s.has(CPU) else None
    if s.has(CREDIT):
        cmin = s.r(CREDIT).get("daily_min")
        shift = s.anchored_shift(CREDIT)
        maxc = getattr(bc, "max_credits", None)
        checks += [
            _c("the credit balance to be at or below the critical level", None if cmin is None else cmin <= 5, 4,
               f"the credit balance fell to {_fmt(cmin)} (critical below 5)"),
            _c("CPU working at/above the burst baseline", None if cpu_max is None or not base else cpu_max >= 0.9 * base, 1.5,
               f"peak CPU was {_fmt(cpu_max)}% against an instance baseline of {_fmt(base)}%"),
            _c("a large drop from the pre-incident balance", None if shift is None else shift <= -50, 2,
               f"the balance is {_fmt(shift)} versus its pre-incident level"
               + (f" (max {maxc})" if maxc else "")),
            _c("a prolonged episode", None if s.incident_hours is None else s.incident_hours >= 6, 1,
               f"the incident has lasted {_fmt(s.incident_hours)}h"),
        ]
    else:  # GCP shared-core: scheduler wait is the only signal
        wmax = s.r(WAIT).get("daily_max") if s.has(WAIT) else None
        shift = s.anchored_shift(WAIT)
        checks += [
            _c("high vCPU scheduler wait", None if wmax is None else wmax >= 300, 4,
               f"vCPU scheduler wait reached {_fmt(wmax)} s/h (alert at 300)"),
            _c("CPU pinned near the shared-core baseline", None if cpu_avg is None or not base else
               (0.6 * base <= cpu_avg <= 1.4 * base), 2,
               f"average CPU is {_fmt(cpu_avg)}% against a ~{_fmt(base)}% shared-core baseline"),
            _c("scheduler wait far above its pre-incident level", None if shift is None else shift >= 200, 1.5,
               f"scheduler wait is {_fmt(shift)} s/h above its pre-incident level"),
            _c("a prolonged episode", None if s.incident_hours is None else s.incident_hours >= 6, 1,
               f"the incident has lasted {_fmt(s.incident_hours)}h"),
        ]
    return checks


def h_disk_growth(s: _Signals):
    if not s.has(DISK):
        return [_c("disk data", False, 1, required=True)]
    h = s.h(DISK)
    slope, r2 = h.get("slope_7d"), h.get("r2_7d")
    shape = (h.get("shape10") or {}).get("shape")
    jump = s.f(DISK).get("max_up_jump")
    w = s.ratio_series(DWRITE) if s.has(DWRITE) else None
    wmax = float(np.nanmax(w)) if w is not None and np.isfinite(w).any() else None
    return [
        _c("a disk alert", s.alerted(DISK), 0, required=True),
        _c("steady linear growth", None if slope is None else (slope >= 0.4 and (r2 or 0) >= 0.85), 3,
           f"disk usage grew {_fmt(slope, 2)} points/day (linear fit r2={_fmt(r2, 2)})"),
        _c("no sudden jump", None if jump is None and shape in (None, "unknown") else
           ((jump or 0) < 5 and shape != "step"), 2,
           f"the largest hourly rise is {_fmt(jump)} points and the multi-day shape is '{shape}'"),
        _c("a normal write rate", None if wmax is None else wmax < 2.5, 1,
           f"disk writes peaked at {_fmt(wmax)}x their baseline"),
    ]


def h_disk_sudden(s: _Signals):
    if not s.has(DISK):
        return [_c("disk data", False, 1, required=True)]
    h = s.h(DISK)
    shape = (h.get("shape10") or {}).get("shape")
    step = (h.get("shape10") or {}).get("step_size")
    jump = s.f(DISK).get("max_up_jump")
    shift = s.anchored_shift(DISK)
    w = s.ratio_series(DWRITE) if s.has(DWRITE) else None
    wmax = float(np.nanmax(w)) if w is not None and np.isfinite(w).any() else None
    sudden = None if jump is None and shape in (None, "unknown") else ((jump or 0) >= 6 or (shape == "step" and (step or 0) >= 8))
    return [
        _c("a disk alert", s.alerted(DISK), 0, required=True),
        _c("an abrupt rise", sudden, 3, f"disk usage rose {_fmt(max(jump or 0, step or 0))} points within hours (shape '{shape}')"),
        _c("a level far above the pre-incident level", None if shift is None else shift >= 8, 2,
           f"disk usage is {_fmt(shift)} points above its pre-incident level"),
        _c("a coinciding write burst", None if wmax is None else wmax >= 2.5, 1.5,
           f"disk writes peaked at {_fmt(wmax)}x their baseline"),
    ]


def h_net_ingress(s: _Signals):
    if not s.has(NIN):
        return [_c("network-in data", False, 1, required=True)]
    rmax = s.f(NIN).get("ratio_max")
    up = s.f(NIN).get("max_up_ratio")
    out_r = s.f(NOUT).get("ratio_max") if s.has(NOUT) else None
    return [
        _c("a network-in surge alert", any(a["metric"] == NIN and a["op"] == "surge" for a in s.alerts), 0, required=True),
        _c("a large multiple of baseline", None if rmax is None else rmax >= 3, 3,
           f"network-in peaked at {_fmt(rmax)}x its same-hour baseline"),
        _c("an abrupt step onset", None if up is None else up >= 3.5, 2.5,
           f"network-in changed by x{_fmt(up)} between two consecutive hours"),
        _c("CPU to stay below its alert thresholds", not s.alerted(CPU),  1.5,
           "CPU alerted as well" if s.alerted(CPU) else "CPU stayed below its alert thresholds"),
        _c("outbound traffic not to surge with it", None if out_r is None else out_r < 2, 1,
           f"network-out peaked at {_fmt(out_r)}x baseline"),
    ]


def h_net_egress(s: _Signals):
    if not s.has(NOUT):
        return [_c("network-out data", False, 1, required=True)]
    rmax = s.f(NOUT).get("ratio_max")
    in_r = s.f(NIN).get("ratio_max") if s.has(NIN) else None
    cpu_r = s.f(CPU).get("ratio_mean") if s.has(CPU) else None
    sustained = None
    rt = s.ratio_series(NOUT)
    if np.isfinite(rt).any():
        sustained = int((rt[np.isfinite(rt)] >= 2.5).sum()) >= 4
    return [
        _c("a network-out surge alert", any(a["metric"] == NOUT and a["op"] == "surge" for a in s.alerts), 0, required=True),
        _c("a large multiple of baseline", None if rmax is None else rmax >= 3, 3,
           f"network-out peaked at {_fmt(rmax)}x its same-hour baseline"),
        _c("normal inbound traffic", None if in_r is None else in_r < 1.6, 3,
           f"network-in peaked at {_fmt(in_r)}x baseline"),
        _c("CPU to stay normal", None if cpu_r is None else cpu_r < 1.4 and not s.alerted(CPU), 1.5,
           f"CPU averaged {_fmt(cpu_r)}x its baseline" + (" and alerted" if s.alerted(CPU) else "")),
        _c("the elevated outbound rate to persist for 4+ hours", sustained, 1,
           "the outbound rate stayed 2.5x+ above baseline for 4 or more hours" if sustained else "the elevated period was shorter than 4 hours"),
    ]


def h_net_loss(s: _Signals):
    drops = [a for a in s.alerts if a["op"] == "drop"]
    m = NIN if s.has(NIN) else NOUT
    rmin = s.f(m).get("ratio_min") if s.has(m) else None
    cpu_now = s.r(CPU).get("daily_min") if s.has(CPU) else None
    mem_r = s.f(MEM).get("ratio_mean") if s.has(MEM) else None
    running = getattr(s.norm, "is_running", None)
    return [
        _c("a traffic-drop alert", bool(drops), 0, required=True),
        _c("traffic to fall to a small fraction of baseline", None if rmin is None else rmin <= 0.2, 3,
           f"network traffic fell to {_fmt(rmin, 2)}x of its normal level"),
        _c("the VM to be up and still reporting", None if running is None else (bool(running) and cpu_now is not None), 2,
           "the VM is running and still reports CPU/memory - not an outage of the VM itself"),
        _c("memory to be unchanged", None if mem_r is None else 0.8 <= mem_r <= 1.2, 1.5,
           f"memory averaged {_fmt(mem_r, 2)}x its usual level"),
    ]


_HYPOTHESES: dict[str, Callable] = {
    "CPU_TRAFFIC_SURGE": h_cpu_traffic_surge,
    "CPU_RUNAWAY_PROCESS": h_cpu_runaway,
    "CPU_RECURRING_LOAD": h_cpu_recurring,
    "MEMORY_LEAK": h_memory_leak,
    "MEMORY_STEP_CHANGE": h_memory_step,
    "CREDIT_EXHAUSTION": h_credit_exhaustion,
    "DISK_LOG_GROWTH": h_disk_growth,
    "DISK_SUDDEN_FILL": h_disk_sudden,
    "NETWORK_INGRESS_ANOMALY": h_net_ingress,
    "NETWORK_EGRESS_ANOMALY": h_net_egress,
    "NETWORK_TRAFFIC_LOSS": h_net_loss,
    "ALERT_FLAPPING": h_alert_flapping,
    "TRANSIENT_SPIKE": h_transient,
}
