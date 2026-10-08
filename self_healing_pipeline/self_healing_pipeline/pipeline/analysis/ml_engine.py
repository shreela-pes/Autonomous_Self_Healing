"""
HierarchicalMLEngine — three-level Isolation Forest anomaly detection.

Level 1 (config_group) — PRIMARY BASELINE
  Group: resources sharing the same configuration fingerprint.
  e.g.  Lambda::python3.11::512MB::x86_64
        EC2::t3.nano
        AzureVM::Standard_B2s
  Answers: "How do resources with this exact configuration normally behave?"
  This is the strongest baseline when enough resources of the same config exist.

Level 2 (per_resource) — INDIVIDUAL BASELINE
  Trains on this single resource's own observation history.
  Answers: "Has this specific resource deviated from its own past?"
  Requires RESOURCE_MIN_SAMPLES observations before the model activates.

Level 3 (global_type) — FALLBACK
  All resources of the same type (e.g. all Lambdas).
  Less precise because different configs have different natural behaviours.
  Used only when neither Level 1 nor Level 2 has enough data yet.

For inference, the finest available level is used.
Every update() call feeds all three levels simultaneously.

Feature vectors use DEVIATION-BASED features only (pct_deviation, robust z-score,
normalised slope, worst hourly residual vs the seasonal baseline) so resources within a
config group are comparable even when their raw metric magnitudes differ.  Missing metrics
fill with 0.0.

Role in the pipeline (LIGHT ML, evidence only): the score says whether the day looks unusual
for this resource / config group as a WHOLE (multivariate).  It corroborates or questions a
source alert; it never creates or suppresses one.  One observation per (resource, day) is kept
(re-processing a day overwrites, never duplicates) and every store is capped, so cost stays flat.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# ── Minimum observations before a model is trained ────────────────────────────
_TYPE_MIN_SAMPLES     = 20
_GROUP_MIN_SAMPLES    = 15
_RESOURCE_MIN_SAMPLES = 30

# ── Retrain every N new additions (per model key) ─────────────────────────────
_TYPE_RETRAIN_EVERY     = 10
_GROUP_RETRAIN_EVERY    =  5
_RESOURCE_RETRAIN_EVERY =  5

# ── Sigmoid steepness — controls how fast the score transitions around 0 ──────
_SIGMOID_K = 5.0

# ── Score threshold above which a resource is flagged as anomalous ────────────
ANOMALY_THRESHOLD = 0.65

# ── Canonical metric set per resource type ────────────────────────────────────
# Matches the metric names used in thresholds.py / statistical.py.
# Only metrics that the stat engine actually emits are included.
_METRIC_SETS: dict[str, list[str]] = {
    "Lambda": [
        "lambda_duration_ms", "lambda_error_count",
        "lambda_throttle_count", "lambda_concurrent_exec",
    ],
    "EC2": [
        "cpu_pct", "memory_used_pct", "disk_used_pct", "cpu_credit_balance",
        "network_in_bytes", "network_out_bytes", "disk_write_bytes",
    ],
    "Virtual_Machines": [
        "cpu_pct", "memory_used_pct", "disk_used_pct", "cpu_credit_balance",
        "network_in_bytes", "network_out_bytes", "disk_write_bytes",
    ],
    "Compute_Engine": [
        "cpu_pct", "memory_used_pct", "disk_used_pct", "cpu_scheduler_wait_sec",
        "network_in_bytes", "network_out_bytes", "disk_write_bytes",
    ],
    "Compute": [  # OCI
        "cpu_pct", "memory_used_pct", "load_average",
        "network_in_bytes", "network_out_bytes",
    ],
    "EBS": [
        "volume_queue_length", "burst_balance_pct",
        "volume_read_bytes", "volume_write_bytes",
        "volume_read_ops", "volume_write_ops",
    ],
    "EFS": [
        "percent_io_limit", "burst_credit_balance",
        "client_connections", "total_io_bytes",
    ],
    "S3": [
        "bucket_size_bytes", "bytes_downloaded",
        "bytes_uploaded", "api_request_count",
    ],
    "Accounts": [
        "server_latency_ms", "e2e_latency_ms",
        "availability_pct", "transaction_count",
    ],
    "Storage_Disks": [
        "disk_read_ops_per_sec", "disk_write_ops_per_sec",
        "disk_read_bytes_per_sec", "disk_write_bytes_per_sec",
    ],
    "Bucket": [
        "storage_byte_seconds", "network_in_bytes",
        "network_out_bytes", "api_request_count",
    ],
    "File_Storage": [
        "filesystem_used_bytes",
        "read_throughput_bytes_per_sec", "write_throughput_bytes_per_sec",
        "metadata_iops",
    ],
}


@dataclass
class MLAnomalyResult:
    anomaly_score:        float              # [0, 1]; 1 = maximally anomalous
    is_anomaly:           bool
    level_used:           str               # "per_resource" | "config_group" | "global_type"
    config_group_key:     str               # e.g. "Lambda::python3.11::512MB::x86_64"
    n_training_samples:   int
    top_features: list = field(default_factory=list)  # [(feature_name, value), …] top 3


class HierarchicalMLEngine:
    """
    Maintains three tiers of Isolation Forest models.
    Call update() once per processed document to feed all tiers.
    Call predict() to get the best available anomaly score.
    """

    def __init__(self) -> None:
        # Level 3 — one model per resource type
        self._type_models: dict[str, IsolationForest] = {}
        self._type_data:   dict[str, OrderedDict]     = {}

        # Level 1 — one model per configuration group
        self._group_models: dict[str, IsolationForest] = {}
        self._group_data:   dict[str, OrderedDict]     = {}

        # Level 2 — one model per individual resource
        self._resource_models: dict[str, IsolationForest] = {}
        self._resource_data:   dict[str, OrderedDict]     = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(
        self,
        resource_id:   str,
        resource_type: str,
        config:        dict,
        alert_dicts:   list[dict],
        obs_key:       str = "",
    ) -> None:
        """
        Accumulate one observation across all three model tiers.
        `obs_key` (the observation day) makes the call idempotent per (resource, day).
        """
        features, _ = _build_feature_vector(resource_type, alert_dicts)
        if features is None:
            return

        group_key = config_group_key(resource_type, config)
        k = (resource_id, obs_key)
        for store, key in ((self._type_data, resource_type), (self._group_data, group_key),
                           (self._resource_data, resource_id)):
            od = store.setdefault(key, OrderedDict())
            od[k] = features
            while len(od) > _MAX_OBSERVATIONS:
                od.popitem(last=False)

        self._maybe_retrain(resource_type, group_key, resource_id)

    def predict(
        self,
        resource_id:   str,
        resource_type: str,
        config:        dict,
        alert_dicts:   list[dict],
    ) -> Optional[MLAnomalyResult]:
        """
        Return anomaly result using the finest available model tier.
        Returns None if no model has been trained for this resource yet.
        """
        features, feature_names = _build_feature_vector(resource_type, alert_dicts)
        if features is None:
            return None

        group_key = config_group_key(resource_type, config)
        feat = np.array(features, dtype=float).reshape(1, -1)

        # Level 2 — per resource (most precise, requires 30+ observations)
        if resource_id in self._resource_models:
            return self._make_result(
                self._resource_models[resource_id], feat,
                feature_names, features,
                "per_resource", group_key,
                len(self._resource_data[resource_id]),
            )

        # Level 1 — configuration group
        if group_key in self._group_models:
            return self._make_result(
                self._group_models[group_key], feat,
                feature_names, features,
                "config_group", group_key,
                len(self._group_data[group_key]),
            )

        # Level 3 — global resource type fallback
        if resource_type in self._type_models:
            return self._make_result(
                self._type_models[resource_type], feat,
                feature_names, features,
                "global_type", group_key,
                len(self._type_data[resource_type]),
            )

        return None  # not enough data at any level yet

    def model_counts(self) -> dict:
        """Return how many models exist at each level — useful for health checks."""
        return {
            "global_type":  len(self._type_models),
            "config_group": len(self._group_models),
            "per_resource": len(self._resource_models),
        }

    # ── Internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_result(
        model:         IsolationForest,
        feat:          np.ndarray,
        feature_names: list[str],
        features:      list[float],
        level:         str,
        group_key:     str,
        n_samples:     int,
    ) -> MLAnomalyResult:
        # decision_function: negative = outlier, positive = inlier
        df = float(model.decision_function(feat)[0])
        # Sigmoid: maps large negative df → 1.0 (anomalous), large positive → 0.0 (normal)
        score = float(1.0 / (1.0 + np.exp(_SIGMOID_K * df)))

        # Top contributing features: highest |pct_deviation| or |z-score| values
        # (deviation-based features, so large absolute value = most unusual)
        top = sorted(
            zip(feature_names, features),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:3]

        return MLAnomalyResult(
            anomaly_score      = round(score, 4),
            is_anomaly         = score >= ANOMALY_THRESHOLD,
            level_used         = level,
            config_group_key   = group_key,
            n_training_samples = n_samples,
            top_features       = [(name, round(val, 3)) for name, val in top],
        )

    def _maybe_retrain(
        self,
        resource_type: str,
        group_key:     str,
        resource_id:   str,
    ) -> None:
        # Level 3
        td = list(self._type_data.get(resource_type, {}).values())
        if len(td) >= _TYPE_MIN_SAMPLES and (
            len(td) % _TYPE_RETRAIN_EVERY == 0
            or resource_type not in self._type_models
        ):
            _train(self._type_models, resource_type, td)

        # Level 1
        gd = list(self._group_data.get(group_key, {}).values())
        if len(gd) >= _GROUP_MIN_SAMPLES and (
            len(gd) % _GROUP_RETRAIN_EVERY == 0
            or group_key not in self._group_models
        ):
            _train(self._group_models, group_key, gd)

        # Level 2
        rd = list(self._resource_data.get(resource_id, {}).values())
        if len(rd) >= _RESOURCE_MIN_SAMPLES and (
            len(rd) % _RESOURCE_RETRAIN_EVERY == 0
            or resource_id not in self._resource_models
        ):
            _train(self._resource_models, resource_id, rd)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _safe(v) -> float:
    """Return float; map None and NaN to 0.0 (neutral — no deviation observed)."""
    if v is None:
        return 0.0
    try:
        f = float(v)
        return 0.0 if (f != f) else f  # NaN != NaN
    except (TypeError, ValueError):
        return 0.0


def _train(store: dict, key: str, data: list) -> None:
    X = np.array(data, dtype=float)
    # Belt-and-suspenders: replace any surviving NaN/Inf with 0.0 before fitting
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    model = IsolationForest(
        n_estimators  = 60,
        contamination = 0.05,
        random_state  = 42,
        n_jobs        = 1,
    )
    try:
        model.fit(X)
        store[key] = model
        logger.debug(
            "Trained IsolationForest [%s]: %d samples × %d features",
            key, X.shape[0], X.shape[1],
        )
    except Exception as exc:
        logger.warning("IsolationForest training failed for '%s': %s", key, exc)


def _build_feature_vector(
    resource_type: str,
    alert_dicts:   list[dict],
) -> tuple[Optional[list], list[str]]:
    """
    Build a fixed-size, deviation-based feature vector for the given resource type.

    Three features per canonical metric:
      {metric}__pct_deviation  — % deviation from 30-day mean  (scale-free)
      {metric}__zscore         — z-score from stat engine       (scale-free)
      {metric}__slope_norm     — trend slope / historical_std   (scale-free)

    Missing metrics fill with 0.0 (neutral — no deviation observed).
    Returns (None, []) if the resource type is not in the metric catalogue
    or if every feature is 0 (no useful data).
    """
    metric_set = _METRIC_SETS.get(resource_type)
    if not metric_set:
        return None, []

    by_metric = {r.get("metric"): r for r in alert_dicts}

    features:      list[float] = []
    feature_names: list[str]   = []
    has_data = False

    for metric in metric_set:
        r = by_metric.get(metric) or {}

        pct_dev  = _safe(r.get("pct_deviation"))
        z_score  = _safe(r.get("anomaly_score"))
        slope    = _safe(r.get("trend_slope"))
        hist_std = _safe(r.get("historical_std"))

        slope_norm = (slope / hist_std) if hist_std > 0 else 0.0
        resid = _safe((r.get("features") or {}).get("resid_z_max"))
        # squash heavy tails so one huge value cannot dominate the forest
        pct_dev = float(np.clip(pct_dev, -500, 500))

        features.extend([pct_dev, z_score, slope_norm, resid])
        feature_names.extend([
            f"{metric}__pct_deviation",
            f"{metric}__zscore",
            f"{metric}__slope_norm",
            f"{metric}__resid_max",
        ])

        if pct_dev != 0.0 or z_score != 0.0 or resid != 0.0:
            has_data = True

    return (features, feature_names) if has_data else (None, [])


def config_group_key(resource_type: str, config: dict) -> str:
    """
    Derive the Level-1 group key from resource type + configuration.
    All resources sharing a key are trained together in the config-group model.

    The key captures the dimensions that most determine 'normal behaviour':
      Lambda  → runtime + memory tier + architecture
      EC2     → instance type (encodes vCPUs, memory, family, generation)
      AzureVM → VM size
      GCE     → machine type
      OCI     → shape
      EBS     → volume type (gp2/gp3/io1/io2/st1/sc1)
      EFS     → throughput mode
      Others  → resource type only (becomes identical to Level-3 key)
    """
    if resource_type == "Lambda":
        runtime = config.get("runtime") or "unknown"
        memory  = config.get("memory_mb") or 128
        arch    = config.get("architecture") or "x86_64"
        if isinstance(arch, list):
            arch = arch[0] if arch else "x86_64"
        return f"Lambda::{runtime}::{_quantize_lambda_memory(memory)}MB::{arch}"

    tier = f"::{config.get('_tier')}" if config.get("_tier") else ""   # web / app / db behave differently
    if resource_type == "EC2":
        return f"EC2::{config.get('instance_type') or 'unknown'}{tier}"

    if resource_type == "Virtual_Machines":
        return f"AzureVM::{config.get('vm_size') or 'unknown'}{tier}"

    if resource_type == "Compute_Engine":
        return f"GCE::{(config.get('machine_type') or 'unknown').split('/')[-1]}{tier}"

    if resource_type == "Compute":  # OCI
        return f"OCI::{config.get('shape') or 'unknown'}"

    if resource_type in ("EBS", "Storage_Disks"):
        vt = config.get("volume_type") or config.get("boot_volume_type") or "unknown"
        return f"{resource_type}::{vt}"

    if resource_type in ("EFS", "File_Storage"):
        mode = config.get("throughput_mode") or "bursting"
        return f"{resource_type}::{mode}"

    return resource_type  # Level-1 key collapses to Level-3 key for unsupported types


def _quantize_lambda_memory(memory_mb) -> int:
    """Round Lambda memory to the nearest standard allocation tier."""
    try:
        mb = int(memory_mb)
    except (TypeError, ValueError):
        return 512
    tiers = [128, 256, 512, 1024, 2048, 3008, 4096, 6144, 8192, 10240]
    return min(tiers, key=lambda t: abs(t - mb))
