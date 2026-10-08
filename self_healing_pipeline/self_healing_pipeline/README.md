# Self-Healing Recommendation Pipeline (real-time, alert-gated, human-in-the-loop)

For every cloud resource (AWS EC2, Azure VM, GCP Compute Engine) that raises a **source alert**, the pipeline
answers three questions - *what is really wrong (root cause), what should a human do about it, and why do we
think so* - in real time.  It is **not** a prediction pipeline and it **never remediates automatically**.

```
 logs (1 doc = 1 resource x 1 metric x 1 day, 24 hourly points, + alerts[] when the cloud fired one)
   |
   |  1 INGEST     canonical metrics for every cloud, per-weekday hourly baselines learned on HEALTHY days,
   |               idempotent 90-day history, source alerts kept as events
   |  2 ENRICH     statistics (seasonality-aware z / hourly residuals / trend / step-vs-ramp shape) + light ML
   |               (Isolation Forest, 3 tiers) - evidence only
   |  3 GATE       only resources whose logs carry a FIRED SOURCE ALERT continue      <- "no alert, no recommendation"
   |  4 INCIDENTS  raw alerts grouped on event time: one problem = one incident = one diagnosis
   |  5 CORRELATE  same resource (alerting vs quiet metrics) + cross-resource (topology from tags: web->app->db,
   |               tier-wide peers, upstream/downstream) + domain rules
   |  6 RCA        evidence-scored hypotheses -> root cause, confidence, "why not the others"
   |  7 PLAYBOOK   root cause -> ordered, HUMAN-EXECUTED actions (+ do-not-do, verification, risk if ignored)
   |  8 EXPLAIN    LLM (optional, Ollama) narrates the finished decision; validated; template fallback
   v  9 PERSIST    one versioned recommendation per incident  (collection `recommendations`)
```

**Where the intelligence lives**

| concern | mechanism | LLM involved? |
|---|---|---|
| Is there something to act on? | source alert in the log (`alerts[]`) | no |
| What is unusual, how, since when? | seasonality-aware statistics + trend/shape analysis | no |
| Is the whole resource behaving unusually? | Isolation Forest (per resource -> per config group -> per type) | no (light ML) |
| Which alerts belong together / where does it start? | incident grouping + tag-based topology correlation | no |
| **Root cause** | weighted evidence checks per hypothesis, ranked, with counter-evidence | **no** |
| **Recommendation** | playbooks (`recommendation/playbooks.py`) | **no** |
| Plain-language explanation | Ollama, validated per section (numbers must exist in the decision, no CLI commands), one retry with feedback, template fills any section still invalid | **yes - explanation only** |

`python main.py --no-llm` gives byte-for-byte the same decisions; only the wording of `explanation` differs (tested).

---------------------------------------------------------------------------------------------------------

## Quick start

```bash
pip install -r requirements.txt                 # (scikit-learn was missing from the original requirements)
cp .env.example .env                            # MONGO_URI, DB / collection names, Ollama settings

python tools/load_dataset.py --drop             # data/synthetic_logs.ndjson.gz -> MongoDB (7,980 docs)
python main.py --reset --no-llm                 # replay history oldest-first in day batches (~1 min in-memory; faster on mongod)
python tools/report.py                          # one line per recommendation
python tools/report.py --resource db-01 --detail
python tools/evaluate.py                        # score against data/ground_truth.json
```

With Ollama running (`ollama pull qwen3:8b`) just drop `--no-llm`.

## UI (Streamlit)

```bash
python main.py --ui                       # http://localhost:8501, reads MONGO_DB_NAME from .env
python main.py --ui --db my_output_db     # UI-only run, pointed at a specific output database
python main.py --reset --no-llm --run-ui  # run the pipeline, then open the UI
python main.py --reset --db my_output_db --run-ui  # run + UI, all against my_output_db
```

`--db` overrides `MONGO_DB_NAME` from `.env` for that process only - it applies to both the pipeline
run (where recommendations are written) and `--ui` (where they are read from), and to nothing else
(source logs, derived collections, and the UI all live in that one database). The UI's sidebar shows
which database it is reading.

