"""
Build the synthetic multi-cloud log dataset + ground truth.

    python -m generator.build_dataset                       # full fleet, 70 days -> data/
    python -m generator.build_dataset --providers AWS --projects p1 --out /tmp/mini
    python -m generator.build_dataset --aws-native-points   # AWS docs use Timestamp/Average/Sum keys

Outputs (in --out):
    synthetic_logs.ndjson.gz   one Mongo extended-JSON document per line (mongoimport / load_dataset.py)
    ground_truth.json          every injected scenario with the expected root cause (used by evaluate.py)
    dataset_manifest.json      fleet, metric matrix, counts, date range
    sample_docs.json           a handful of documents (incl. alert-bearing ones) for eyeballing
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

from . import alerts as alert_mod
from . import signals
from .docs import Identity, build_docs_for_series
from .fleet import (NATIVE_METRIC, USE_CASE_METRICS, USE_CASES, build_fleet, oid, roles_for)

DEFAULT_END = "2026-09-18"


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(days=70, end_date=DEFAULT_END, providers=("AWS", "Azure", "GCP"), projects=("p1", "p2"),
          seed=42, aws_native=False):
    if days < 60:
        raise SystemExit("days must be >= 60 (scenarios are scheduled between day 28 and day 66)")
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    t0 = end - timedelta(days=days - 1)
    start_wd = t0.weekday()
    weekday_of = lambda d: (start_wd + d) % 7
    n = days * 24

    fleet = build_fleet(tuple(providers), tuple(projects))
    all_docs, gt, fleet_info = [], [], []
    alert_total = Counter()

    for proj in fleet:
        project_id = oid(f"proj|{proj.provider}|{proj.key}")
        prng = np.random.default_rng([seed, hash_int(proj.provider), hash_int(proj.key)])
        web_latent = signals.latent_load(n, start_wd, "web", prng)
        web_latent = web_latent / web_latent.mean()
        rid_by_key = {}
        idents = {}
        for res in proj.resources:
            idents[res.key] = Identity(proj, res, project_id)
            rid_by_key[res.key] = idents[res.key].resource_id

        for res in proj.resources:
            ident = idents[res.key]
            roles = roles_for(proj.provider, res.tier)
            rrng = np.random.default_rng([seed, hash_int(proj.provider), hash_int(proj.key), hash_int(res.key)])
            arrays, windows = signals.build_resource_series(
                proj.provider, res.tier, res.instance_type, res.scenarios, roles, days, start_wd,
                rrng, web_latent, proj.day_offset, res.lag_hours, weekday_of)

            episodes_by_role = {r: alert_mod.evaluate(r, arrays[r]) for r in roles if r in arrays}
            for role, arr in arrays.items():
                if role not in roles:
                    continue
                docrng = np.random.default_rng([seed, hash_int(ident.resource_id), hash_int(role)])
                all_docs += build_docs_for_series(ident, role, arr, episodes_by_role[role], t0, days,
                                                  docrng, aws_native=aws_native)
                for ep in episodes_by_role[role]:
                    alert_total[(proj.provider, ep.severity)] += 1

            fleet_info.append(dict(provider=proj.provider, project_key=proj.key, project_id=project_id,
                                   resource_id=ident.resource_id, resource_name=ident.name,
                                   tier=res.tier, instance_type=res.instance_type, roles=roles,
                                   native_metrics=[NATIVE_METRIC[proj.provider][r] for r in roles]))

            # ---- ground truth ----------------------------------------------------
            all_eps = [e for r in roles for e in episodes_by_role.get(r, [])]
            used_win = defaultdict(int)
            for si, sc in enumerate(res.scenarios):
                wins = [w for w in windows if w["sidx"] == si]
                for k, w in enumerate(wins):
                    in_win = [e for e in all_eps if w["start"] <= e.fired_idx < w["end"]]
                    entry = dict(
                        incident_id=f"GT-{proj.provider}-{proj.key}-{res.key}-{sc.kind}" + (f"-{k + 1}" if len(wins) > 1 else ""),
                        provider=proj.provider, project_key=proj.key, project_id=project_id,
                        resource_id=ident.resource_id, resource_name=ident.name, tier=res.tier,
                        use_case=sc.use_case, scenario=sc.kind, note=sc.note,
                        window_start=_iso(t0 + timedelta(hours=w["start"])),
                        window_end=_iso(t0 + timedelta(hours=w["end"])),
                        expects_alert=sc.expects_alert,
                        expects_recommendation=sc.expected_root_cause is not None,
                        expected_root_cause=sc.expected_root_cause,
                        acceptable_root_causes=[sc.expected_root_cause] if sc.expected_root_cause else [],
                        # the origin may be any node of the upstream tier (tier-wide surge)
                        root_resource_ids=([idents[r.key].resource_id for r in proj.resources
                                            if r.tier == next(x.tier for x in proj.resources if x.key == sc.root_resource_key)]
                                           if sc.root_resource_key else []),
                        n_alert_episodes=len(in_win),
                        alert_metrics=sorted({NATIVE_METRIC[proj.provider][e.role] for e in in_win}),
                    )
                    if sc.kind == "recurring_batch":
                        entry["episode_index"] = k
                        if k < 2:          # the pattern is only learnable after the 3rd occurrence
                            entry["acceptable_root_causes"] = ["CPU_RUNAWAY_PROCESS", "CPU_RECURRING_LOAD"]
                    if sc.expects_alert and not in_win:
                        raise RuntimeError(f"scenario {entry['incident_id']} produced no alert - retune params")
                    if not sc.expects_alert and in_win:
                        raise RuntimeError(f"scenario {entry['incident_id']} must NOT alert but did")
                    gt.append(entry)
            # every alert must be explained by a scenario window
            covered = set()
            for w in windows:
                for e in all_eps:
                    if w["start"] <= e.fired_idx < w["end"]:
                        covered.add(id(e))
            for e in all_eps:
                if id(e) not in covered:
                    raise RuntimeError(f"unexplained alert on {ident.name}: {e.role} {e.severity} idx={e.fired_idx}")

    all_docs.sort(key=lambda d: (d["from_date"]["$date"], d["project"], d["resourceId"], d["metric"]))
    return all_docs, gt, fleet_info, t0, end, alert_total


def hash_int(s: str) -> int:
    import hashlib
    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=70)
    ap.add_argument("--end-date", default=DEFAULT_END, help="last day of data (UTC, YYYY-MM-DD)")
    ap.add_argument("--providers", nargs="+", default=["AWS", "Azure", "GCP"], choices=["AWS", "Azure", "GCP"])
    ap.add_argument("--projects", nargs="+", default=["p1", "p2"], choices=["p1", "p2"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    ap.add_argument("--aws-native-points", action="store_true",
                    help="emit AWS points with CloudWatch-style keys (Timestamp/Average/Sum/...)")
    a = ap.parse_args(argv)

    docs, gt, fleet_info, t0, end, alert_total = build(
        a.days, a.end_date, a.providers, a.projects, a.seed, a.aws_native_points)
    os.makedirs(a.out, exist_ok=True)

    with gzip.open(os.path.join(a.out, "synthetic_logs.ndjson.gz"), "wt", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, separators=(",", ":")) + "\n")
    with open(os.path.join(a.out, "ground_truth.json"), "w") as f:
        json.dump(gt, f, indent=1)

    with_alerts = [d for d in docs if d["alerts"]]
    sample = docs[:2] + with_alerts[:2]
    with open(os.path.join(a.out, "sample_docs.json"), "w") as f:
        json.dump(sample, f, indent=1)

    series = {(d["resourceId"], d["metric"]) for d in docs}
    manifest = dict(
        generated_with=dict(days=a.days, end_date=a.end_date, start_date=t0.strftime("%Y-%m-%d"),
                            seed=a.seed, providers=a.providers, projects=a.projects),
        counts=dict(documents=len(docs), series=len(series), resources=len(fleet_info),
                    documents_with_alerts=len(with_alerts),
                    alert_episodes={f"{p}:{s}": c for (p, s), c in sorted(alert_total.items())},
                    ground_truth_incidents=len(gt),
                    expected_recommendations=sum(1 for g in gt if g["expects_recommendation"]),
                    negative_cases=sum(1 for g in gt if not g["expects_recommendation"])),
        use_cases=USE_CASES,
        main_metrics_per_use_case_and_provider={
            uc: {p: [NATIVE_METRIC[p][r] for r in roles] for p, roles in per.items()}
            for uc, per in USE_CASE_METRICS.items()},
        fleet=fleet_info,
    )
    with open(os.path.join(a.out, "dataset_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)

    c = manifest["counts"]
    print(f"wrote {c['documents']} docs ({c['series']} series, {c['resources']} resources, "
          f"{a.days} days {t0:%Y-%m-%d}..{end:%Y-%m-%d}) -> {a.out}/")
    print(f"  docs carrying alerts: {c['documents_with_alerts']}   alert episodes: {c['alert_episodes']}")
    print(f"  ground truth: {c['ground_truth_incidents']} scenarios "
          f"({c['expected_recommendations']} expect a recommendation, {c['negative_cases']} must NOT)")


if __name__ == "__main__":
    main()
