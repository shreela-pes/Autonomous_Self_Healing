"""
Score the pipeline's recommendations against the generator's ground truth.

    python tools/evaluate.py                       # uses data/ground_truth.json and the configured MongoDB
    python tools/evaluate.py --json result.json --min-accuracy 0.9

Checks
  * detection      every injected incident that raised alerts has a recommendation for that resource/time
  * RCA accuracy   the diagnosed root cause is the expected one (or an accepted alternative)
  * gate           anomalies WITHOUT a source alert (and data gaps) produce NO recommendation
  * precision      no recommendation exists that is not explained by an injected incident
  * cross-resource downstream symptoms are attributed to the right upstream resource
"""
import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from _common import DEFAULT_DATA  # noqa: F401
import pymongo

from pipeline.config import MONGO_URI, MONGO_DB_NAME, RECOMMENDATIONS_COLLECTION


def _t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def evaluate(db, gt: list[dict]) -> dict:
    recs = list(db[RECOMMENDATIONS_COLLECTION].find({}))
    by_res = defaultdict(list)
    for r in recs:
        by_res[r["resource_id"]].append(r)

    matched_rec_ids, rows = set(), []
    for g in gt:
        ws, we = _t(g["window_start"]), _t(g["window_end"])
        cands = [r for r in by_res.get(g["resource_id"], [])
                 if ws - timedelta(hours=2) <= _aware(r["first_alert_at"]) <= we]
        if g["expects_recommendation"]:
            rec = min(cands, key=lambda r: _aware(r["first_alert_at"])) if cands else None
            if rec:
                matched_rec_ids.add(rec["_id"])
            got = rec["root_cause"]["id"] if rec else None
            ok_rc = got in g["acceptable_root_causes"]
            row = dict(gt=g["incident_id"], provider=g["provider"], use_case=g["use_case"], scenario=g["scenario"],
                       kind="positive", expected=g["expected_root_cause"], got=got, detected=rec is not None,
                       correct=ok_rc, confidence=rec["root_cause"]["confidence"] if rec else None,
                       priority=rec["priority"] if rec else None)
            if ok_rc and g.get("root_resource_ids"):
                row["root_resource_ok"] = rec["root_cause"].get("root_resource_id") in g["root_resource_ids"]
                row["correct"] = ok_rc and row["root_resource_ok"]
            rows.append(row)
        else:
            near = [r for r in by_res.get(g["resource_id"], [])
                    if ws - timedelta(hours=24) <= _aware(r["first_alert_at"]) <= we + timedelta(hours=24)]
            rows.append(dict(gt=g["incident_id"], provider=g["provider"], use_case=g["use_case"], scenario=g["scenario"],
                             kind="negative", expected=None, got=near[0]["root_cause"]["id"] if near else None,
                             detected=bool(near), correct=not near))

    # incidents whose rec matched a GT window by the *any* rule (for precision)
    for g in gt:
        ws, we = _t(g["window_start"]), _t(g["window_end"])
        for r in by_res.get(g["resource_id"], []):
            if ws - timedelta(hours=2) <= _aware(r["first_alert_at"]) <= we:
                matched_rec_ids.add(r["_id"])
    unexplained = [r for r in recs if r["_id"] not in matched_rec_ids]

    pos = [r for r in rows if r["kind"] == "positive"]
    neg = [r for r in rows if r["kind"] == "negative"]
    detected = [r for r in pos if r["detected"]]
    summary = dict(
        recommendations_total=len(recs),
        positives=len(pos), detected=len(detected),
        detection_recall=round(len(detected) / len(pos), 3) if pos else None,
        rca_correct=sum(1 for r in pos if r["correct"]),
        rca_accuracy=round(sum(1 for r in pos if r["correct"]) / len(pos), 3) if pos else None,
        negatives=len(neg), negatives_correctly_silent=sum(1 for r in neg if r["correct"]),
        unexplained_recommendations=len(unexplained),
        precision=round(len(matched_rec_ids) / len(recs), 3) if recs else None,
        every_rec_has_alert=all(r.get("alerts") for r in recs),
        every_rec_human_approved_only=all(r.get("automated_remediation") is False and r.get("requires_human_approval") for r in recs),
    )
    by_uc, by_prov = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in pos:
        for key, store in ((r["use_case"], by_uc), (r["provider"], by_prov)):
            store[key][1] += 1
            store[key][0] += int(r["correct"])
    conf = Counter((r["expected"], r["got"]) for r in pos if not r["correct"])
    return dict(summary=summary, rows=rows,
                by_use_case={k: f"{a}/{b}" for k, (a, b) in sorted(by_uc.items())},
                by_provider={k: f"{a}/{b}" for k, (a, b) in sorted(by_prov.items())},
                misses=[dict(expected=e, got=g, n=n) for (e, g), n in conf.most_common()],
                unexplained=[dict(resource=r["resource_name"], root_cause=r["root_cause"]["id"],
                                  first_alert_at=str(r["first_alert_at"])) for r in unexplained[:20]])


def print_report(res: dict) -> None:
    s = res["summary"]
    print("=" * 78)
    print("SELF-HEALING PIPELINE - EVALUATION AGAINST GROUND TRUTH")
    print("=" * 78)
    print(f"recommendations written        : {s['recommendations_total']}")
    print(f"injected incidents (positive)  : {s['positives']}   detected: {s['detected']}   recall: {s['detection_recall']}")
    print(f"root-cause accuracy            : {s['rca_correct']}/{s['positives']} = {s['rca_accuracy']}")
    print(f"negative cases silent          : {s['negatives_correctly_silent']}/{s['negatives']}  (anomaly w/o alert, data gap)")
    print(f"precision (recs explained)     : {s['precision']}   unexplained recs: {s['unexplained_recommendations']}")
    print(f"every rec carries a source alert: {s['every_rec_has_alert']}   human-approval only: {s['every_rec_human_approved_only']}")
    print(f"by use case                    : {res['by_use_case']}")
    print(f"by provider                    : {res['by_provider']}")
    print("-" * 78)
    for r in res["rows"]:
        mark = "OK " if r["correct"] else "XX "
        print(f"{mark}{r['gt']:<52} expected={r['expected'] or '(none)':<24} got={r['got'] or '(none)'}")
    if res["misses"]:
        print("misdiagnoses:", res["misses"])
    if res["unexplained"]:
        print("unexplained:", res["unexplained"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=os.path.join(DEFAULT_DATA, "ground_truth.json"))
    ap.add_argument("--json", default=None, help="write full result JSON here")
    ap.add_argument("--min-accuracy", type=float, default=0.0, help="exit 1 if RCA accuracy is below this")
    a = ap.parse_args()
    client = pymongo.MongoClient(MONGO_URI, tz_aware=True)
    gt = json.load(open(a.gt))
    res = evaluate(client[MONGO_DB_NAME], gt)
    print_report(res)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1, default=str)
    raise SystemExit(0 if (res["summary"]["rca_accuracy"] or 0) >= a.min_accuracy else 1)


if __name__ == "__main__":
    main()
