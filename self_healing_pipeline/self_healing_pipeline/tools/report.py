"""
Print / export the recommendations produced by the pipeline.

    python tools/report.py                          # one line per recommendation
    python tools/report.py --open --priority P1     # only open P1 incidents
    python tools/report.py --resource db-01 --detail
    python tools/report.py --root-cause MEMORY_LEAK --detail
    python tools/report.py --md report.md           # full markdown report of everything selected
    python tools/report.py --json recs.json
"""
import argparse
import json

from _common import DEFAULT_DATA  # noqa: F401
import pymongo

from pipeline.config import MONGO_URI, MONGO_DB_NAME, RECOMMENDATIONS_COLLECTION


def _ts(x):
    return str(x)[:16].replace("T", " ") if x else "-"


def render_summary(recs: list) -> str:
    lines = [f"{'first alert (UTC)':<17} {'cloud':<5} {'pri':<3} {'state':<8} {'resource':<32} {'use case':<24} {'root cause':<26} {'conf':<5} rev"]
    for r in sorted(recs, key=lambda r: (r["first_alert_at"], r["provider"])):
        lines.append(f"{_ts(r['first_alert_at']):<17} {r['provider']:<5} {r['priority']:<3} {r['status']:<8} {r['resource_name'][:32]:<32} "
                     f"{r['use_case_title'][:24]:<24} {r['root_cause']['id']:<26} {r['root_cause']['confidence']:<5} {r['revision']}")
    return "\n".join(lines)


def render_detail(r: dict) -> str:
    rc = r["root_cause"]
    o = []
    o.append("=" * 100)
    o.append(f"[{r['priority']}] {r['title']}   ({r['provider']} / {r['resource_type']} / {r['status']})")
    o.append(f"priority reason : {r['priority_reason']}")
    o.append(f"use case        : {r['use_case']} - {r['use_case_title']}")
    o.append(f"root cause      : {rc['id']} - {rc['label']}   confidence {rc['confidence']:.0%}")
    if rc.get("root_resource_name"):
        o.append(f"origin resource : {rc['root_resource_name']}")
    o.append(f"incident window : first alert {_ts(r['first_alert_at'])}  last alert {_ts(r['last_alert_at'])}  "
             f"resolved {_ts(r.get('resolved_at'))}   (revision {r['revision']})")
    o.append("")
    o.append("ALERTS (source)")
    for a in r["alerts"]:
        thr = a["threshold"]
        o.append(f"  - {a['severity']:<4} {a['metric']:<24} {a['op']:<5} thr={thr if thr is None else round(thr, 2)} "
                 f"observed={a['observed'] if a['observed'] is None else round(a['observed'], 2)}  "
                 f"fired {_ts(a['fired_at'])}  resolved {_ts(a.get('resolved_at'))}")
    o.append("")
    o.append("WHY THIS ROOT CAUSE (evidence)")
    o += [f"  + {e}" for e in rc["evidence"]] or ["  (none)"]
    if rc["counter_evidence"]:
        o.append("  facts that do not fit perfectly")
        o += [f"  - {e}" for e in rc["counter_evidence"]]
    if rc["alternatives"]:
        o.append("  considered and ranked lower")
        o += [f"  ~ {e}" for e in rc["alternatives"]]
    o.append(f"  confidence parts: {rc['confidence_parts']}")
    o.append("")
    o.append("CORRELATION")
    o.append(f"  {r['correlation']['summary'] or '(none)'}")
    for tl in r["correlation"]["timeline"][:12]:
        o.append(f"    {_ts(tl['time'])}  {tl['resource']:<24} {tl['event']:<8} {tl['metric']} ({tl['severity']})")
    if r["statistics"]["trends"]:
        o.append("TRENDS (seasonality-aware)")
        for t in r["statistics"]["trends"][:5]:
            s7, s30 = t["slope_7d_per_day"], t["slope_30d_per_day"]
            o.append(f"  {t['metric']:<24} history={t['days_of_history']}d  7d slope={s7 if s7 is None else round(s7, 3)}/day  "
                     f"30d slope={s30 if s30 is None else round(s30, 3)}/day  shape(10d)={t['shape_last_10d']}  "
                     f"same-weekday median={t['same_weekday_median'] if t['same_weekday_median'] is None else round(t['same_weekday_median'], 1)}")
    if r.get("ml"):
        o.append(f"  ML (Isolation Forest, {r['ml']['model_level']}, n={r['ml']['training_samples']}): "
                 f"anomaly_score={r['ml']['anomaly_score']:.2f} flagged={r['ml']['is_anomaly']}")
    o.append("")
    o.append("RECOMMENDED ACTIONS - human executed, nothing is automated")
    for ph, name in (("now", "NOW"), ("fix", "FIX"), ("prevent", "PREVENT")):
        for a in [a for a in r["actions"] if a["phase"] == ph]:
            flag = "  [disruptive]" if a["disruptive"] else ""
            o.append(f"  [{name}] {a['title']}{flag}")
            o.append(f"        {a['detail']}")
            for c in a["commands"]:
                o.append(f"        {'$ ' if not c['mutating'] else '$! '}{c['command']}   # {c['purpose']}")
    o.append("  ($ = read-only diagnostic, $! = changes the system)")
    o.append("")
    o.append("DO NOT")
    o += [f"  x {d}" for d in r["do_not_do"]]
    o.append(f"VERIFY: {r['verification']}")
    o.append(f"IF IGNORED: 1h - {r['risk_if_ignored']['1h']}  |  24h - {r['risk_if_ignored']['24h']}  |  7d - {r['risk_if_ignored']['7d']}")
    o.append("")
    ex = r["explanation"]
    o.append(f"EXPLANATION ({ex['source']})")
    for k, v in ex["sections"].items():
        o.append(f"  {k}: {v}")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resource", help="substring of the resource name")
    ap.add_argument("--root-cause")
    ap.add_argument("--priority", choices=["P1", "P2", "P3"])
    ap.add_argument("--provider", choices=["AWS", "Azure", "GCP"])
    ap.add_argument("--open", action="store_true", help="only unresolved incidents")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--md", help="write a markdown report to this file")
    ap.add_argument("--json", help="write the selected recommendations as JSON")
    a = ap.parse_args()

    db = pymongo.MongoClient(MONGO_URI, tz_aware=True)[MONGO_DB_NAME]
    q = {}
    if a.resource:
        q["resource_name"] = {"$regex": a.resource}
    if a.root_cause:
        q["root_cause.id"] = a.root_cause
    if a.priority:
        q["priority"] = a.priority
    if a.provider:
        q["provider"] = a.provider
    if a.open:
        q["status"] = "open"
    recs = list(db[RECOMMENDATIONS_COLLECTION].find(q))
    print(render_summary(recs))
    if a.detail:
        for r in sorted(recs, key=lambda r: r["first_alert_at"]):
            print(render_detail(r))
    if a.md:
        with open(a.md, "w") as f:
            f.write("# Self-healing recommendations\n\n```\n" + render_summary(recs) + "\n```\n\n")
            for r in sorted(recs, key=lambda r: r["first_alert_at"]):
                f.write("```\n" + render_detail(r) + "\n```\n\n")
    if a.json:
        json.dump(recs, open(a.json, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
