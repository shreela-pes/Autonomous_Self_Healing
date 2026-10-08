"""Trimmed copies of REAL log documents (no `alerts` field, other categories, deprecated metrics) must not break the pipeline."""
import json
import os

import mongomock
from bson import json_util

from pipeline.config import MONGO_DB_NAME
from pipeline.ingestion.normalizer import parse_document
from pipeline.recommendation.engine import RecommendationEngine

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "real_sample_logs.json")


def _docs():
    return [json_util.loads(json.dumps(d)) for d in json.load(open(FIX))]


def test_real_documents_parse_without_alerts():
    vm, st = [parse_document(d) for d in _docs()]
    assert vm.resource_type == "Virtual_Machines" and vm.alerts == [] and vm.config["vm_size"] == "Standard_B1ls"
    assert len(vm.points) == 24 and st.resource_type == "Accounts" and st.alerts == []


def test_legacy_documents_produce_no_recommendation_and_no_crash():
    db = mongomock.MongoClient(tz_aware=True)[MONGO_DB_NAME]
    eng = RecommendationEngine(db, use_llm=False)
    out = eng.process_batch([parse_document(d) for d in _docs()])
    assert out == [] and db["recommendations"].count_documents({}) == 0
    assert db["resource_profiles"].count_documents({}) == 2