| page | shows |
|---|---|
| Overview | KPIs, filters (priority / cloud / status / use case / root cause / resource), charts, incident table -> click through |
| Incident detail | explanation, evidence and counter-evidence, hypothesis scores, metric charts with alert markers and incident window, alerts, correlation + timeline, actions with commands (read-only vs changes), do-not list, verification, trends, ML score, revisions |
| Resource explorer | any metric of any resource over time with its alerts and incidents |
| Evaluation | runs `tools/evaluate.py` against `data/ground_truth.json` |
| Pipeline | collection counts; buttons to load the dataset and run the pipeline |
| Data dictionary | every field of the logs, alerts and recommendations (`docs/FIELDS.md`) |

The UI only reads MongoDB and shows commands for a human; it never runs anything against your cloud.

Real time: `python tools/replay_stream.py --preload-days 62 --seconds-per-day 10` in one terminal (inserts the
last days one at a time) and `python main.py --mode poll` (or `--mode stream` on a replica set) in another.
Documents are buffered per day and flushed on day change / 5 s idle, so all metrics of a resource for that day are
ingested before it is diagnosed - independent of arrival order.

Tests: `pip install -r requirements-dev.txt && pytest` (~2 min, includes headless UI tests; `pytest -m "not slow"` for the few-second subset).
Everything runs on `mongomock`, no MongoDB needed.

---------------------------------------------------------------------------------------------------------

## The five use cases

Each use case has 2-3 **main metrics per provider** (`generator/fleet.py: USE_CASE_METRICS`); the diagnosis also
looks at the resource's other metrics, alerting or not.

| UC | Use case | Main metrics (AWS / Azure / GCP) | Root causes it separates | Typical recommendation |
|---|---|---|---|---|
| UC1 | **CPU saturation** | cpu, network-in, memory | `CPU_TRAFFIC_SURGE` (load-driven), `CPU_RUNAWAY_PROCESS` (traffic normal, flat plateau), `CPU_RECURRING_LOAD` (same weekday/hour >=3x), `UPSTREAM_PROPAGATION` (cause is on another tier) | add capacity to the tier / find the process / give the job its own capacity / fix the upstream tier first |
| UC2 | **Memory pressure** | memory, cpu | `MEMORY_LEAK` (linear ramp for days), `MEMORY_STEP_CHANGE` (release raised the level) | heap profile + controlled restart window / roll back or right-size |
| UC3 | **Burst-credit exhaustion** | AWS `CPUCreditBalance`+cpu, Azure `CPU Credits Remaining`+cpu, GCP cpu+`scheduler_wait_time` | `CREDIT_EXHAUSTION` | unlimited mode (AWS) / non-burstable size; do **not** reboot |
| UC4 | **Disk capacity** | disk used (Azure: free %), disk-write bytes | `DISK_LOG_GROWTH` (steady), `DISK_SUDDEN_FILL` (step + write burst) | find growth, rotate/archive, extend volume / find the writer *before* extending |
| UC5 | **Network anomaly** | network-in, network-out, cpu | `NETWORK_INGRESS_ANOMALY` (abrupt step, attack-like), `NETWORK_EGRESS_ANOMALY` (out up, in normal), `NETWORK_TRAFFIC_LOSS` (VM alive, traffic gone) | WAF/rate-limit / find destination / check LB-DNS-NSG - **never** stop the "idle" VM |

Cross-cutting: `TRANSIENT_SPIKE` (self-resolved, nothing else deviates -> P3, no action), `ALERT_FLAPPING` (rule hovers at
its threshold -> tune the rule, no capacity change), `UNDETERMINED` (evidence does not single out a cause -> diagnostics + escalate).

Metrics you listed (cpu %, memory %, cpu credit balance / credits remaining, network in/out, disk used/free) are the main
metrics. Two supporting metrics were added because they discriminate causes and are real provider metrics:
`DiskWriteBytes` (sudden fill vs growth) and GCP `scheduler_wait_time` (GCP exposes no credit metric for shared-core VMs).
Verify the latter exists in your GCP tenants.

### Why the pipeline correlates alerts (examples from the dataset)

* **CPU alert on `app-01` + traffic surge on `web-01/web-02` one hour earlier** -> `UPSTREAM_PROPAGATION`; `app-01` is told *not* to resize, the origin tier gets the capacity action.
* **CPU alert with quiet network and flat 97% plateau** -> `CPU_RUNAWAY_PROCESS`; "scaling up" is listed under *do not*.
* **Credit balance alert while CPU looks moderate (20%)** -> that flat line *is* the throttle; recommendation is about credits, not CPU.
* **Same CPU alert every Monday 02:00** -> first two are `CPU_RUNAWAY_PROCESS`; from the 3rd it becomes `CPU_RECURRING_LOAD` (P3, tune the schedule).

