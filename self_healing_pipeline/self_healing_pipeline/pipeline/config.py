"""Central configuration — all tuneable values live here."""
import os
from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI        = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME    = os.getenv("MONGO_DB_NAME", "symthetic_data")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "distinct logs")

RESOURCE_PROFILES_COLLECTION = "resource_profiles"
PROJECT_SNAPSHOTS_COLLECTION = "project_snapshots"
INCIDENTS_COLLECTION         = "incidents"
PATTERNS_COLLECTION          = "alert_patterns"
RECOMMENDATIONS_COLLECTION   = "recommendations"
# every collection the pipeline writes (source logs are never touched) — used by `--reset`
DERIVED_COLLECTIONS = [
    RESOURCE_PROFILES_COLLECTION, PROJECT_SNAPSHOTS_COLLECTION, INCIDENTS_COLLECTION,
    PATTERNS_COLLECTION, RECOMMENDATIONS_COLLECTION,
]

# ── Ollama (LLM is used ONLY to explain a decision that was already made) ─────
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_TIMEOUT     = int(os.getenv("OLLAMA_TIMEOUT", "180"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
USE_LLM            = _flag("USE_LLM", True)

# ── Pipeline ───────────────────────────────────────────────────────────────────
BATCH_SIZE                 = int(os.getenv("BATCH_SIZE", "500"))
HISTORY_DAYS               = 90        # daily history retained per metric (>= 60 needed for weekday seasonality + trend)
ANOMALY_ZSCORE_THRESHOLD   = 3.0       # (robust) z-score above which a value is flagged anomalous
TREND_HOURS_TO_BREACH_WARN = 24        # only used when PREDICTIVE_ALERTS_ENABLED

# This is a REAL-TIME REACTION pipeline, not a prediction pipeline:
#   * a recommendation is produced only for a log that carries a fired source alert;
#   * statistics / ML / correlation enrich and explain the alert, they never create one.
REQUIRE_SOURCE_ALERT       = _flag("REQUIRE_SOURCE_ALERT", True)
PREDICTIVE_ALERTS_ENABLED  = _flag("PREDICTIVE_ALERTS_ENABLED", False)

# ── Seasonal baseline (learned from HEALTHY days only) ─────────────────────────
BASELINE_ALPHA             = 0.25      # EWMA weight of a new healthy day in the per-weekday hourly baseline
BASELINE_MIN_SAMPLES       = 2         # healthy same-weekday days needed before the baseline is trusted
SEASONAL_MIN_SAMPLES       = 4         # same-weekday daily points needed for the daily z-score baseline

# ── Incident grouping (event time, not wall-clock time) ────────────────────────
INCIDENT_ANY_METRIC_GAP_HOURS   = 6    # an alert on any metric within this gap joins the resource's incident
INCIDENT_SAME_METRIC_GAP_HOURS  = 72   # a repeat of the same metric's alert within this gap joins it too
CROSS_RESOURCE_WINDOW_HOURS     = 6    # peer incidents starting within this window can be causally related
RECURRENCE_MIN_EPISODES         = 3    # same metric + same weekday/hour this many times => scheduled load
RECURRENCE_HOUR_TOLERANCE       = 2
FLAPPING_MIN_EPISODES           = 3    # same alert rule fired this many times within FLAPPING_WINDOW_HOURS
FLAPPING_WINDOW_HOURS           = 24
TRANSIENT_MAX_HOURS             = 2.5  # violating hours; a self-resolved episode this short with nothing else off is "transient"

# ── Priority ───────────────────────────────────────────────────────────────────
# (kept for reference; priority itself is decided in recommendation/playbooks.py)
DEDUP_WINDOW_HOURS = {"P1": 6, "P2": 12, "P3": 24}

SUPPORTED_CATEGORIES = {"Compute", "Storage"}

# The metric families this deployment cares about (as requested).  Alert-bearing logs for
# other metrics are still processed, but the use-case playbooks are built around these.
REQUESTED_METRIC_KEYWORDS = [
    "cpu utilization", "cpu_utilization", "cpu usage", "cpu percent",
    "memory utilization", "memory usage", "memory percent", "memory_used",
    "cpu credit balance", "cpu_credit_balance", "burst credit",
    "cpu credits remaining", "credits remaining",
    "network in", "network_in", "network ingress",
    "network out", "network_out", "network egress",
    "disk usage", "disk utilization", "disk used",
    "disk free", "free disk space",
]

# Canonical metric name -> loose phrasings (used to recognise a metric mentioned in free text)
METRIC_ALIASES = {
    "cpu_pct":              ["cpu utilization", "cpu_utilization", "cpu usage", "cpu percent"],
    "memory_used_pct":      ["memory utilization", "memory usage", "memory percent", "memory_used"],
    "cpu_credit_balance":   ["cpu credit balance", "cpu_credit_balance", "burst credit",
                             "cpu credits remaining", "credits remaining"],
    "network_in_bytes":     ["network in", "network_in", "network ingress"],
    "network_out_bytes":    ["network out", "network_out", "network egress"],
    "disk_used_pct":        ["disk usage", "disk utilization", "disk used", "disk free", "free disk space"],
}

# ── Resource type → actual monitoring platform ──────────────────────────────────
RESOURCE_TYPE_TO_MONITORING = {
    # AWS
    "EC2":              "AWS CloudWatch",
    "Lambda":           "AWS CloudWatch",
    "EBS":              "AWS CloudWatch",
    "EFS":              "AWS CloudWatch",
    "S3":               "AWS CloudWatch",
    # Azure
    "Virtual_Machines": "Azure Monitor",
    "Accounts":         "Azure Monitor",
    "Storage_Disks":    "Azure Monitor",
    "Recovery_Services":"Azure Monitor",
    # GCP
    "Compute_Engine":   "GCP Cloud Monitoring",
    "Bucket":           "GCP Cloud Monitoring",
    "File_Storage":     "GCP Cloud Monitoring",
    # OCI
    "Compute":          "OCI Monitoring",
}

RESOURCE_TYPE_TO_PROVIDER = {
    "EC2": "AWS", "Lambda": "AWS", "EBS": "AWS", "EFS": "AWS", "S3": "AWS",
    "Virtual_Machines": "Azure", "Accounts": "Azure", "Storage_Disks": "Azure", "Recovery_Services": "Azure",
    "Compute_Engine": "GCP", "Bucket": "GCP", "File_Storage": "GCP",
    "Compute": "OCI",
}
