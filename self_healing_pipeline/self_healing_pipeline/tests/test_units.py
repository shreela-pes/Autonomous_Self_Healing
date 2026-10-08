import numpy as np

from pipeline.analysis import features as F
from pipeline.analysis.rca import _score, Check
from pipeline.llm.explainer import Explainer
from pipeline.recommendation import playbooks as P


def test_shape_classifier():
    step = np.array([57, 57.2, 56.8, 57, 57.1, 57, 57.3, 57, 57.1, 71])
    ramp = np.array([57, 57.2, 56.8, 58, 60, 61.6, 63.3, 65, 66.4, 68.2])
    flat = np.array([57, 57.2, 56.8, 57, 57.1, 57, 57.3, 57, 57.1, 57.2])
    assert F.classify_shape(step)["shape"] == "step"
    assert F.classify_shape(ramp)["shape"] == "linear_up"
    assert F.classify_shape(flat)["shape"] == "flat"


def test_hourly_baseline_learns_and_ignores_gaps():
    b = None
    for _ in range(4):
        v = np.array([10.0] * 24)
        v[3] = np.nan
        b = F.update_hourly_baseline(b, v, 0.25)
    assert b["n"] == 4 and abs(b["mean"][0] - 10) < 1e-6 and b["mean"][3] is None


def test_missing_evidence_counts_against_a_hypothesis():
    full = [Check("a", True, 3), Check("b", True, 2)]
    partial = [Check("a", True, 3), Check("b", None, 2), Check("c", None, 3)]
    assert _score(full) == 1.0 and _score(partial) < 0.7
    assert _score([Check("req", False, 0, required=True), Check("a", True, 3)]) == 0.0


def _pb(provider):
    inst = {"AWS": "t3.small", "Azure": "Standard_B2s", "GCP": "e2-small"}[provider]
    return P.PB(provider, "res-1", "vm-1", "vm", region="r", zone="z", rg="rg", instance_type=inst,
                facts={"cpu_pct": {"max": 95, "avg": 20}, "memory_used_pct": {"avg": 80, "slope_7d": 1.6},
                       "disk_used_pct": {"avg": 80, "slope_7d": 1.4, "max": 90},
                       "network_in_bytes": {"ratio_max": 6}, "network_out_bytes": {"ratio_max": 5}})


def test_every_root_cause_has_a_safe_human_only_playbook_for_every_provider():
    from pipeline.analysis.rca import ROOT_CAUSE_LABELS
    for rc in ROOT_CAUSE_LABELS:
        for prov in ("AWS", "Azure", "GCP"):
            body = P.build_recommendation_body(rc, _pb(prov))
            assert body["actions"] and body["do_not"] and body["verify"]
            for a in body["actions"]:
                assert a["automated"] is False and a["requires_approval"] is True


def test_destructive_commands_are_rejected():
    bad = [{"automated": False, "requires_approval": True,
            "commands": [{"command": "aws ec2 terminate-instances --instance-ids i-1"}]}]
    try:
        P.validate_actions(bad)
        assert False, "should have raised"
    except ValueError:
        pass


def test_priority_rules():
    assert P.decide_priority("MEMORY_LEAK", {"CRIT", "WARN"}, False)[0] == "P1"
    assert P.decide_priority("MEMORY_LEAK", {"WARN"}, False)[0] == "P2"
    assert P.decide_priority("TRANSIENT_SPIKE", {"CRIT"}, True)[0] == "P3"
    assert P.decide_priority("ALERT_FLAPPING", {"WARN"}, False)[0] == "P3"
    assert P.decide_priority("NETWORK_TRAFFIC_LOSS", {"WARN"}, False)[0] == "P1"


DECISION = {
    "resource_name": "vm-1", "provider": "AWS", "priority": "P1", "root_cause_label": "Memory leak", "confidence": 0.9,
    "summary": "Memory grew 1.6 points/day.", "alerts": [{"metric": "memory_used_pct", "severity": "CRIT", "fired_at": "2026-09-01 10:00"}],
    "all_resolved": False, "evidence": ["memory grew 1.6 points/day over the last 7 days"], "counter_evidence": [],
    "alternatives": [], "actions": [{"title": "Schedule a controlled restart", "phase": "now"}],
    "do_not": ["Do not add CPU."], "verify": "Memory returns to its previous level.", "correlation_summary": "",
}
GOOD = {"summary": "Memory keeps growing about 1.6 points per day.", "why_this_cause": "It rises in a straight line.",
        "what_to_do": "Schedule a controlled restart.", "what_to_watch": "Memory should return to its previous level.",
        "confidence_note": "Confidence is 90%."}


class Stub:
    """Returns the queued outputs one per call (the last one repeats)."""
    def __init__(self, *outs, exc=None):
        self.outs, self.exc, self.calls, self.prompts = list(outs), exc, 0, []

    def generate(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.outs[min(self.calls - 1, len(self.outs) - 1)]


def test_explainer_accepts_faithful_llm_text_and_falls_back_otherwise():
    assert Explainer(Stub(GOOD)).explain(DECISION)["source"] == "llm"
    assert Explainer(Stub(None)).explain(DECISION)["source"] == "template"
    assert Explainer(Stub(exc=RuntimeError("down"))).explain(DECISION)["source"] == "template"
    assert Explainer(None, use_llm=False).explain(DECISION)["source"] == "template"
    assert Explainer.template(DECISION)["what_to_do"].startswith("Recommended steps for a human")
    everything_bad = {k: "Run aws ec2 stop-instances --instance-ids i-1" for k in GOOD}
    assert Explainer(Stub(everything_bad), max_retries=0).explain(DECISION)["source"] == "template"


def test_plain_cloud_names_are_not_mistaken_for_commands():
    """Regression: 'this AWS instance' used to be rejected as a command, discarding almost every LLM answer."""
    prose = {**GOOD, "summary": "This AWS instance keeps growing memory about 1.6 points per day.",
             "what_to_do": "Schedule a controlled restart of the service on the AWS instance."}
    r = Explainer(Stub(prose)).explain(DECISION)
    assert r["source"] == "llm" and "AWS instance" in r["sections"]["summary"]
    for cmd in ("aws ec2 stop-instances --instance-ids i-1", "sudo systemctl restart app",
                "az vm resize -g rg -n vm", "gcloud compute instances stop x", "use `free -m`"):
        assert Explainer(Stub({**GOOD, "what_to_do": cmd}), max_retries=0).explain(DECISION)["source"] != "llm"


def test_one_bad_section_does_not_discard_the_rest():
    bad = {**GOOD, "summary": "Memory grew 47 points per day."}       # 47 is not in the decision
    r = Explainer(Stub(bad), max_retries=0).explain(DECISION)
    assert r["source"] == "llm+template"
    assert r["sections"]["why_this_cause"] == GOOD["why_this_cause"]           # LLM text kept
    assert r["sections"]["summary"] == Explainer.template(DECISION)["summary"]  # template used only where needed


def test_rejected_sections_are_retried_with_feedback():
    bad = {**GOOD, "summary": "Memory grew 47 points per day."}
    stub = Stub(bad, GOOD)
    r = Explainer(stub).explain(DECISION)
    assert stub.calls == 2 and r["source"] == "llm" and r["sections"]["summary"] == GOOD["summary"]
    assert "numbers not in the decision" in stub.prompts[1] and "summary" in stub.prompts[1]