Every recommendation stores the alert timeline of the correlated resources, the ranked hypotheses with supporting *and*
contradicting evidence, trend lines, ML score, and `automated_remediation: false`, `requires_human_approval: true`.

---------------------------------------------------------------------------------------------------------

## Synthetic dataset (`data/`)

| item | value |
|---|---|
| documents | **7,980** (114 metric series x 70 days), 24 hourly points each, `2026-07-11 .. 2026-09-18` |
| shape | 3 clouds x 2 projects (`prod`/shop, `staging`/analytics) x 5 VMs (web-01, web-02, app-01, worker-01, db-01) = 30 resources |
| history | 70 days per resource id (requirement: >= 60) |
| schema | **identical top-level keys for AWS, Azure and GCP** (real-sample fields + `alerts[]`); `--aws-native-points` emits CloudWatch-style point keys to exercise the normalizer |
| alerts | 230 documents carry `alerts[]`; 182 alert episodes (Warning + Critical are separate rules, flapping produces repeats, alerts span days with `is_continuation`) |
| ground truth | `ground_truth.json`: 66 incident windows = 17 scenarios per cloud, the weekly batch counted per episode (60 must produce a recommendation, 6 must **not**) |

**Realism.** One latent load per project drives CPU, network, memory and disk-write (so cross-metric correlation is real,
not painted on); diurnal cycle, weekend dip, slow growth trend, AR(1) noise, weekly log-rotation sawtooth on disks, deploy-cycle
sawtooth on memory; burst-credit accounting is physical (1 credit = 1 vCPU-minute; empty balance throttles CPU to the baseline);
web -> app load is lagged 1 h; alerts are *computed from the series* the way cloud rules work (static thresholds; seasonal
"dynamic threshold" bands for network).  A log only contains what was known by the end of its own day (no future resolution times).

**Cases covered** (per provider, 17 scenarios): fleet-wide traffic surge + downstream app CPU, ingress step, egress spike,
traffic loss, memory leak (ends in a restart), memory step-change (rolled back), credit exhaustion (throttled for days, recovers),
2-hour transient spike, flapping alert, runaway process, weekly recurring batch (6 episodes), sudden disk fill (cleaned up),
steady disk growth (**still open, Critical, at the end of the window**), anomaly *without* alert (must be silent), 6-hour monitoring gap (must be silent).

Regenerate / customise: `python -m generator.build_dataset --days 70 --seed 42 --providers AWS Azure GCP --projects p1 p2 --out data`.
Scenarios, timings and parameters are plain data in `generator/fleet.py`; the generator refuses to build if a scenario produces no
alert, a negative case alerts, or an alert is not explained by a scenario.  Details: `docs/DATASET.md`.

---------------------------------------------------------------------------------------------------------

## Validation (`python tools/evaluate.py`, `data/evaluation_result.json`)

| check | result on the shipped dataset |
|---|---|
| incidents detected (recommendation exists) | 60 / 60 |
| root cause correct (incl. cross-resource origin) | 60 / 60 - UC1 36/36, UC2 6/6, UC3 3/3, UC4 6/6, UC5 9/9; AWS/Azure/GCP 20/20 each |
| no-alert anomalies and data gaps stay silent | 6 / 6 (700 resource-days showed statistical anomalies without any source alert -> 0 recommendations) |
| recommendations not explained by an injected incident | 0 |
| same result with seeds 7 and 123, and with AWS-native point format | yes |
| re-delivering already-processed days | no new recommendations, no duplicated history |
| decisions with vs without LLM | identical (LLM touches only `explanation`) |

**Read this honestly:** the ground truth comes from the same author as the generator, so this proves the *plumbing and logic*
(gating, canonicalisation, grouping, correlation, evidence scoring, safety), not accuracy on your production estate.
RCA thresholds (e.g. "leak = >=0.6 points/day, r2 >= 0.7") are sensible defaults tuned on this data; expect to calibrate them
on real incidents.  Run `evaluate.py` on labelled real incidents when you have them.

---------------------------------------------------------------------------------------------------------

## What was analysed in the original pipeline, and what changed

Findings (all fixed unless noted):

