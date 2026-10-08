"""
Document builders: turn canonical hourly arrays + alert episodes into Mongo-style log
documents with ONE schema for AWS, Azure and GCP.

One document = one resource x one metric x one UTC day (24 hourly points) - the same
granularity as the real sample logs.  Every document carries the same top-level keys;
`alerts` is [] unless a cloud alert rule was active for that metric during that day.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np

from .fleet import DISK_GB, INSTANCE, NATIVE_METRIC, ProjectSpec, ResourceSpec, oid

ISO = "%Y-%m-%dT%H:%M:%S.%f"


def _d(dt: datetime) -> dict:
    return {"$date": dt.strftime(ISO)[:-3] + "Z"}


def _h(seed: str, n: int) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:n]


def _uuid(seed: str) -> str:
    h = hashlib.sha1(seed.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ── identity of a resource ────────────────────────────────────────────────────

class Identity:
    """Everything provider-specific that stays constant for a resource."""

    def __init__(self, proj: ProjectSpec, res: ResourceSpec, project_id: str):
        self.proj, self.res, self.project_id = proj, res, project_id
        self.provider = proj.provider
        self.name = f"{proj.app}-{proj.env}-{res.key}"
        seed = f"{proj.provider}|{proj.key}|{res.key}"
        self.account_id = oid(f"acct|{proj.provider}|{proj.key}")
        self.inventory_id = oid(f"inv|{seed}")
        vcpus, mem_gb, _, _ = INSTANCE[self.provider][res.instance_type]
        self.vcpus, self.mem_gb = vcpus, mem_gb
        self.mem_bytes = mem_gb * 1024 ** 3

        if self.provider == "AWS":
            self.region = "us-east-1"
            self.zone = "us-east-1a" if res.key.endswith("1") else "us-east-1b"
            self.aws_acct = "".join(str(int(c, 16) % 10) for c in _h("aws" + proj.key, 12))
            self.resource_id = "i-" + _h(seed, 17)
            self.account_name = "QATeamAccount" if proj.key == "p1" else "PlatformStagingAccount"
            self.group = f"{proj.app}-{proj.env}-vpc"
        elif self.provider == "Azure":
            self.region = "eastus" if proj.key == "p1" else "centralus"
            self.zone = ""
            self.sub = _uuid("sub|" + proj.key)
            self.rg = f"{proj.app}-{proj.env}-rg"
            self.resource_id = (f"/subscriptions/{self.sub}/resourceGroups/{self.rg}"
                                f"/providers/Microsoft.Compute/virtualMachines/{self.name}")
            self.account_name = ("CS_SaaS_QA_API-Automation-Testing" if proj.key == "p1"
                                 else "CS_SaaS_Staging_Platform")
            self.group = self.rg
        else:
            self.region = "us-central1"
            self.zone = "us-central1-a"
            self.gcp_project = f"{proj.app}-{proj.env}-{_h('gcp' + proj.key, 5)}"
            self.resource_id = f"projects/{self.gcp_project}/zones/{self.zone}/instances/{self.name}"
            self.account_name = "gcp-shop-prod" if proj.key == "p1" else "gcp-analytics-staging"
            self.group = self.gcp_project

    # ---- tags -----------------------------------------------------------------
    def tag_dict(self) -> dict:
        t = {"app": self.proj.app, "tier": self.res.tier, "env": self.proj.env,
             "owner": "cloudops", "cost-center": "CC-" + _h(self.proj.app, 4)}
        if self.provider != "GCP":
            t["Name"] = self.name
        return t

    def tag_list(self) -> list:
        return [{"key": k, "value": v} for k, v in self.tag_dict().items()]

    # ---- summary_details (what the config extractor reads) --------------------
    def summary_details(self) -> dict:
        p = self.provider
        itype = self.res.instance_type
        disk_gb = DISK_GB[p]
        if p == "AWS":
            vol = "vol-" + _h(self.resource_id + "root", 17)
            items = [{"deviceName": "/dev/xvda",
                      "ebs": {"volumeId": vol, "status": "attached", "deleteOnTermination": "true"}}]
            if self.res.tier == "db":
                items.append({"deviceName": "/dev/sdf", "ebs": {
                    "volumeId": "vol-" + _h(self.resource_id + "data", 17), "status": "attached",
                    "deleteOnTermination": "false"}})
            return {
                "reservationId": "r-" + _h(self.resource_id, 17), "ownerId": self.aws_acct,
                "instancesSet": {"item": {
                    "instanceId": self.resource_id, "imageId": "ami-0" + _h("ami" + itype, 16),
                    "instanceState": {"code": 16, "name": "running"},
                    "instanceType": itype,
                    "launchTime": "2026-01-14T09:12:41.000Z",
                    "placement": {"availabilityZone": self.zone, "tenancy": "default", "groupName": ""},
                    "monitoring": {"state": "enabled" if self.proj.env == "prod" else "disabled"},
                    "architecture": "x86_64", "rootDeviceType": "ebs", "rootDeviceName": "/dev/xvda",
                    "blockDeviceMapping": {"item": items},
                    "virtualizationType": "hvm", "hypervisor": "xen",
                    "ebsOptimized": "true" if not itype.startswith("t") else "false",
                    "enaSupport": "true",
                    "cpuOptions": {"coreCount": str(max(self.vcpus // 2, 1)), "threadsPerCore": "2"},
                    "metadataOptions": {"state": "applied", "httpTokens": "required",
                                        "httpPutResponseHopLimit": "1", "httpEndpoint": "enabled"},
                    "maintenanceOptions": {"autoRecovery": "default"},
                    "sourceDestCheck": "true",
                    "platformDetails": "Linux/UNIX", "usageOperation": "RunInstances",
                    "tagSet": {"item": [{"key": k, "value": v} for k, v in self.tag_dict().items()]},
                }},
            }
        if p == "Azure":
            data_disks = []
            if self.res.tier == "db":
                data_disks = [{"lun": 0, "name": f"{self.name}_datadisk_0", "createOption": "Attach",
                               "diskSizeGB": disk_gb, "caching": "ReadOnly",
                               "managedDisk": {"id": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}"
                                                     f"/providers/Microsoft.Compute/disks/{self.name}_datadisk_0"}}]
            return {
                "name": self.name, "id": self.resource_id,
                "type": "Microsoft.Compute/virtualMachines", "location": self.region,
                "tags": self.tag_dict(),
                "properties": {
                    "hardwareProfile": {"vmSize": itype}, "provisioningState": "Succeeded",
                    "vmId": _uuid("vm|" + self.resource_id),
                    "storageProfile": {
                        "imageReference": {"publisher": "canonical", "offer": "ubuntu-24_04-lts",
                                           "sku": "server", "version": "latest"},
                        "osDisk": {"osType": "Linux", "name": f"{self.name}_osdisk", "createOption": "FromImage",
                                   "caching": "ReadWrite", "diskSizeGB": 64,
                                   "managedDisk": {"id": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}"
                                                         f"/providers/Microsoft.Compute/disks/{self.name}_osdisk"}},
                        "dataDisks": data_disks},
                    "osProfile": {"computerName": self.name, "adminUsername": "azureuser"},
                    "diagnosticsProfile": {"bootDiagnostics": {"enabled": True}},
                },
                "zones": ["1"], "status": "VM running",
            }
        boot = {"boot": True, "diskSizeGb": "30", "type": "PERSISTENT", "autoDelete": True,
                "deviceName": "boot", "source": f"projects/{self.gcp_project}/zones/{self.zone}/disks/{self.name}"}
        disks = [boot]
        if self.res.tier == "db":
            disks.append({"boot": False, "diskSizeGb": str(disk_gb), "type": "PERSISTENT", "autoDelete": False,
                          "deviceName": "data",
                          "source": f"projects/{self.gcp_project}/zones/{self.zone}/disks/{self.name}-data"})
        return {
            "id": str(int(_h(self.resource_id, 15), 16)), "name": self.name,
            "zone": f"https://www.googleapis.com/compute/v1/projects/{self.gcp_project}/zones/{self.zone}",
            "machineType": f"https://www.googleapis.com/compute/v1/projects/{self.gcp_project}/zones/{self.zone}/machineTypes/{itype}",
            "status": "RUNNING", "cpuPlatform": "Intel Broadwell",
            "canIpForward": False, "deletionProtection": False,
            "scheduling": {"preemptible": False, "provisioningModel": "STANDARD",
                           "automaticRestart": True, "onHostMaintenance": "MIGRATE"},
            "disks": disks,
            "shieldedInstanceConfig": {"enableSecureBoot": False, "enableVtpm": True,
                                       "enableIntegrityMonitoring": True},
            "networkInterfaces": [{"accessConfigs": [{"networkTier": "PREMIUM"}]}],
            "labels": self.tag_dict(),
        }

    def extended_summary_details(self) -> dict:
        p = self.provider
        if p == "Azure":
            return {"network_interfaces_details": {
                "name": f"{self.name}-nic",
                "id": f"/subscriptions/{self.sub}/resourceGroups/{self.rg}/providers/Microsoft.Network/networkInterfaces/{self.name}-nic",
                "properties": {"provisioningState": "Succeeded", "enableAcceleratedNetworking": False,
                               "enableIPForwarding": False, "nicType": "Standard",
                               "ipConfigurations": [{"name": "ipconfig1", "properties": {
                                   "privateIPAddress": f"10.{1 if self.proj.key == 'p1' else 2}.0.{4 + int(self.res.key[-1]) + (10 if self.res.tier == 'app' else 0)}",
                                   "privateIPAllocationMethod": "Dynamic", "primary": True}}]},
                "location": self.region}}
        if p == "AWS":
            return {"network_interfaces": [{"privateIpAddress": f"10.{1 if self.proj.key == 'p1' else 2}.1.{10 + int(self.res.key[-1])}",
                                            "subnetId": "subnet-" + _h(self.group, 8),
                                            "sourceDestCheck": True}]}
        return {"network_interface_details": {"network": f"projects/{self.gcp_project}/global/networks/default",
                                              "subnetwork": "default"}}


# ── metric encoding ───────────────────────────────────────────────────────────

_ROLE_META = {
    #  role       display                               unit       kind
    "cpu":        ("CPU Utilization",                   "Percent", "pct"),
    "mem":        ("Memory Used",                       "Percent", "pct"),
    "disk":       ("Disk Used",                         "Percent", "pct"),
    "credit":     ("CPU Credit Balance",                "Count",   "count"),
    "sched_wait": ("CPU Scheduler Wait Time",           "Seconds", "sec"),
    "net_in":     ("Network In",                        "Bytes",   "bytes"),
    "net_out":    ("Network Out",                       "Bytes",   "bytes"),
    "disk_write": ("Disk Write Bytes",                  "Bytes",   "bytes"),
}
_AZ_DISPLAY = {
    "cpu": "Percentage CPU", "mem": "Available Memory Bytes", "disk": "Disk Free Percent",
    "credit": "CPU Credits Remaining", "net_in": "Network In Total", "net_out": "Network Out Total",
    "disk_write": "Disk Write Bytes",
}
_BYTES_DIV = {"AWS": 12.0, "Azure": 60.0, "GCP": 60.0}     # hourly total -> mean per sampling interval


def native_value(role: str, provider: str, v: float, ident: Identity) -> float:
    """canonical -> provider-native average value."""
    if role == "cpu" and provider == "GCP":
        return v / 100.0
    if role == "mem" and provider == "Azure":
        return (100.0 - v) / 100.0 * ident.mem_bytes
    if role == "disk" and provider == "Azure":
        return 100.0 - v
    if _ROLE_META[role][2] == "bytes":
        return v / _BYTES_DIV[provider]
    return v


def _encode_points(role, ident, arr_day, day_start, rng, aws_native):
    prov = ident.provider
    kind = _ROLE_META[role][2]
    unit = _ROLE_META[role][1]
    if role == "cpu" and prov == "GCP":
        unit = "Ratio"
    if role == "mem" and prov == "Azure":
        unit = "Bytes"
    pts = []
    for h, v in enumerate(arr_day):
        ts = day_start + timedelta(hours=h)
        if v != v:                               # monitoring gap: timestamp present, no values
            pts.append({("Timestamp" if aws_native else "timeStamp"): _d(ts)})
            continue
        avg = native_value(role, prov, float(v), ident)
        if kind == "pct":
            spread = 4.0 if role == "cpu" else (0.8 if role == "mem" else 0.08)
            hi_c, lo_c = float(v) + abs(rng.normal(0, spread)), float(v) - abs(rng.normal(0, spread))
            hi = native_value(role, prov, min(hi_c, 100.0), ident)
            lo = native_value(role, prov, max(lo_c, 0.0), ident)
            mx, mn = (max(hi, lo), min(hi, lo))
            mx, mn = max(mx, avg), min(mn, avg)
            core = {"average": round(avg, 6), "minimum": round(mn, 6), "maximum": round(mx, 6)}
        elif kind in ("bytes",):
            mx = avg * (1 + abs(rng.normal(0, 0.28)))
            mn = max(avg * (1 - abs(rng.normal(0, 0.28))), 0.0)
            core = {"average": round(avg, 2), "minimum": round(mn, 2), "maximum": round(mx, 2),
                    "total": round(float(v), 2), "count": int(_BYTES_DIV[prov])}
        elif kind == "sec":
            core = {"average": round(avg, 3), "minimum": round(avg * 0.85, 3), "maximum": round(avg * 1.2, 3),
                    "total": round(avg, 3), "count": 60}
        else:  # count (credits)
            core = {"average": round(avg, 3), "minimum": round(max(avg - abs(rng.normal(0, 0.5)) - 0.5, 0), 3),
                    "maximum": round(avg + abs(rng.normal(0, 0.5)) + 0.5, 3)}
        if aws_native and prov == "AWS":
            pt = {"Timestamp": _d(ts), "SampleCount": core.get("count", 12) if "count" in core else 12,
                  "Unit": unit, "Average": core["average"], "Minimum": core["minimum"],
                  "Maximum": core["maximum"], "Sum": core.get("total", round(core["average"] * 12, 3))}
        else:
            pt = {"timeStamp": _d(ts), **core}
        pts.append(pt)
    return pts, unit


# ── alert objects ─────────────────────────────────────────────────────────────

_ALERT_LABEL = {
    ("cpu", ">"): "HighCpuUtilization", ("mem", ">"): "HighMemoryUsage",
    ("credit", "<"): "LowCpuCreditBalance", ("sched_wait", ">"): "HighCpuSchedulerWait",
    ("disk", ">"): "DiskSpaceLow", ("net_in", "surge"): "NetworkInAnomalyHigh",
    ("net_out", "surge"): "NetworkOutAnomalyHigh", ("net_in", "drop"): "NetworkInTrafficDrop",
    ("net_out", "drop"): "NetworkOutTrafficDrop",
}
_PROV_SEV = {
    "AWS": {"Critical": "ALARM", "Warning": "ALARM"},
    "Azure": {"Critical": "Sev1", "Warning": "Sev2"},
    "GCP": {"Critical": "CRITICAL", "Warning": "WARNING"},
}
_OPERATOR = {
    "AWS":   {">": "GreaterThanThreshold", "<": "LessThanThreshold",
              "surge": "GreaterThanUpperThreshold", "drop": "LessThanLowerThreshold"},
    "Azure": {">": "GreaterThan", "<": "LessThan", "surge": "GreaterThan", "drop": "LessThan"},
    "GCP":   {">": "COMPARISON_GT", "<": "COMPARISON_LT", "surge": "COMPARISON_GT", "drop": "COMPARISON_LT"},
}
_SOURCE = {"AWS": "CloudWatch Alarm", "Azure": "Azure Monitor Metric Alert",
           "GCP": "Cloud Monitoring Alert Policy"}


def build_alert(ep, ident: Identity, t0: datetime, day_start: datetime, day_end: datetime):
    prov, role = ident.provider, ep.role
    native_metric = NATIVE_METRIC[prov][role]
    fired = t0 + timedelta(hours=ep.fired_idx, minutes=55)
    resolved = None if ep.resolved_idx is None else t0 + timedelta(hours=ep.resolved_idx, minutes=55)

    if ep.condition == "static":
        thr_c, obs_c = ep.threshold, ep.observed
        thr = native_value(role, prov, thr_c, ident)
        obs = native_value(role, prov, obs_c, ident)
        op = ep.op
        # Azure reports free-space / available-bytes, so the comparison flips
        if prov == "Azure" and role in ("mem", "disk"):
            op = "<"
        expected = None
    else:
        base = native_value(role, prov, ep.baseline or 0.0, ident)
        thr = base * ep.threshold
        obs = native_value(role, prov, ep.observed, ident)
        expected = base
        op = ep.op
    rule_label = _ALERT_LABEL[(role, ep.op if ep.condition == "dynamic" else ">" if ep.op == ">" else "<")]
    rule_name = f"{ident.name}-{rule_label}-{ep.severity}"
    if prov == "AWS":
        rule_id = f"arn:aws:cloudwatch:{ident.region}:{ident.aws_acct}:alarm:{rule_name}"
    elif prov == "Azure":
        rule_id = (f"/subscriptions/{ident.sub}/resourceGroups/{ident.rg}/providers/"
                   f"microsoft.insights/metricalerts/{rule_name}")
    else:
        rule_id = f"projects/{ident.gcp_project}/alertPolicies/{_h(rule_name, 12)}"

    # a log only knows what had happened by the end of its own day
    if resolved is not None and resolved > day_end:
        resolved = None
    state = "Resolved" if resolved is not None else "Fired"
    dur = None
    if resolved is not None:
        dur = int((resolved - fired).total_seconds() // 60)
    if ep.condition == "dynamic":
        desc = (f"{native_metric} {'above' if ep.op == 'surge' else 'below'} the seasonal band "
                f"(x{ep.threshold:g} of the same-hour-of-week baseline) for {ep.eval_hours}h")
    else:
        label = {"cpu": "CPU utilization", "mem": "memory used", "disk": "disk used",
                 "credit": "CPU credit balance", "sched_wait": "CPU scheduler wait (s/h)"}[role]
        sym = {">": "above", "<": "below"}[ep.op]
        unit = "%" if role in ("cpu", "mem", "disk") else ""
        desc = f"{label} {sym} {ep.threshold:g}{unit} for {ep.eval_hours} consecutive hourly period(s)"
        if prov == "Azure" and role in ("mem", "disk"):
            desc += f" (rule evaluated on {native_metric})"
    return {
        "alert_id": "alr-" + _h(f"{ident.resource_id}|{rule_name}|{ep.fired_idx}", 14),
        "alert_name": rule_name,
        "alert_rule_id": rule_id,
        "alert_source": _SOURCE[prov],
        "severity": ep.severity,
        "provider_severity": _PROV_SEV[prov][ep.severity],
        "state": state,
        "metric": native_metric,
        "operator": _OPERATOR[prov][op if ep.condition == "dynamic" else (">" if op == ">" else "<")],
        "aggregation": "Minimum" if ep.op == "<" or ep.op == "drop" else "Average",
        "threshold": round(float(thr), 4),
        "expected_value": None if expected is None else round(float(expected), 4),
        "observed_value": round(float(obs), 4),
        "condition_type": ep.condition,
        "evaluation_periods": ep.eval_hours,
        "period_minutes": 60,
        "fired_at": _d(fired),
        "resolved_at": None if resolved is None else _d(resolved),
        "duration_minutes": dur,
        "is_continuation": fired < day_start,
        "description": desc,
    }


# ── document assembly ─────────────────────────────────────────────────────────

def build_docs_for_series(ident: Identity, role: str, values: np.ndarray, episodes: list,
                          t0: datetime, n_days: int, rng, aws_native=False):
    prov = ident.provider
    native = NATIVE_METRIC[prov][role]
    display = _AZ_DISPLAY[role] if prov == "Azure" else native
    ns = {"AWS": "AWS/EC2" if role in ("cpu", "credit", "net_in", "net_out", "disk_write") else "CWAgent",
          "Azure": "Microsoft.Compute/virtualMachines",
          "GCP": "compute.googleapis.com" if role not in ("mem", "disk") else "agent.googleapis.com"}[prov]
    cfg = {
        "AWS": dict(uri="AWS/Compute/EC2/Instance", operation_id="EC2_DescribeInstances", component="EC2",
                    resource="Instances", resource_type="EC2", filt=ident.region),
        "Azure": dict(uri="Azure/Compute/Virtual_Machines/Virtual_Machines", operation_id="VirtualMachinesList",
                      component="Virtual_Machines", resource="Virtual_Machines", resource_type="Virtual_Machines",
                      filt=getattr(ident, "rg", "")),
        "GCP": dict(uri="GCP/Compute/Compute_Engine/Instance", operation_id="compute.instances.list",
                    component="Compute_Engine", resource="Instances", resource_type="Compute_Engine",
                    filt=ident.zone),
    }[prov]
    summary = ident.summary_details()
    ext = ident.extended_summary_details()
    tags = ident.tag_list()
    docs = []
    for d in range(n_days):
        ds = t0 + timedelta(days=d)
        de = ds + timedelta(days=1) - timedelta(milliseconds=1)
        arr = values[d * 24:(d + 1) * 24]
        pts, unit = _encode_points(role, ident, arr, ds, rng, aws_native)
        alerts = []
        for ep in episodes:
            fired = t0 + timedelta(hours=ep.fired_idx, minutes=55)
            res = None if ep.resolved_idx is None else t0 + timedelta(hours=ep.resolved_idx, minutes=55)
            if fired <= de and (res is None or res >= ds):
                alerts.append(build_alert(ep, ident, t0, ds, de))
        ingest = de + timedelta(minutes=int(rng.integers(3, 25)))
        docs.append({
            "_id": {"$oid": oid(f"{ident.resource_id}|{native}|{d}")},
            "category": "Compute",
            "config_type": "default_monitoring",
            "metric": native,
            "resourceId": ident.resource_id,
            "account_id": ident.account_id,
            "to_date": _d(de),
            "element_id": ident.resource_id,
            "from_date": _d(ds),
            "display_name": display,
            "group_name": display,
            "metric_group_name": display,
            "metric_value": pts,
            "namespace": ns,
            "name": ident.group,
            "resource_name": ident.name,
            "uri": cfg["uri"],
            "unit": unit,
            "updated_at": _d(ingest),
            "inventory_id": {"$oid": ident.inventory_id},
            "resource_filter": cfg["filt"],
            "operation_id": cfg["operation_id"],
            "component": cfg["component"],
            "created_at": _d(ingest),
            "created_by": "coreteam_rootaccount",
            "custom_metrics": {},
            "location": ident.zone or ident.region,
            "region": ident.region,
            "meta_data": {},
            "project": ident.project_id,
            "resource": cfg["resource"],
            "resource_type": cfg["resource_type"],
            "account_name": ident.account_name,
            "service_name": prov,
            "service_type": "Cloud",
            "summary_details": summary,
            "tags": tags,
            "third_party_integration": {},
            "extended_summary_details": ext,
            "alerts": alerts,
        })
    return docs
