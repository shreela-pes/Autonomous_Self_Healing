"""
Fleet definition: providers -> projects -> resources -> scenarios.

Everything the generator needs to know about *what exists* and *what goes wrong*
lives here, as plain data.  Add / remove / retime scenarios by editing this file;
the rest of the generator is generic.

Use-case x provider metric matrix (2-3 MAIN metrics each - see USE_CASE_METRICS):

  UC1  CPU saturation          cpu, network_in, memory
  UC2  Memory pressure         memory, cpu
  UC3  Burst-credit exhaustion cpu_credit_balance (GCP: cpu + scheduler wait), cpu
  UC4  Disk capacity           disk_used, disk_write (+ memory for context)
  UC5  Network anomaly         network_in, network_out, cpu
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

# ── Use cases ────────────────────────────────────────────────────────────────

USE_CASES = {
    "UC1": "CPU saturation & root-cause split (traffic vs runaway process vs scheduled load)",
    "UC2": "Memory pressure (leak vs release step-change)",
    "UC3": "Burstable / shared-core CPU credit exhaustion",
    "UC4": "Disk capacity exhaustion (steady log growth vs sudden fill)",
    "UC5": "Network anomaly (ingress surge, egress spike, traffic loss)",
}

# Semantic metric roles -> the provider-native metric each provider actually exposes.
# (raw names match pipeline/metrics/registry.py so no registry lookup is missed)
NATIVE_METRIC = {
    "AWS": {
        "cpu":         "CPUUtilization",
        "mem":         "mem_used_percent",
        "disk":        "disk_used_percent",
        "disk_write":  "DiskWriteBytes",
        "credit":      "CPUCreditBalance",
        "net_in":      "NetworkIn",
        "net_out":     "NetworkOut",
    },
    "Azure": {
        "cpu":         "Percentage CPU",
        "mem":         "Available Memory Bytes",
        "disk":        "disk/free_percent",
        "disk_write":  "Disk Write Bytes",
        "credit":      "CPU Credits Remaining",
        "net_in":      "Network In Total",
        "net_out":     "Network Out Total",
    },
    "GCP": {
        "cpu":         "compute.googleapis.com/instance/cpu/utilization",
        "mem":         "agent.googleapis.com/memory/percent_used",
        "disk":        "agent.googleapis.com/disk/percent_used",
        "disk_write":  "compute.googleapis.com/instance/disk/write_bytes_count",
        "sched_wait":  "compute.googleapis.com/instance/cpu/scheduler_wait_time",
        "net_in":      "compute.googleapis.com/instance/network/received_bytes_count",
        "net_out":     "compute.googleapis.com/instance/network/sent_bytes_count",
    },
}

# MAIN metrics per (use case, provider): max three each.
USE_CASE_METRICS = {
    "UC1": {"AWS": ["cpu", "net_in", "mem"], "Azure": ["cpu", "net_in", "mem"], "GCP": ["cpu", "net_in", "mem"]},
    "UC2": {"AWS": ["mem", "cpu"],           "Azure": ["mem", "cpu"],           "GCP": ["mem", "cpu"]},
    "UC3": {"AWS": ["credit", "cpu"],        "Azure": ["credit", "cpu"],        "GCP": ["cpu", "sched_wait"]},
    "UC4": {"AWS": ["disk", "disk_write"],   "Azure": ["disk", "disk_write"],   "GCP": ["disk", "disk_write"]},
    "UC5": {"AWS": ["net_in", "net_out", "cpu"], "Azure": ["net_in", "net_out", "cpu"], "GCP": ["net_in", "net_out", "cpu"]},
}

# Metric roles recorded per tier (what the monitoring agent reports for that kind of box)
TIER_ROLES = {
    "web":    ["cpu", "mem", "net_in", "net_out"],
    "app":    ["cpu", "mem", "net_in", "net_out"],
    "worker": ["cpu", "mem", "credit"],          # GCP: sched_wait replaces credit
    "db":     ["cpu", "mem", "disk", "disk_write"],
}

# ── Instance catalogue ───────────────────────────────────────────────────────
# (vcpus, memory_gb, burst_credits_per_hr, burst_max_credits)   burst_* None => fixed
INSTANCE = {
    "AWS": {
        "m5.large":  (2, 8.0, None, None),
        "c5.large":  (2, 4.0, None, None),
        "r5.large":  (2, 16.0, None, None),
        "t3.small":  (2, 2.0, 24, 576),
    },
    "Azure": {
        "Standard_D2s_v5": (2, 8.0, None, None),
        "Standard_D4s_v5": (4, 16.0, None, None),
        "Standard_E2s_v5": (2, 16.0, None, None),
        "Standard_F2s_v2": (2, 4.0, None, None),
        "Standard_B2s":    (2, 4.0, 24, 576),
    },
    "GCP": {
        "e2-standard-2": (2, 8.0, None, None),
        "n2-standard-2": (2, 8.0, None, None),
        "n2-standard-4": (4, 16.0, None, None),
        # shared-core: no public credit metric.  0.5 vCPU sustained of 2 => 25% baseline.
        "e2-small":      (2, 2.0, 30, 720),
    },
}

DISK_GB = {"AWS": 200, "Azure": 256, "GCP": 200}


@dataclass
class ScenarioSpec:
    kind: str                 # key into signals.SCENARIOS
    day: int                  # day index (0 = first day of window)
    hour: int = 0
    params: dict = field(default_factory=dict)
    # ---- ground truth --------------------------------------------------------
    use_case: str = ""
    expected_root_cause: Optional[str] = None      # None => must NOT produce a recommendation
    expects_alert: bool = True
    note: str = ""
    # for cross-resource scenarios: which peer resource key is the real origin
    root_resource_key: Optional[str] = None


@dataclass
class ResourceSpec:
    key: str                  # web-01
    tier: str
    instance_type: str
    scenarios: list = field(default_factory=list)
    lag_hours: int = 0        # app tier reacts to web tier with this lag


@dataclass
class ProjectSpec:
    key: str                  # "p1" | "p2"
    provider: str
    app: str
    env: str
    resources: list = field(default_factory=list)
    day_offset: int = 0       # nudges scenario days per provider so incidents do not all coincide


def _hex(seed: str, n: int) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:n]


def oid(seed: str) -> str:
    return _hex("oid:" + seed, 24)


# ── Per-provider instance sizing ─────────────────────────────────────────────

_TYPES = {
    "AWS": {
        "p1": {"web-01": "m5.large", "web-02": "m5.large", "app-01": "m5.large", "worker-01": "t3.small", "db-01": "r5.large"},
        "p2": {"web-01": "c5.large", "web-02": "c5.large", "app-01": "m5.large", "worker-01": "t3.small", "db-01": "r5.large"},
    },
    "Azure": {
        "p1": {"web-01": "Standard_D2s_v5", "web-02": "Standard_D2s_v5", "app-01": "Standard_D2s_v5", "worker-01": "Standard_B2s", "db-01": "Standard_E2s_v5"},
        "p2": {"web-01": "Standard_F2s_v2", "web-02": "Standard_F2s_v2", "app-01": "Standard_D2s_v5", "worker-01": "Standard_B2s", "db-01": "Standard_D4s_v5"},
    },
    "GCP": {
        "p1": {"web-01": "e2-standard-2", "web-02": "e2-standard-2", "app-01": "n2-standard-2", "worker-01": "e2-small", "db-01": "n2-standard-4"},
        "p2": {"web-01": "e2-standard-2", "web-02": "e2-standard-2", "app-01": "n2-standard-2", "worker-01": "e2-small", "db-01": "n2-standard-4"},
    },
}
_APP = {"p1": ("shop", "prod"), "p2": ("analytics", "staging")}
_PROVIDER_DAY_OFFSET = {"AWS": 0, "Azure": 2, "GCP": -1}


def _p1_scenarios(provider: str) -> dict[str, list[ScenarioSpec]]:
    gcp = provider == "GCP"
    return {
        "web-01": [
            ScenarioSpec("traffic_surge", day=33, hour=12, use_case="UC1",
                         params=dict(factor=2.8, ramp=3, hold=4, decay=3, load_gain=1.0),
                         expected_root_cause="CPU_TRAFFIC_SURGE",
                         note="fleet-wide organic traffic surge (ramp), web-tier"),
            ScenarioSpec("net_ingress_anomaly", day=51, hour=2, use_case="UC5",
                         params=dict(factor=7.0, hold=3, cpu_add=9.0),
                         expected_root_cause="NETWORK_INGRESS_ANOMALY",
                         note="abrupt off-hours ingress step, attack/scan-like, CPU barely moves"),
            ScenarioSpec("anomaly_no_alert", day=60, hour=14, use_case="UC1",
                         params=dict(level=66.0, hold=2),
                         expected_root_cause=None, expects_alert=False,
                         note="CPU blip to ~66% - anomalous vs baseline but BELOW every alert threshold"),
        ],
        "web-02": [
            ScenarioSpec("traffic_surge", day=33, hour=12, use_case="UC1",
                         params=dict(factor=2.6, ramp=3, hold=4, decay=3, load_gain=1.0),
                         expected_root_cause="CPU_TRAFFIC_SURGE",
                         note="same LB-driven surge on the peer web node"),
            ScenarioSpec("cpu_flapping", day=46, hour=9, use_case="UC1",
                         params=dict(hours=10, hi=78.0, lo=69.0),
                         expected_root_cause="ALERT_FLAPPING",
                         note="CPU oscillating around the 75% warning line -> alert fires/resolves repeatedly"),
        ],
        "app-01": [
            ScenarioSpec("downstream_surge", day=33, hour=12, use_case="UC1",
                         params=dict(factor=2.7, ramp=3, hold=4, decay=3, cpu_gain=1.0),
                         expected_root_cause="UPSTREAM_PROPAGATION", root_resource_key="web-01",
                         note="CPU alert on app tier that is purely a consequence of the web-tier surge"),
            ScenarioSpec("memory_leak", day=42, hour=0, use_case="UC2",
                         params=dict(slope_per_day=1.6, restart_day=63, restart_hour=10, gc_cpu=9.0),
                         expected_root_cause="MEMORY_LEAK",
                         note="linear memory growth for ~22 days, ends with a restart"),
        ],
        "worker-01": [
            ScenarioSpec("credit_exhaustion", day=36, hour=0, use_case="UC3",
                         params=dict(days=8, extra_cpu=42.0 if gcp else 24.0),
                         expected_root_cause="CREDIT_EXHAUSTION",
                         note="sustained demand above burst baseline for days -> credits hit zero -> throttled"),
            ScenarioSpec("transient_spike", day=57, hour=11, use_case="UC1",
                         params=dict(level=93.0, hold=2),
                         expected_root_cause="TRANSIENT_SPIKE",
                         note="2-hour CPU spike that self-resolves; nothing else deviates"),
        ],
        "db-01": [
            ScenarioSpec("disk_sudden_fill", day=47, hour=10, use_case="UC4",
                         params=dict(jump=36.0, over_hours=3, cleanup_day=49, cleanup_hour=15, write_mult=6.0),
                         expected_root_cause="DISK_SUDDEN_FILL",
                         note="core-dump / runaway export fills the volume within 3 hours"),
        ],
    }


def _p2_scenarios(provider: str) -> dict[str, list[ScenarioSpec]]:
    return {
        "web-01": [
            ScenarioSpec("net_egress_anomaly", day=44, hour=20, use_case="UC5",
                         params=dict(factor=5.5, hold=12, cpu_add=3.0),
                         expected_root_cause="NETWORK_EGRESS_ANOMALY",
                         note="12h egress spike while ingress and CPU stay normal (bulk copy / exfil-like)"),
        ],
        "web-02": [
            ScenarioSpec("net_traffic_loss", day=55, hour=9, use_case="UC5",
                         params=dict(hold=6, residual=0.03),
                         expected_root_cause="NETWORK_TRAFFIC_LOSS",
                         note="VM stays up but traffic vanishes (LB / DNS / NSG change upstream)"),
        ],
        "app-01": [
            ScenarioSpec("memory_step", day=41, hour=10, use_case="UC2",
                         params=dict(delta=23.0, rollback_day=58, rollback_hour=9),
                         expected_root_cause="MEMORY_STEP_CHANGE",
                         note="release raises steady-state memory by ~23 points; rolled back later"),
            ScenarioSpec("data_gap", day=50, hour=4, use_case="UC1",
                         params=dict(hours=6, roles=["cpu"]),
                         expected_root_cause=None, expects_alert=False,
                         note="monitoring gap (6 missing hourly points) - data-quality case, no alert"),
            ScenarioSpec("cpu_runaway", day=63, hour=6, use_case="UC1",
                         params=dict(level=97.0, hold=9),
                         expected_root_cause="CPU_RUNAWAY_PROCESS",
                         note="flat ~97% CPU with normal traffic and memory"),
        ],
        "worker-01": [
            ScenarioSpec("recurring_batch", day=28, hour=2, use_case="UC1",
                         params=dict(weekday=0, level=93.0, hold=3),
                         expected_root_cause="CPU_RECURRING_LOAD",
                         note="weekly Monday 02:00-05:00 batch job saturates CPU (alert every week)"),
        ],
        "db-01": [
            ScenarioSpec("disk_log_growth", day=40, hour=0, use_case="UC4",
                         params=dict(slope_per_day=1.45, write_mult=1.35),
                         expected_root_cause="DISK_LOG_GROWTH",
                         note="unrotated logs grow ~1.5 pts/day; still open (critical) at end of window"),
        ],
    }


def build_fleet(providers=("AWS", "Azure", "GCP"), projects=("p1", "p2")) -> list[ProjectSpec]:
    fleet = []
    for provider in providers:
        for pk in projects:
            app, env = _APP[pk]
            scen = (_p1_scenarios if pk == "p1" else _p2_scenarios)(provider)
            resources = []
            for rkey, itype in _TYPES[provider][pk].items():
                tier = rkey.split("-")[0]
                rs = ResourceSpec(key=rkey, tier=tier, instance_type=itype,
                                  scenarios=list(scen.get(rkey, [])),
                                  lag_hours=1 if tier == "app" else 0)
                resources.append(rs)
            fleet.append(ProjectSpec(key=pk, provider=provider, app=app, env=env,
                                     resources=resources,
                                     day_offset=_PROVIDER_DAY_OFFSET[provider]))
    return fleet


def roles_for(provider: str, tier: str) -> list[str]:
    roles = list(TIER_ROLES[tier])
    if provider == "GCP" and "credit" in roles:
        roles[roles.index("credit")] = "sched_wait"
    return roles
