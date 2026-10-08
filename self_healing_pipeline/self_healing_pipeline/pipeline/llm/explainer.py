"""
Explainer -- the LLM's ONLY job: put an already-made decision into plain language.

Decision-making (root cause, confidence, priority, actions, do-not-do list) is done by the
deterministic RCA + playbook layers.  The explainer receives that finished decision and writes a
short narrative for the on-call engineer.  Guard rails:

  * the LLM output is stored ONLY under `explanation`; it can never change any other field;
  * numbers in the narrative must trace back to numbers present in the decision (tolerance for
    rounding) - otherwise the narrative is rejected;
  * commands / CLI snippets in the narrative are rejected (commands come from playbooks only);
  * on any failure (Ollama down, bad JSON, rejected content) the deterministic template
    explanation is used, so the pipeline works identically with or without an LLM.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_SECTIONS = ("summary", "why_this_cause", "what_to_do", "what_to_watch", "confidence_note")
_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")
# Real CLI syntax only.  The old pattern matched the plain word "AWS " in ordinary prose
# ("this AWS instance ...") and rejected almost every explanation.
_CMD = re.compile(
    r"(\baws (ec2|ssm|autoscaling|cloudwatch|logs|elbv2|cloudtrail|s3|iam)\b"
    r"|\baz (vm|vmss|monitor|network|disk|resource|account)\b"
    r"|\bgcloud (compute|logging|monitoring|config)\b"
    r"|\bsudo \w|\bkubectl \w|\bsystemctl \w|\brm -\w|\blogrotate -|\bjournalctl -"
    r"|(?<!\w)--[a-z][a-z-]{2,}|`|```)")


def _nums(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _allowed_numbers(decision: dict) -> list[float]:
    nums = _nums(json.dumps(decision, default=str))
    # a 0-1 confidence may legitimately be quoted as a percentage
    nums += [round(n * 100) for n in nums if 0 < n <= 1]
    conf = decision.get("confidence")
    if isinstance(conf, (int, float)):
        nums.append(round(conf * 100))
    return nums


def _number_ok(n: float, allowed: list[float]) -> bool:
    if n <= 10 and float(n).is_integer():          # list numbering / small counts
        return True
    return any(abs(n - a) <= max(0.06 * abs(a), 0.51) for a in allowed)


class Explainer:
    def __init__(self, llm_client=None, use_llm: bool = True, max_retries: int = 1):
        self.llm = llm_client
        self.use_llm = bool(use_llm and llm_client is not None)
        self.max_retries = max_retries

    # ── public ────────────────────────────────────────────────────────────────
    def explain(self, decision: dict) -> dict:
        """
        decision -> {"sections": {...}, "source": "llm" | "llm+template" | "template", "note": str}

        Each of the five sections is validated on its own.  A rejected section is asked for again once
        (with the reason as feedback); whatever is still invalid is filled from the deterministic template,
        so one stray number no longer throws away an otherwise good explanation.
        """
        template = self.template(decision)
        if not self.use_llm:
            return {"sections": template, "source": "template", "note": "LLM disabled"}

        accepted: dict = {}
        problems: dict = {}
        for attempt in range(1 + self.max_retries):
            feedback = _feedback(problems) if attempt else ""
            try:
                raw = self.llm.generate(self._prompt(decision, feedback))
            except Exception as exc:                          # network / timeout
                logger.warning("LLM explanation failed (%s) - using template", exc)
                if not accepted:
                    return {"sections": template, "source": "template", "note": f"LLM error: {exc}"}
                break
            ok, problems = self._validate_sections(raw, decision, only=[k for k in _SECTIONS if k not in accepted])
            accepted.update(ok)
            if len(accepted) == len(_SECTIONS):
                break

        if not accepted:
            why = "; ".join(f"{k}: {v}" for k, v in problems.items())
            logger.info("LLM explanation rejected (%s) - using template", why)
            return {"sections": template, "source": "template", "note": f"LLM output rejected: {why}"}
        sections = {k: accepted.get(k, template[k]) for k in _SECTIONS}
        if len(accepted) == len(_SECTIONS):
            return {"sections": sections, "source": "llm", "note": "validated against the decision"}
        replaced = [k for k in _SECTIONS if k not in accepted]
        logger.info("LLM explanation partly accepted; template used for %s (%s)", replaced,
                    "; ".join(f"{k}: {v}" for k, v in problems.items()))
        return {"sections": sections, "source": "llm+template",
                "note": "template used for: " + ", ".join(replaced)}

    # ── template (deterministic) ───────────────────────────────────────────────
    @staticmethod
    def template(d: dict) -> dict:
        alerts = d.get("alerts") or []
        metrics = ", ".join(sorted({a["metric"] for a in alerts})) or "the monitored metrics"
        first = alerts[0]["fired_at"] if alerts else None
        n = len(alerts)
        state = "already resolved" if d.get("all_resolved") else "still active"
        summary = (f"{d['resource_name']} raised {n} alert(s) on {metrics}"
                   + (f" starting {first}" if first else "") + f" ({state}). "
                   f"Diagnosis: {d['root_cause_label']} - priority {d['priority']}. {d.get('summary', '')}").strip()
        ev = d.get("evidence") or []
        counter = d.get("counter_evidence") or []
        why = "This cause was chosen because: " + "; ".join(ev[:4]) + "." if ev else "The evidence for this cause is limited."
        if counter:
            why += " Points that do not fit perfectly: " + "; ".join(counter[:2]) + "."
        alts = d.get("alternatives") or []
        if alts:
            why += " Other explanations were considered and ranked lower: " + " | ".join(a.split(" - argued")[0] for a in alts[:2]) + "."
        corr = d.get("correlation_summary")
        if corr:
            why += " " + corr
        steps = [a["title"] for a in d.get("actions", []) if a.get("phase") in ("now", "fix")][:4]
        what_to_do = ("Recommended steps for a human to review and approve (nothing is executed automatically): "
                      + "; ".join(f"{i + 1}) {t}" for i, t in enumerate(steps)) + ".") if steps else "No corrective step is needed."
        dn = d.get("do_not") or []
        if dn:
            what_to_do += " Avoid: " + " ".join(dn[:2])
        watch = d.get("verify") or ""
        conf = d.get("confidence")
        conf_note = (f"Confidence {conf:.0%}: it comes from how many of the checks for this cause passed and how far ahead of "
                     "the runner-up it is (not from a language model).") if conf is not None else ""
        return {"summary": summary, "why_this_cause": why, "what_to_do": what_to_do,
                "what_to_watch": watch, "confidence_note": conf_note}

    # ── LLM path ─────────────────────────────────────────────────────────────
    @staticmethod
    def _prompt(d: dict, feedback: str = "") -> str:
        slim = {
            "resource": d["resource_name"], "cloud": d.get("provider"), "priority": d["priority"],
            "diagnosis": d["root_cause_label"], "confidence_percent": round((d.get("confidence") or 0) * 100),
            "alerts": [f"{a['metric']} {a['severity']} at {a['fired_at']}" for a in (d.get("alerts") or [])[:6]],
            "evidence": d.get("evidence", [])[:6], "does_not_fit": d.get("counter_evidence", [])[:3],
            "ruled_out": [x.split(" - argued")[0] for x in d.get("alternatives", [])[:2]],
            "recommended_steps": [a["title"] for a in d.get("actions", [])][:6],
            "avoid": d.get("do_not", [])[:3], "verify_with": d.get("verify"),
            "related": d.get("correlation_summary"),
        }
        nums = sorted({n for n in _nums(json.dumps(slim, default=str))})[:60]
        return (
            "You are writing the explanation section of an incident recommendation for an on-call cloud engineer.\n"
            "A rules engine has ALREADY decided the diagnosis, priority and steps below. Your job is ONLY to explain them clearly.\n"
            "STRICT RULES:\n"
            "- Do not propose a different cause, extra steps, or different priorities.\n"
            "- Numbers: copy them exactly as written in the DECISION. NEVER calculate, convert, round or derive a number "
            "(no durations, no differences, no percentages you worked out). If a number is not in the DECISION, describe it in words "
            "(for example 'several hours') without digits.\n"
            "- Do not write shell or CLI commands, code, or backticks. Naming the cloud (AWS, Azure, GCP) in a sentence is fine.\n"
            "- Plain English, each field at most 3 sentences.\n"
            "- Nothing is executed automatically; a human approves every step.\n"
            'Return ONLY JSON with exactly these string keys: "summary", "why_this_cause", "what_to_do", "what_to_watch", "confidence_note".\n\n'
            "NUMBERS YOU MAY USE: " + ", ".join(f"{n:g}" for n in nums) + "\n\n"
            "DECISION:\n" + json.dumps(slim, indent=1, default=str)
            + (("\n\nYOUR PREVIOUS ANSWER WAS PARTLY REJECTED - fix only these fields and return all five keys again:\n" + feedback)
               if feedback else "")
        )

    @staticmethod
    def _validate_sections(raw, decision, only=None):
        """-> (accepted {section: text}, problems {section: reason}) - each section judged independently."""
        keys = list(only) if only is not None else list(_SECTIONS)
        if not isinstance(raw, dict):
            return {}, {k: "no JSON object returned" for k in keys}
        allowed = _allowed_numbers(decision)
        ok, bad = {}, {}
        for k in keys:
            v = raw.get(k)
            if not isinstance(v, str) or not v.strip():
                bad[k] = "missing or empty"
            elif len(v) > 1200:
                bad[k] = "too long"
            elif _CMD.search(v):
                bad[k] = "contains a command / code (write plain prose)"
            else:
                wrong = [n for n in _nums(v) if not _number_ok(n, allowed)]
                if wrong:
                    bad[k] = "numbers not in the decision: " + ", ".join(f"{n:g}" for n in wrong[:3])
                else:
                    ok[k] = v.strip()
        return ok, bad


def _feedback(problems: dict) -> str:
    return "\n".join(f'- "{k}": {why}' for k, why in problems.items())
