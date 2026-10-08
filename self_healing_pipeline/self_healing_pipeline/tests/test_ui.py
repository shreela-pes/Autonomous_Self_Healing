"""UI smoke tests: run the Streamlit app headlessly against an in-memory MongoDB filled by the pipeline."""
import json
import os

import mongomock
import pymongo
import pytest
from bson import json_util

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from generator.build_dataset import build  # noqa: E402
from pipeline.config import MONGO_COLLECTION, MONGO_DB_NAME  # noqa: E402
from pipeline.ingestion.change_stream import ChangeStreamListener  # noqa: E402
from pipeline.recommendation.engine import RecommendationEngine  # noqa: E402

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "app.py")


@pytest.fixture(scope="module")
def client(monkeypatch_module):
    docs, _, _, _, _, _ = build(days=70, providers=("AWS", "Azure"), projects=("p1",))
    c = mongomock.MongoClient(tz_aware=True)
    c[MONGO_DB_NAME][MONGO_COLLECTION].insert_many([json_util.loads(json.dumps(d)) for d in docs])
    eng = RecommendationEngine(c[MONGO_DB_NAME], use_llm=False)
    ChangeStreamListener(c, eng.process_batch).run_batch()
    monkeypatch_module.setattr(pymongo, "MongoClient", lambda *a, **k: c)
    return c


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _run(page=None, **state):
    at = AppTest.from_file(APP, default_timeout=90)
    at.session_state["nav"] = page or "Overview"
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_overview_renders_kpis_and_table(client):
    at = _run("Overview")
    assert at.header[0].value == "Overview"
    assert len(at.metric) == 5 and int(at.metric[0].value) >= 10
    assert at.dataframe                                              # incident table


def test_incident_detail_renders_every_tab(client):
    at = _run("Incident detail")
    assert at.header[0].value == "Incident detail"
    assert len(at.tabs) == 5
    assert any("Recommendations for a human" in w.value or "human to review" in w.value for w in at.warning)


def test_every_incident_page_renders_without_error(client):
    ids = [r["_id"] for r in client[MONGO_DB_NAME]["recommendations"].find({}, {"_id": 1})]
    assert len(ids) >= 10
    n_code = 0
    for iid in ids:
        at = _run("Incident detail", incident_id=iid)
        n_code += len(at.code)
    assert n_code > 0                                               # suggested commands are rendered as code blocks


def test_resource_explorer_dictionary_pipeline_pages(client):
    _run("Resource explorer")
    _run("Pipeline")
    at = _run("Data dictionary")
    assert any("Source log document" in m.value for m in at.markdown)


def test_evaluation_page_runs(client):
    at = _run("Evaluation")
    assert at.button
