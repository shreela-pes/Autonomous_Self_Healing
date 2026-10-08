"""The synthetic dataset must satisfy the stated requirements and be internally consistent."""
import json
from collections import Counter, defaultdict

import pytest
from bson import json_util

from generator.build_dataset import build
from generator.fleet import NATIVE_METRIC, USE_CASE_METRICS, USE_CASES
from pipeline.ingestion.normalizer import parse_document
from pipeline.metrics.registry import get_canonical


@pytest.fixture(scope="module")
def ds():
    docs, gt, fleet, t0, end, alerts = build(days=70, projects=("p1",))
    return docs, gt, fleet


def test_same_schema_across_providers(ds):
    docs, _, _ = ds
    keysets = {d["service_name"]: set(d.keys()) for d in docs}
    assert set(keysets) == {"AWS", "Azure", "GCP"}
    assert len({frozenset(k) for k in keysets.values()}) == 1
    for d in docs:
        assert isinstance(d["alerts"], list)


def test_at_least_60_days_for_every_resource_and_metric(ds):
    docs, _, _ = ds
    days = defaultdict(set)
    for d in docs:
        days[(d["resourceId"], d["metric"])].add(d["from_date"]["$date"][:10])
    assert days and all(len(v) >= 60 for v in days.values())
    for d in docs[:50]:
        assert len(d["metric_value"]) == 24


def test_three_projects_with_resources_and_multiple_metrics(ds):
    docs, _, fleet = ds
    projects = {d["project"] for d in docs}
    assert len(projects) == 3
    per_res = defaultdict(set)
    for d in docs:
        per_res[d["resourceId"]].add(d["metric"])
    assert all(len(v) >= 3 for v in per_res.values())


def test_main_metrics_per_use_case_and_provider_are_two_or_three():
    assert set(USE_CASES) == {"UC1", "UC2", "UC3", "UC4", "UC5"}
    for uc, per in USE_CASE_METRICS.items():
        for prov, roles in per.items():
            assert 2 <= len(roles) <= 3, (uc, prov)
            for r in roles:
                assert r in NATIVE_METRIC[prov]


def test_every_native_metric_is_known_to_the_pipeline_registry(ds):
    for prov, m in NATIVE_METRIC.items():
        rtype = {"AWS": "EC2", "Azure": "Virtual_Machines", "GCP": "Compute_Engine"}[prov]
        for role, native in m.items():
            assert get_canonical(rtype, native)[0] is not None, (prov, native)


def test_alerts_exist_only_for_injected_incidents_and_gt_is_complete(ds):
    docs, gt, _ = ds
    assert sum(1 for g in gt if g["expects_recommendation"]) >= 25
    negatives = [g for g in gt if not g["expects_recommendation"]]
    assert len(negatives) >= 3                       # one anomaly-without-alert case per provider (p1)
    assert any(d["alerts"] for d in docs) and any(not d["alerts"] for d in docs)


def test_no_future_information_in_alert_records(ds):
    docs, _, _ = ds
    for d in docs:
        end = d["to_date"]["$date"]
        for a in d["alerts"]:
            if a["resolved_at"]:
                assert a["resolved_at"]["$date"] <= end
                assert a["state"] == "Resolved"
            else:
                assert a["state"] == "Fired"
            assert a["fired_at"]["$date"] <= end


def test_anomalies_seasonality_and_trend_are_present(ds):
    docs, _, _ = ds
    # weekend dip on a web tier CPU series (seasonality)
    import numpy as np
    from datetime import datetime
    series = {}
    for d in docs:
        if d["service_name"] == "AWS" and d["metric"] == "CPUUtilization" and "web-01" in d["resource_name"]:
            dt = datetime.strptime(d["from_date"]["$date"][:10], "%Y-%m-%d")
            series[dt] = np.mean([p["average"] for p in d["metric_value"] if "average" in p])
    wk = [v for k, v in series.items() if k.weekday() < 5]
    we = [v for k, v in series.items() if k.weekday() >= 5]
    assert np.mean(we) < 0.9 * np.mean(wk)


def test_all_documents_parse_and_alerts_are_canonicalised(ds):
    docs, _, _ = ds
    sample = [json_util.loads(json.dumps(d)) for d in docs if d["alerts"]][:200]
    for raw in sample:
        p = parse_document(raw)
        assert p is not None and p.canonical_metric
        assert all(a.metric == p.canonical_metric and a.fired_at for a in p.alerts)
    azure_mem = [json_util.loads(json.dumps(d)) for d in docs
                 if d["service_name"] == "Azure" and d["metric"] == "Available Memory Bytes" and d["alerts"]][0]
    p = parse_document(azure_mem)
    assert p.canonical_metric == "memory_used_pct" and p.source_metric_id == "memory_available_bytes"
    assert all(a.op == ">" and 70 <= a.threshold <= 95 for a in p.alerts if a.condition_type == "static")
