"""
CorrelationEngine — cross-resource analysis within a project.

Two resources are considered correlated when:
  1. Both have at least WARN status during the same observation window (same day).
  2. A domain rule matches their resource types and triggered metrics.

Domain rules encode known causal chains in cloud infrastructure.
When a rule matches, the engine:
  - Identifies the probable root-cause resource (the one whose alert came first, or
    the one named in the rule's causal_resource field)
  - Computes a confidence score (base + rule boost + historical boost)
  - Returns a CorrelatedSet describing the event

CorrelatedSet is stored in the project snapshot and passed to the LLM context builder.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class CorrelatedSet:
    rule_name: str
    root_cause_resource_id: str
    root_cause_resource_type: str
    root_cause_category: str
    dependent_resource_ids: list[str]
    triggered_metrics: list[str]
    root_cause_description: str
    do_not_recommend: str
    confidence: float
    causal_order: list[str]           # [root_cause_type, …, dependent_type]
    detected_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "rule_name":               self.rule_name,
            "root_cause_resource_id":  self.root_cause_resource_id,
            "root_cause_resource_type":self.root_cause_resource_type,
            "root_cause_category":     self.root_cause_category,
            "dependent_resource_ids":  self.dependent_resource_ids,
            "triggered_metrics":       self.triggered_metrics,
            "root_cause_description":  self.root_cause_description,
            "do_not_recommend":        self.do_not_recommend,
            "confidence":              self.confidence,
            "causal_order":            self.causal_order,
        }


# ── Domain Rules ───────────────────────────────────────────────────────────────
# Each rule defines:
#   triggers      : list of {resource_type, metrics (any of these suffices)}
#   causal_index  : index into triggers[] that identifies the ROOT CAUSE resource
#   description   : text describing the cross-resource causal chain
#   do_not_recommend: what NOT to do (prevents naive scaling advice)
#   confidence_boost: added to base confidence (0.5) when rule fires

_RULES = [
    {
        "name":             "ebs_io_causes_ec2_cpu_iowait",
        "triggers": [
            {"resource_type": "EBS",   "metrics": ["volume_queue_length", "burst_balance_pct"]},
            {"resource_type": "EC2",   "metrics": ["cpu_iowait_pct", "cpu_pct", "disk_io_time_ms"]},
        ],
        "causal_index":     0,
        "description":      "EBS I/O saturation (high VolumeQueueLength / depleted BurstBalance) is causing CPU I/O wait on the EC2 instance. The compute CPU spike is downstream of the storage bottleneck.",
        "do_not_recommend": "Scaling the EC2 instance type or adding CPU capacity will NOT resolve the CPU pressure while EBS I/O remains saturated. Investigate EBS performance first.",
        "confidence_boost": 0.25,
        "causal_order":     ["EBS", "EC2"],
    },
    {
        "name":             "efs_io_limit_causes_compute_cpu",
        "triggers": [
            {"resource_type": "EFS",   "metrics": ["percent_io_limit", "burst_credit_balance"]},
            {"resource_type": "EC2",   "metrics": ["cpu_pct", "cpu_iowait_pct"]},
        ],
        "causal_index":     0,
        "description":      "EFS has reached its I/O limit (PercentIOLimit high or BurstCreditBalance depleted). Compute instances mounting this filesystem are experiencing blocked I/O, which is showing up as elevated CPU utilization.",
        "do_not_recommend": "Adding EC2 capacity will increase I/O demand on the already-saturated EFS filesystem and worsen the situation. Address EFS throughput first.",
        "confidence_boost": 0.22,
        "causal_order":     ["EFS", "EC2"],
    },
    {
        "name":             "azure_storage_latency_causes_vm_cpu",
        "triggers": [
            {"resource_type": "Accounts",         "metrics": ["server_latency_ms", "e2e_latency_ms", "availability_pct"]},
            {"resource_type": "Virtual_Machines", "metrics": ["cpu_pct", "os_disk_queue_depth"]},
        ],
        "causal_index":     0,
        "description":      "Azure Storage Account latency is elevated. VMs reading from or writing to this storage account are experiencing blocked I/O, which is causing CPU utilization to spike as threads wait.",
        "do_not_recommend": "Resizing the VM SKU will not relieve CPU pressure caused by storage latency. Investigate the storage account's performance tier and region health.",
        "confidence_boost": 0.20,
        "causal_order":     ["Accounts", "Virtual_Machines"],
    },
    {
        "name":             "azure_managed_disk_iops_causes_vm_cpu",
        "triggers": [
            {"resource_type": "Storage_Disks",    "metrics": ["disk_read_ops_per_sec", "disk_write_ops_per_sec"]},
            {"resource_type": "Virtual_Machines", "metrics": ["cpu_pct", "os_disk_queue_depth", "data_disk_queue_depth"]},
        ],
        "causal_index":     0,
        "description":      "Azure Managed Disk I/O operations are anomalously high or approaching provisioned IOPS limits. This is causing OS/data disk queue depth to grow on the VM, indirectly driving CPU pressure.",
        "do_not_recommend": "Do not increase VM CPU size without addressing disk IOPS saturation — the bottleneck is in storage, not compute.",
        "confidence_boost": 0.20,
        "causal_order":     ["Storage_Disks", "Virtual_Machines"],
    },
    {
        "name":             "oci_filesystem_full_causes_compute_pressure",
        "triggers": [
            {"resource_type": "File_Storage", "metrics": ["filesystem_used_bytes", "read_throughput_bytes_per_sec", "metadata_iops"]},
            {"resource_type": "Compute",      "metrics": ["cpu_pct", "load_average"]},
        ],
        "causal_index":     0,
        "description":      "OCI File Storage is near capacity or throughput limits. Compute instances using this filesystem are stalling on writes, which is elevating CPU load average.",
        "do_not_recommend": "Scaling compute shape will not fix the storage capacity/throughput issue. Expand the file system or clean up data first.",
        "confidence_boost": 0.20,
        "causal_order":     ["File_Storage", "Compute"],
    },
    {
        "name":             "gcp_compute_network_spike_with_cpu",
        "triggers": [
            {"resource_type": "Compute_Engine", "metrics": ["network_in_bytes", "network_out_bytes"]},
            {"resource_type": "Compute_Engine", "metrics": ["cpu_pct"]},
        ],
        "causal_index":     0,
        "description":      "Anomalous network traffic on GCP Compute Engine instances is co-occurring with CPU spikes. High inbound traffic may indicate a traffic surge, misconfigured clients, or a DDoS pattern.",
        "do_not_recommend": "Adding CPU without identifying the traffic source may not resolve the issue. Investigate network traffic origin and patterns first.",
        "confidence_boost": 0.15,
        "causal_order":     ["Compute_Engine (network)", "Compute_Engine (cpu)"],
    },
    {
        "name":             "backup_failure_with_storage_pressure",
        "triggers": [
            {"resource_type": "Accounts",          "metrics": ["storage_used_capacity_bytes", "availability_pct"]},
            {"resource_type": "Recovery_Services", "metrics": ["backup_health_event"]},
        ],
        "causal_index":     0,
        "description":      "Azure Storage Account is nearing capacity or has degraded availability, and Recovery Services backup health events are firing. The backup failures may be caused by insufficient storage headroom.",
        "do_not_recommend": "Retrying backups without addressing storage capacity will continue to fail. Expand storage or delete unneeded data first.",
        "confidence_boost": 0.25,
        "causal_order":     ["Accounts", "Recovery_Services"],
    },
    {
        "name":             "ebs_burst_depleted_causes_volume_io_degradation",
        "triggers": [
            {"resource_type": "EBS", "metrics": ["burst_balance_pct"]},
            {"resource_type": "EBS", "metrics": ["volume_queue_length", "volume_total_read_time_sec", "volume_total_write_time_sec"]},
        ],
        "causal_index":     0,
        "description":      "EBS BurstBalance is critically low, meaning the volume can no longer sustain burst IOPS. This directly causes VolumeQueueLength to grow as I/O requests back up.",
        "do_not_recommend": "Switching to a larger EC2 instance will not help — the issue is the EBS volume type. Upgrade to gp3 (which has no burst model) or provision dedicated IOPS with io1/io2.",
        "confidence_boost": 0.30,
        "causal_order":     ["EBS (burst_balance)", "EBS (queue_length)"],
    },
]

_RANK = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}


class CorrelationEngine:
    def find_correlated_sets(
        self,
        project_resources: list[dict],     # from ResourceStateManager.get_project_resources()
        historical_confidence_boost: float = 0.0,
    ) -> list[CorrelatedSet]:
        """
        Evaluate all domain rules against the current project resource states.
        Returns a list of matched CorrelatedSets (may be empty).
        """
        # Index resources by resource_type for fast rule matching
        by_type: dict[str, list[dict]] = {}
        for r in project_resources:
            rt = r.get("resource_type", "")
            by_type.setdefault(rt, []).append(r)

        matched_sets = []
        for rule in _RULES:
            sets = self._evaluate_rule(rule, by_type, historical_confidence_boost)
            matched_sets.extend(sets)

        return matched_sets

    def _evaluate_rule(
        self,
        rule: dict,
        by_type: dict[str, list[dict]],
        hist_boost: float,
    ) -> list[CorrelatedSet]:
        triggers = rule["triggers"]
        causal_idx = rule["causal_index"]

        # For each trigger, find matching resources (in WARN/CRIT/ANOMALY)
        trigger_matches: list[list[dict]] = []
        for trig in triggers:
            rt = trig["resource_type"]
            required_metrics = set(trig["metrics"])
            matching = []
            for res in by_type.get(rt, []):
                alerts = res.get("current_alerts") or []
                alert_metrics = {a["metric"] for a in alerts if _RANK.get(a.get("status", "OK"), 0) >= 1}
                if alert_metrics & required_metrics:
                    matching.append(res)
            trigger_matches.append(matching)

        # Rule fires only if ALL triggers have at least one matching resource
        if any(len(m) == 0 for m in trigger_matches):
            return []

        # Build CorrelatedSets: one per matching root-cause resource
        results = []
        root_candidates = trigger_matches[causal_idx]
        for root_resource in root_candidates:
            dependent_ids = []
            triggered_metrics = []

            # Collect alert metrics from root resource
            for a in (root_resource.get("current_alerts") or []):
                if _RANK.get(a.get("status", "OK"), 0) >= 1:
                    triggered_metrics.append(f"{root_resource.get('resource_type')}:{a['metric']}")

            # Collect dependent resources (all other triggers)
            for idx, matches in enumerate(trigger_matches):
                if idx == causal_idx:
                    continue
                for dep in matches:
                    dep_id = dep.get("_id", "")
                    if dep_id and dep_id != root_resource.get("_id"):
                        dependent_ids.append(dep_id)
                    for a in (dep.get("current_alerts") or []):
                        if _RANK.get(a.get("status", "OK"), 0) >= 1:
                            triggered_metrics.append(f"{dep.get('resource_type')}:{a['metric']}")

            confidence = min(0.5 + rule["confidence_boost"] + hist_boost, 0.97)

            results.append(CorrelatedSet(
                rule_name               = rule["name"],
                root_cause_resource_id  = root_resource.get("_id", ""),
                root_cause_resource_type= root_resource.get("resource_type", ""),
                root_cause_category     = root_resource.get("category", ""),
                dependent_resource_ids  = list(set(dependent_ids)),
                triggered_metrics       = list(set(triggered_metrics)),
                root_cause_description  = rule["description"],
                do_not_recommend        = rule["do_not_recommend"],
                confidence              = confidence,
                causal_order            = rule["causal_order"],
                detected_at             = datetime.now(),
            ))

        return results
