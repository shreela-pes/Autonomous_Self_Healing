"""
End-to-end: synthetic dataset -> pipeline (in-memory MongoDB) -> recommendations -> scored against ground truth.
Takes about a minute for the full 30-resource fleet.  Skip with:  pytest -m "not slow"
"""
import gzip
import json
import os
from collections import Counter

import mongomock
import pytest
from bson import json_util

import evaluate
from generator.build_dataset import build
from pipeline.config import MONGO_COLLECTION, MONGO_DB_NAME
from pipeline.ingestion.change_stream import ChangeStreamListener
from pipeline.ingestion.normalizer import parse_document
from pipeline.recommendation.engine import RecommendationEngine

pytestmark = pytest.mark.slow


def _run(docs, llm=None):
    client = mongomock.MongoClient(tz_aware=True)
    db = client[MONGO_DB_NAME]
    db[MONGO_COLLECTION].insert_many([json_util.loads(json.dumps(d)) for d in docs])
    eng = RecommendationEngine(db, ollama_client=llm, use_llm=llm is not None)
    ChangeStreamListener(client, eng.process_batch).run_batch()
    return client, db, eng


@pytest.fixture(scope="module")
def full():
    docs, gt, _, _, _, _ = build(days=70)
    client, db, eng = _run(docs)
    return dict(docs=docs, gt=gt, client=client, db=db, eng=eng, ev=evaluate.evaluate(db, gt))


def test_detection_precision_and_gate(full):
    s = full["ev"]["summary"]
    assert s["detection_recall"] == 1.0
    assert s["negatives_correctly_silent"] == s["negatives"] >= 6      # anomaly-without-alert + data-gap cases
    assert s["unexplained_recommendations"] == 0
    assert s["every_rec_has_alert"] and s["every_rec_human_approved_only"]
    # the statistics DID see anomalies that had no alert - and correctly produced nothing for them
    assert full["eng"].stats["anomaly_without_alert"] > 0


def test_root_cause_accuracy_per_use_case_and_provider(full):
    ev = full["ev"]
    assert ev["summary"]["rca_accuracy"] >= 0.95
    for uc in ("UC1", "UC2", "UC3", "UC4", "UC5"):
        a, b = map(int, ev["by_use_case"][uc].split("/"))
        assert b > 0 and a / b >= 0.9, (uc, ev["by_use_case"])
    for prov in ("AWS", "Azure", "GCP"):
        a, b = map(int, ev["by_provider"][prov].split("/"))
        assert a / b >= 0.9


def test_related_alerts_are_grouped_into_one_incident(full):
    recs = list(full["db"]["recommendations"].find({"root_cause.id": "MEMORY_LEAK"}))
    assert len(recs) == 3                                              # one incident per provider, not one per daily alert
    assert all(len(r["alerts"]) >= 4 and r["revision"] >= 1 for r in recs)


def test_cross_resource_attribution(full):
    recs = list(full["db"]["recommendations"].find({"root_cause.id": "UPSTREAM_PROPAGATION"}))
    assert len(recs) == 3
    for r in recs:
        assert r["tier"] == "app" and "web" in r["root_cause"]["root_resource_name"]
        assert r["correlation"]["upstream"] and r["actions"][0]["kind"] == "escalate"


def test_recurrence_is_learned_after_third_occurrence(full):
    recs = sorted(full["db"]["recommendations"].find({"root_cause.id": {"$in": ["CPU_RECURRING_LOAD", "CPU_RUNAWAY_PROCESS"]},
                                                     "resource_name": {"$regex": "analytics-staging-worker-01"}}),
                  key=lambda r: r["first_alert_at"])
    per_res = {}
    for r in recs:
        per_res.setdefault(r["resource_id"], []).append(r["root_cause"]["id"])
    for ids in per_res.values():
        assert len(ids) >= 5 and ids[2:] == ["CPU_RECURRING_LOAD"] * (len(ids) - 2)


def test_recommendations_are_complete_and_never_automated(full):
    for r in full["db"]["recommendations"].find({}):
        assert r["automated_remediation"] is False and r["requires_human_approval"] is True
        assert r["actions"] and r["do_not_do"] and r["verification"] and r["explanation"]["sections"]["summary"]
        assert r["root_cause"]["evidence"] and 0.25 <= r["root_cause"]["confidence"] <= 0.95
        for a in r["actions"]:
            assert a["automated"] is False
            for c in a["commands"]:
                assert not any(w in c["command"] for w in ("terminate-instances", " delete ", "deallocate"))


def test_reprocessing_is_idempotent(full):
    """Re-delivering the last days must not create recommendations or duplicate history."""
    db, eng = full["db"], full["eng"]
    before_recs = db["recommendations"].count_documents({})
    hist_before = {p["_id"]: sum(len(m.get("daily_history", [])) for m in p["metrics"].values())
                   for p in db["resource_profiles"].find({})}
    last = sorted({d["from_date"]["$date"][:10] for d in full["docs"]})[-2:]
    redo = [parse_document(json_util.loads(json.dumps(d))) for d in full["docs"] if d["from_date"]["$date"][:10] in last]
    for day in last:
        eng.process_batch([p for p, d in zip(redo, [d for d in full["docs"] if d["from_date"]["$date"][:10] in last])
                           if d["from_date"]["$date"][:10] == day])
    assert db["recommendations"].count_documents({}) == before_recs
    hist_after = {p["_id"]: sum(len(m.get("daily_history", [])) for m in p["metrics"].values())
                  for p in db["resource_profiles"].find({})}
    assert hist_before == hist_after


def test_history_is_long_enough_for_trend_analysis(full):
    p = full["db"]["resource_profiles"].find_one({"resource_name": {"$regex": "prod-web-01"}})
    assert all(len(m["daily_history"]) >= 60 for m in p["metrics"].values())
    assert all(len(m["hourly_baseline"]) == 7 for m in p["metrics"].values())      # weekday seasonality learned
    assert p["tags"]["tier"] == "web"


class StubLLM:
    """Pretends to be Ollama: returns faithful prose built from the decision it is shown."""
    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return {"summary": "An alert fired and the analysis found a cause.", "why_this_cause": "The evidence in the analysis supports it.",
                "what_to_do": "Review the recommended steps and approve them.", "what_to_watch": "Watch the same metrics recover.",
                "confidence_note": "Confidence comes from the checks that passed."}


def test_llm_only_explains_and_never_changes_the_decision():
    docs, _, _, _, _, _ = build(days=70, providers=("AWS",), projects=("p1",))
    _, db_a, eng_a = _run(docs, llm=None)
    stub = StubLLM()
    _, db_b, eng_b = _run(docs, llm=stub)
    assert stub.calls > 0 and eng_b.stats["llm_explanations"] > 0
    key = lambda r: (r["resource_name"], str(r["first_alert_at"]))
    a = {key(r): r for r in db_a["recommendations"].find({})}
    b = {key(r): r for r in db_b["recommendations"].find({})}
    assert a.keys() == b.keys()
    for k in a:
        for field in ("priority", "status", "actions", "do_not_do", "verification"):
            assert a[k][field] == b[k][field]
        assert a[k]["root_cause"]["id"] == b[k]["root_cause"]["id"]
        assert a[k]["root_cause"]["confidence"] == b[k]["root_cause"]["confidence"]
        assert a[k]["explanation"]["source"] == "template" and b[k]["explanation"]["source"] in ("llm", "llm+template", "template")