1. **Alerts were invented internally** from thresholds/forecasts; logs had no alert concept.  Now the log's `alerts[]` is the trigger; forecasting-based upgrades are off (`PREDICTIVE_ALERTS_ENABLED=false`).
2. **The LLM decided root cause and actions** (with regex guards patching its output).  Now RCA + playbooks decide; the LLM only explains, under validation.
3. **Time windows used wall-clock time**, which breaks replaying history (dedup/cache/expiry).  All logic now uses event time; batch replay is sorted oldest-first.
4. **Baselines**: 30 days, mean/std contaminated by anomalies, no weekday awareness, today's value inside its own baseline.  Now >= 90 days kept, per-weekday hourly baselines learned only from healthy days, robust (median/MAD) z-scores that exclude today.
5. **Azure `extended_summary_details`** sits at the top level of the log but was read from `summary_details` -> NIC/IP-forwarding findings never populated.
6. **Unit bug**: daily min/max/avg were stored raw while values were transformed (GCP CPU ratio vs %).  Now transformed consistently.
7. **Cross-cloud gaps**: Azure memory (available bytes) and disk (free %) had different semantics than AWS/GCP; credits had two names.  `metrics/derive.py` maps them to `memory_used_pct`, `disk_used_pct`, `cpu_credit_balance` (alert thresholds converted too).
8. **ML** trained on one observation per *document* (3-5 duplicates per resource-day); now one per resource-day, capped, cheaper retraining, tier-aware config groups.
9. `scikit-learn` missing from `requirements.txt`; unused `pandas` removed.
10. Not addressed: categories other than Compute/Storage (your samples also show Network, Databases, Container - they are skipped by `SUPPORTED_CATEGORIES`); adding them means new registry rows, thresholds and RCA hypotheses.

Kept: registry, config extractor, feature normalizer, resource/project state managers, ML engine, project-level lag correlation,
domain-rule correlation engine (now fed by incidents), Ollama client.
Removed: `llm/context_builder.py` (LLM-as-decision-maker prompt) and the old engine's guard/rewrite code.

## Repository layout

```
main.py                        entry point (batch | stream | poll, --no-llm, --reset)
pipeline/
  config.py                    all tunables (env-overridable)
  ingestion/                   normalizer (alerts + cross-cloud canonicalisation), day-batched change-stream/poll listener
  metrics/                     registry, thresholds, derive (Azure/GCP -> canonical), config extractor, feature normalizer
  state/                       resource_state (baselines, history, alert events), incident_state (grouping), project_state
  analysis/                    features, statistical, ml_engine, project_correlation, alert_correlation, rca, pattern_store
  recommendation/              engine (orchestration), playbooks (the only place advice is written)
  llm/                         explainer (validated, template fallback), ollama_client
generator/                     fleet.py (data), signals.py, alerts.py, docs.py, build_dataset.py
tools/                         load_dataset, replay_stream, report, evaluate
ui/                            app.py (Streamlit), data.py (queries; no Streamlit imports)
tests/                         unit + generator + end-to-end + real-sample compatibility
data/                          synthetic_logs.ndjson.gz, ground_truth.json, manifest, samples, evaluation + sample report
docs/DATASET.md                schema and scenario reference
docs/FIELDS.md                 every field name: logs, alerts, ground truth, recommendations
```

## Key design decisions (short)

* **Event time everywhere**, day batches: a CPU alert is diagnosed with the same day's network/memory even if those documents arrive later.
* **Incident = grouping unit**: an alert joins the resource's incident if it is unresolved, within 6 h, or the same metric within 72 h (daily-peak leaks are one incident, weekly batches are separate).  Diagnosis is *sticky* (changes only if another cause wins by >= 0.15) and frozen once the incident resolves (post-recovery data is a poor basis).
* **Scoring**: score = weighted share of passed checks; unavailable data counts half against a hypothesis (a VM without network metrics cannot be called a traffic surge); `required` checks rule a cause out.  Confidence = `0.30 + 0.50*score + 0.12*margin` +/- ML agreement, pattern history, learned correlation, missing data - fully itemised in `root_cause.confidence_parts`.
* **Safety**: playbook commands are validated (no terminate/delete/deallocate), all actions carry `automated:false`; read-only diagnostics (`$`) are distinguished from changes (`$!`).
* **Tunables**: `pipeline/config.py` (gap windows, recurrence/flapping/transient thresholds, baseline learning rate, history length).
