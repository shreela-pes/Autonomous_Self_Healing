"""
Feature Normalizer — converts provider-specific raw config into cross-cloud
canonical features and pre-computed analytical signals.

Outputs a NormalizedProfile with:
  - Canonical sizing fields (vcpus, memory_gb, resource_size_label)
  - Lifecycle state (is_running, is_orphaned, is_idle_waste)
  - Encryption posture (is_encrypted, encryption_type)
  - Security findings (IMDSv1, public access, no encryption, deprecated runtime…)
  - Cost signals (gp2→gp3, unattached disks, stopped VMs still billed, old generation…)
  - Reliability signals (no auto-recovery, single-AZ, no monitoring…)
  - Burst model context (credits, baseline, exhaustion risk)

These signals are injected into the LLM prompt so that every recommendation
is grounded in the actual resource configuration — not generic advice.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Finding:
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW | INFO
    category: str          # SECURITY | COST | RELIABILITY | PERFORMANCE | OBSERVABILITY
    finding: str
    remediation: str
    context: str = ""


@dataclass
class BurstContext:
    is_burstable: bool
    baseline_cpu_pct: Optional[float] = None
    credits_per_hour_earned: Optional[float] = None
    max_credits: Optional[float] = None
    description: str = ""


@dataclass
class NormalizedProfile:
    # ── Cross-cloud canonical sizing ──────────────────────────────────────────
    resource_size_label: str = "unknown"
    vcpus: Optional[float] = None
    memory_gb: Optional[float] = None
    storage_size_gb: Optional[int] = None
    iops_provisioned: Optional[int] = None
    throughput_mbps_provisioned: Optional[int] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    lifecycle_state: str = "unknown"
    is_running: bool = True
    is_orphaned: bool = False        # unattached disk, deallocated VM still billed for disk
    is_idle_waste: bool = False      # stopped but accruing cost

    # ── Encryption ────────────────────────────────────────────────────────────
    is_encrypted: Optional[bool] = None
    encryption_type: Optional[str] = None

    # ── Security / exposure ───────────────────────────────────────────────────
    public_access_risk: str = "unknown"   # none | low | medium | high | critical
    imds_version: Optional[str] = None   # "v1" | "v2"

    # ── Monitoring ────────────────────────────────────────────────────────────
    monitoring_detail: str = "basic"     # basic | detailed | disabled

    # ── Burst model (compute) ─────────────────────────────────────────────────
    burst_context: Optional[BurstContext] = None

    # ── Pre-computed findings ─────────────────────────────────────────────────
    security_findings: list = field(default_factory=list)
    cost_findings:     list = field(default_factory=list)
    reliability_findings: list = field(default_factory=list)
    performance_notes: list = field(default_factory=list)

    # ── Volume/disk type derived specs ────────────────────────────────────────
    volume_type_specs: dict = field(default_factory=dict)   # baseline IOPS, burst IOPS, cost note

    def all_findings(self) -> list[Finding]:
        return (self.security_findings + self.cost_findings +
                self.reliability_findings + self.performance_notes)

    def has_critical_findings(self) -> bool:
        return any(f.severity in ("CRITICAL", "HIGH") for f in self.all_findings())


# ─────────────────────────────────────────────────────────────────────────────
# Instance specification tables
# ─────────────────────────────────────────────────────────────────────────────

# EC2: (vcpus, memory_gb, is_burstable, baseline_cpu_pct, credits_per_hr, max_credits)
_EC2_SPECS: dict[str, tuple] = {
    # t2 family (legacy burstable)
    "t2.nano":    (1, 0.5,  True, 5.0,  3,   72),
    "t2.micro":   (1, 1.0,  True, 10.0, 6,   144),
    "t2.small":   (1, 2.0,  True, 20.0, 12,  288),
    "t2.medium":  (2, 4.0,  True, 20.0, 24,  576),
    "t2.large":   (2, 8.0,  True, 30.0, 36,  864),
    "t2.xlarge":  (4, 16.0, True, 22.5, 54,  1296),
    "t2.2xlarge": (8, 32.0, True, 17.0, 81.6,1958),
    # t3 family (current burstable — unlimited by default)
    "t3.nano":    (2, 0.5,  True, 5.0,  6,   144),
    "t3.micro":   (2, 1.0,  True, 10.0, 12,  288),
    "t3.small":   (2, 2.0,  True, 20.0, 24,  576),
    "t3.medium":  (2, 4.0,  True, 20.0, 24,  576),
    "t3.large":   (2, 8.0,  True, 30.0, 36,  864),
    "t3.xlarge":  (4, 16.0, True, 40.0, 96,  2304),
    "t3.2xlarge": (8, 32.0, True, 40.0, 192, 4608),
    # t4g family (ARM/Graviton2 burstable)
    "t4g.nano":   (2, 0.5,  True, 5.0,  6,   144),
    "t4g.micro":  (2, 1.0,  True, 10.0, 12,  288),
    "t4g.small":  (2, 2.0,  True, 20.0, 24,  576),
    "t4g.medium": (2, 4.0,  True, 20.0, 24,  576),
    "t4g.large":  (2, 8.0,  True, 30.0, 36,  864),
    # m5 / m6 family (general purpose, non-burstable)
    "m5.large":   (2, 8.0,  False, None, None, None),
    "m5.xlarge":  (4, 16.0, False, None, None, None),
    "m5.2xlarge": (8, 32.0, False, None, None, None),
    "m5.4xlarge": (16,64.0, False, None, None, None),
    "m6i.large":  (2, 8.0,  False, None, None, None),
    "m6i.xlarge": (4, 16.0, False, None, None, None),
    "m6i.2xlarge":(8, 32.0, False, None, None, None),
    "m6a.large":  (2, 8.0,  False, None, None, None),
    "m6a.xlarge": (4, 16.0, False, None, None, None),
    "m7i.large":  (2, 8.0,  False, None, None, None),
    "m7i.xlarge": (4, 16.0, False, None, None, None),
    # c5 / c6 family (compute optimized)
    "c5.large":   (2, 4.0,  False, None, None, None),
    "c5.xlarge":  (4, 8.0,  False, None, None, None),
    "c5.2xlarge": (8, 16.0, False, None, None, None),
    "c5.4xlarge": (16,32.0, False, None, None, None),
    "c6i.large":  (2, 4.0,  False, None, None, None),
    "c6i.xlarge": (4, 8.0,  False, None, None, None),
    # r5 / r6 family (memory optimized)
    "r5.large":   (2, 16.0, False, None, None, None),
    "r5.xlarge":  (4, 32.0, False, None, None, None),
    "r5.2xlarge": (8, 64.0, False, None, None, None),
    "r6i.large":  (2, 16.0, False, None, None, None),
    "r6i.xlarge": (4, 32.0, False, None, None, None),
}

# Azure VM sizes: (vcpus, memory_gb, is_burstable, family_label)
_AZURE_VM_SPECS: dict[str, tuple] = {
    # B-series burstable
    "Standard_B1ls":   (1, 0.5,  True, "B-series burstable"),
    "Standard_B1s":    (1, 1.0,  True, "B-series burstable"),
    "Standard_B1ms":   (1, 2.0,  True, "B-series burstable"),
    "Standard_B2s":    (2, 4.0,  True, "B-series burstable"),
    "Standard_B2ms":   (2, 8.0,  True, "B-series burstable"),
    "Standard_B4ms":   (4, 16.0, True, "B-series burstable"),
    "Standard_B8ms":   (8, 32.0, True, "B-series burstable"),
    "Standard_B12ms":  (12,48.0, True, "B-series burstable"),
    "Standard_B16ms":  (16,64.0, True, "B-series burstable"),
    # D-series general purpose
    "Standard_D2s_v3": (2, 8.0,  False, "Dsv3 general purpose"),
    "Standard_D4s_v3": (4, 16.0, False, "Dsv3 general purpose"),
    "Standard_D8s_v3": (8, 32.0, False, "Dsv3 general purpose"),
    "Standard_D2s_v5": (2, 8.0,  False, "Dsv5 general purpose (latest)"),
    "Standard_D4s_v5": (4, 16.0, False, "Dsv5 general purpose (latest)"),
    "Standard_D8s_v5": (8, 32.0, False, "Dsv5 general purpose (latest)"),
    "Standard_D16s_v5":(16,64.0, False, "Dsv5 general purpose (latest)"),
    # E-series memory optimized
    "Standard_E2s_v5": (2, 16.0, False, "Esv5 memory optimized"),
    "Standard_E4s_v5": (4, 32.0, False, "Esv5 memory optimized"),
    "Standard_E8s_v5": (8, 64.0, False, "Esv5 memory optimized"),
    # F-series compute optimized
    "Standard_F2s_v2": (2, 4.0,  False, "Fsv2 compute optimized"),
    "Standard_F4s_v2": (4, 8.0,  False, "Fsv2 compute optimized"),
    "Standard_F8s_v2": (8, 16.0, False, "Fsv2 compute optimized"),
}

# Azure B-series burst model: (credits banked per hour, max banked credits)
# baseline % of the WHOLE VM = credits_per_hr / (vcpus * 60) * 100
_AZURE_BURST_SPECS: dict[str, tuple] = {
    "Standard_B1ls": (3, 72), "Standard_B1s": (6, 144), "Standard_B1ms": (12, 288),
    "Standard_B2s": (24, 576), "Standard_B2ms": (36, 864), "Standard_B4ms": (54, 1296),
}

# GCP shared-core (e2-micro/small/medium): (sustained credits/hr, max credits) - modelled the same way.
# GCP does not publish a credit metric; the pipeline uses CPU plateau + scheduler wait instead.
_GCP_BURST_SPECS: dict[str, tuple] = {
    "e2-micro": (15, 360), "e2-small": (30, 720), "e2-medium": (60, 1440),
}

# GCP: (vcpus, memory_gb, is_preemptible_eligible)
_GCP_SPECS: dict[str, tuple] = {
    "e2-micro":          (2, 1.0),
    "e2-small":          (2, 2.0),
    "e2-medium":         (2, 4.0),
    "e2-standard-2":     (2, 8.0),
    "e2-standard-4":     (4, 16.0),
    "e2-standard-8":     (8, 32.0),
    "e2-standard-16":    (16,64.0),
    "n1-standard-1":     (1, 3.75),
    "n1-standard-2":     (2, 7.5),
    "n1-standard-4":     (4, 15.0),
    "n2-standard-2":     (2, 8.0),
    "n2-standard-4":     (4, 16.0),
    "n2-standard-8":     (8, 32.0),
    "c2-standard-4":     (4, 16.0),
    "c2-standard-8":     (8, 32.0),
    "n2d-standard-2":    (2, 8.0),
    "n2d-standard-4":    (4, 16.0),
}

# EBS volume type performance characteristics
_EBS_VOLUME_SPECS: dict[str, dict] = {
    "gp2": {
        "baseline_iops_formula": "3 IOPS/GB (min 100, max 16,000)",
        "burst_iops":            3000,
        "burst_model":           "credit-based (volumes < 1 TB burst to 3,000 IOPS)",
        "max_throughput_mbps":   128,
        "cost_per_gb":           0.10,
        "upgrade_note":          "gp3 provides 3,000 baseline IOPS and 125 MB/s at $0.08/GB — 20% cheaper with no burst model",
        "upgrade_target":        "gp3",
    },
    "gp3": {
        "baseline_iops_formula": "3,000 IOPS baseline (up to 16,000 at $0.005/IOPS)",
        "burst_iops":            None,
        "burst_model":           "none — consistent baseline performance",
        "max_throughput_mbps":   1000,
        "cost_per_gb":           0.08,
        "upgrade_note":          "Already optimal general-purpose choice",
        "upgrade_target":        None,
    },
    "io1": {
        "baseline_iops_formula": "Provisioned IOPS (max 64,000)",
        "burst_iops":            None,
        "burst_model":           "none — consistent provisioned performance",
        "max_throughput_mbps":   1000,
        "cost_per_gb":           0.125,
        "upgrade_note":          "io2 provides 100× better durability (99.999%) at same price",
        "upgrade_target":        "io2",
    },
    "io2": {
        "baseline_iops_formula": "Provisioned IOPS (max 256,000)",
        "burst_iops":            None,
        "burst_model":           "none",
        "max_throughput_mbps":   4000,
        "cost_per_gb":           0.125,
        "upgrade_note":          "Highest durability (99.999%) and performance",
        "upgrade_target":        None,
    },
    "st1": {
        "baseline_iops_formula": "40 IOPS/TB baseline",
        "burst_iops":            500,
        "burst_model":           "throughput-optimized (sequential workloads)",
        "max_throughput_mbps":   500,
        "cost_per_gb":           0.045,
        "upgrade_note":          "Best for big-data, log processing, data warehouses",
        "upgrade_target":        None,
    },
    "sc1": {
        "baseline_iops_formula": "12 IOPS/TB baseline",
        "burst_iops":            80,
        "burst_model":           "cold HDD (infrequent access)",
        "max_throughput_mbps":   250,
        "cost_per_gb":           0.025,
        "upgrade_note":          "Cheapest option, for infrequently accessed cold data only",
        "upgrade_target":        None,
    },
}

# Deprecated Lambda runtimes
_DEPRECATED_RUNTIMES = {
    "python2.7": "End-of-life 2019. Update to python3.12 immediately.",
    "python3.6": "End-of-life 2022. Update to python3.12.",
    "python3.7": "End-of-life 2023. Update to python3.12.",
    "python3.8": "Deprecated 2024. Update to python3.12.",
    "python3.9": "Deprecated 2024. Update to python3.12.",
    "nodejs10.x":"End-of-life 2021. Update to nodejs20.x.",
    "nodejs12.x":"End-of-life 2022. Update to nodejs20.x.",
    "nodejs14.x":"End-of-life 2023. Update to nodejs20.x.",
    "nodejs16.x":"Deprecated 2024. Update to nodejs20.x.",
    "java8":     "End-of-life. Update to java21.",
    "go1.x":     "Deprecated. Update to provided.al2023 with custom runtime.",
    "ruby2.5":   "End-of-life. Update to ruby3.3.",
    "ruby2.7":   "End-of-life. Update to ruby3.3.",
    "dotnet5.0": "End-of-life. Update to dotnet8.",
    "dotnet6":   "End-of-life 2024. Update to dotnet8.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-resource normalizer functions
# ─────────────────────────────────────────────────────────────────────────────

def normalize(resource_type: str, raw_config: dict) -> NormalizedProfile:
    fn = _NORMALIZERS.get(resource_type)
    if fn is None:
        return NormalizedProfile()
    return fn(raw_config)


def _normalize_ec2(cfg: dict) -> NormalizedProfile:
    itype = cfg.get("instance_type") or "unknown"
    specs = _EC2_SPECS.get(itype)
    vcpus = None; mem_gb = None; is_burst = False
    baseline = None; cph = None; max_cred = None

    if specs:
        vcpus, mem_gb, is_burst, baseline, cph, max_cred = specs
    else:
        # Parse from cpu_core_count if available
        core = cfg.get("cpu_core_count")
        tpc  = cfg.get("threads_per_core") or 1
        if core:
            vcpus = int(core) * int(tpc)
        # Detect burst from name pattern
        is_burst = itype.startswith(("t2.", "t3.", "t3a.", "t4g."))

    state  = cfg.get("instance_state", "unknown")
    is_run = state == "running"
    is_idle_waste = state == "stopped"  # stopped EC2 still charges for EBS

    size_label = (
        f"{itype} — {vcpus} vCPU{'s' if vcpus and vcpus > 1 else ''}, "
        f"{mem_gb} GB RAM, {'BURSTABLE' if is_burst else 'fixed compute'}"
        if vcpus else itype
    )

    prof = NormalizedProfile(
        resource_size_label = size_label,
        vcpus       = vcpus,
        memory_gb   = mem_gb,
        lifecycle_state = state,
        is_running  = is_run,
        is_idle_waste = is_idle_waste,
        imds_version = "v2" if cfg.get("imds_http_tokens") == "required" else "v1",
        monitoring_detail = "detailed" if cfg.get("monitoring_state") == "enabled" else "basic",
        burst_context = BurstContext(
            is_burstable          = is_burst,
            baseline_cpu_pct      = baseline,
            credits_per_hour_earned = cph,
            max_credits           = max_cred,
            description           = (
                f"Burstable instance (t-family): baseline CPU={baseline}%, "
                f"earns {cph} credits/hr, max pool={max_cred}. "
                f"Sustained CPU above {baseline}% depletes credits."
            ) if is_burst else "Fixed compute — no burst credit model.",
        ) if is_burst else BurstContext(is_burstable=False),
    )

    # ── Security findings ─────────────────────────────────────────────────────
    if cfg.get("imds_http_tokens") != "required":
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="IMDSv1 is active (httpTokens=optional). Instance Metadata API accessible without session tokens.",
            remediation=(
                f"aws ec2 modify-instance-metadata-options "
                f"--instance-id {cfg.get('volume_id', '<instance-id>')} "
                f"--http-tokens required --http-endpoint enabled"
            ),
            context="IMDSv1 + SSRF vulnerabilities = IAM credential theft. AWS recommends IMDSv2 on all instances."
        ))

    if cfg.get("monitoring_state") != "enabled":
        prof.reliability_findings.append(Finding(
            severity="MEDIUM", category="OBSERVABILITY",
            finding="Basic CloudWatch monitoring (5-minute intervals). Detailed monitoring not enabled.",
            remediation="aws ec2 monitor-instances --instance-ids <id>  (adds 1-minute metrics, small cost)",
            context="5-min granularity misses CPU spikes that resolve within a single period — root cause analysis becomes guesswork."
        ))

    if cfg.get("ebs_optimized") is False:
        prof.performance_notes.append(Finding(
            severity="MEDIUM", category="PERFORMANCE",
            finding="EBS-optimized is disabled. I/O to EBS volumes competes with network traffic on shared bandwidth.",
            remediation="Enable EBS-optimized in instance settings (supported on most modern instance types at no extra cost for m5/c5/r5+).",
            context="Non-EBS-optimized instances share network and storage I/O bandwidth, causing latency spikes under I/O load."
        ))

    if cfg.get("source_dest_check") is False:
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Source/Destination Check disabled — instance is configured to route traffic not addressed to it.",
            remediation="If this instance is NOT a NAT gateway, VPN, or firewall appliance, re-enable source/destination check.",
            context="Disabled source/destination check is correct only for NAT/VPN/NVA instances. On application servers it indicates misconfiguration."
        ))

    # ── Cost findings ─────────────────────────────────────────────────────────
    if is_idle_waste:
        prof.cost_findings.append(Finding(
            severity="HIGH", category="COST",
            finding=f"Instance is STOPPED (state={state}). EBS volumes, Elastic IPs, and reserved capacity still incur charges.",
            remediation="Terminate instance if unused, or snapshot EBS volumes and terminate to eliminate ongoing costs. Estimate: EBS + EIP = ~$5-15/month for a stopped t-family instance.",
            context="Stopped EC2 instances do NOT incur instance-hour charges but DO incur charges for attached EBS volumes and any Elastic IPs."
        ))

    if is_burst and is_run:
        gen_note = ""
        if itype.startswith("t2."):
            gen_note = " t3/t4g instances provide better burst limits, more credits, and similar pricing."
        elif itype.startswith("t3."):
            gen_note = " t4g (ARM Graviton) instances offer ~20% cost saving for compatible workloads."
        if gen_note:
            prof.cost_findings.append(Finding(
                severity="INFO", category="COST",
                finding=f"Instance type {itype} may have a cheaper/newer alternative with better burst model.{gen_note}",
                remediation="Evaluate t4g (ARM) or latest-gen equivalents if workload is Linux-compatible.",
                context=""
            ))

    return prof


def _normalize_lambda(cfg: dict) -> NormalizedProfile:
    mem = cfg.get("memory_mb")
    size_label = f"Lambda {mem} MB memory, {cfg.get('timeout_sec')}s timeout, {cfg.get('runtime')}"
    prof = NormalizedProfile(
        resource_size_label = size_label,
        memory_gb = (mem / 1024) if mem else None,
        lifecycle_state = cfg.get("state", "Active"),
        is_running = cfg.get("state") not in ("Failed", "Inactive"),
    )

    runtime = cfg.get("runtime")
    if runtime and runtime in _DEPRECATED_RUNTIMES:
        prof.security_findings.append(Finding(
            severity="CRITICAL", category="SECURITY",
            finding=f"Runtime '{runtime}' is deprecated/end-of-life. AWS will block deployments and may forcibly disable the function.",
            remediation=_DEPRECATED_RUNTIMES[runtime],
            context="Deprecated runtimes no longer receive security patches. This is a compliance and security violation."
        ))

    if not cfg.get("vpc_configured"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Lambda is NOT VPC-attached. It runs in Lambda's managed VPC with internet access.",
            remediation="If this function accesses internal resources (RDS, ElastiCache, private APIs), attach it to a VPC subnet.",
            context="Non-VPC Lambda can reach the internet but cannot reach VPC-internal resources without VPC attachment."
        ))

    if cfg.get("tracing_mode") != "Active":
        prof.reliability_findings.append(Finding(
            severity="LOW", category="OBSERVABILITY",
            finding="X-Ray tracing is not active. Cold start latency, downstream call durations not tracked.",
            remediation="Enable active X-Ray tracing: aws lambda update-function-configuration --function-name <name> --tracing-config Mode=Active",
            context=""
        ))

    if mem and mem < 256:
        prof.performance_notes.append(Finding(
            severity="MEDIUM", category="PERFORMANCE",
            finding=f"Memory allocation is {mem} MB — very low. Lambda CPU allocation scales proportionally with memory.",
            remediation="Increase memory to at least 512 MB for non-trivial workloads. Memory is cheap; CPU-bound Lambda errors are not.",
            context="Lambda vCPU allocation: 128 MB = 0.09 vCPU; 1792 MB = 1 full vCPU; 10240 MB = 6 vCPUs."
        ))

    if cfg.get("state") in ("Failed", "Inactive"):
        prof.reliability_findings.append(Finding(
            severity="CRITICAL", category="RELIABILITY",
            finding=f"Lambda state is '{cfg.get('state')}' (StateReasonCode: {cfg.get('state_reason_code', 'unknown')}). Function may be non-functional.",
            remediation="Check Lambda console, CloudWatch Logs, and fix the root cause (VPC config, layer incompatibility, etc.).",
            context=""
        ))

    return prof


def _normalize_virtual_machines(cfg: dict) -> NormalizedProfile:
    vm_size = cfg.get("vm_size", "unknown")
    specs = _AZURE_VM_SPECS.get(vm_size)
    vcpus = None; mem_gb = None; is_burst = False; family = "unknown"
    if specs:
        vcpus, mem_gb, is_burst, family = specs

    power_state = cfg.get("power_state", "")
    is_run = "running" in (power_state or "").lower()
    is_deallocated = "deallocated" in (power_state or "").lower()

    size_label = f"{vm_size} ({family}) — {vcpus} vCPUs, {mem_gb} GB RAM" if vcpus else vm_size
    burst_ctx = BurstContext(is_burstable=is_burst)
    if is_burst and vm_size in _AZURE_BURST_SPECS and vcpus:
        cph, max_cr = _AZURE_BURST_SPECS[vm_size]
        baseline = round(cph / (vcpus * 60.0) * 100.0, 1)
        burst_ctx = BurstContext(
            is_burstable=True, baseline_cpu_pct=baseline, credits_per_hour_earned=cph, max_credits=max_cr,
            description=(f"B-series: baseline CPU={baseline}% of the VM, banks {cph} credits/hr, "
                         f"max {max_cr}. Sustained CPU above baseline drains the bank; at zero the VM is "
                         f"throttled to baseline."))
    prof = NormalizedProfile(
        resource_size_label = size_label,
        vcpus               = vcpus,
        memory_gb           = mem_gb,
        lifecycle_state     = power_state or "unknown",
        is_running          = is_run,
        is_idle_waste       = is_deallocated,
        burst_context       = burst_ctx,
    )

    if not cfg.get("os_disk_managed"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="RELIABILITY",
            finding="OS disk is UNMANAGED. Unmanaged disks store VHDs in storage accounts and lack Azure-managed snapshot/backup integration.",
            remediation="Migrate OS disk to Azure Managed Disks for better reliability, snapshot management, and performance SLAs.",
            context="Azure Managed Disks provide 99.999% availability SLA; unmanaged disks do not."
        ))

    if cfg.get("ip_forwarding"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="IP forwarding is ENABLED on the NIC. This allows the VM to route traffic not addressed to it.",
            remediation="Disable IP forwarding unless this VM is deliberately acting as a Network Virtual Appliance (NVA), router, or firewall.",
            context="IP forwarding enabled on non-NVA VMs is a common misconfiguration that can allow lateral movement in network attacks."
        ))

    if is_deallocated:
        prof.cost_findings.append(Finding(
            severity="HIGH", category="COST",
            finding=f"VM is DEALLOCATED (power_state={power_state}). Managed disks, static IPs, and other attached resources still incur charges.",
            remediation="Delete VM and its resources if unused, or automate shutdown schedules with Azure Auto-Shutdown.",
            context="Deallocated VMs do not incur compute charges, but attached managed disks ($0.04-0.17/GB/month) and reserved IPs continue billing."
        ))

    if is_burst:
        prof.performance_notes.append(Finding(
            severity="INFO", category="PERFORMANCE",
            finding=f"{vm_size} is a B-series (burstable) VM. CPU performance scales with accumulated credits.",
            remediation="Monitor CPU baseline credit balance. If consistently under credit pressure, migrate to Dsv5 series for consistent performance.",
            context="B-series VMs are cost-effective for bursty workloads. Sustained high CPU will deplete credits and throttle to base performance."
        ))

    if cfg.get("provisioning_state") not in ("Succeeded", None):
        prof.reliability_findings.append(Finding(
            severity="HIGH", category="RELIABILITY",
            finding=f"Provisioning state is '{cfg.get('provisioning_state')}' — VM may be in a failed or transitional state.",
            remediation="Check Azure portal for provisioning errors and attempt repair or redeploy.",
            context=""
        ))

    return prof


def _normalize_compute_engine(cfg: dict) -> NormalizedProfile:
    mtype = cfg.get("machine_type", "unknown")
    # Extract short name (may be full URL like zones/us-central1-a/machineTypes/e2-medium)
    mtype_short = mtype.split("/")[-1] if "/" in mtype else mtype
    specs = _GCP_SPECS.get(mtype_short)
    vcpus = None; mem_gb = None
    if specs:
        vcpus, mem_gb = specs[:2]

    status = cfg.get("status", "unknown")
    gcp_burst = BurstContext(is_burstable=False)
    if mtype_short in _GCP_BURST_SPECS and vcpus:
        cph, max_cr = _GCP_BURST_SPECS[mtype_short]
        baseline = round(cph / (vcpus * 60.0) * 100.0, 1)
        gcp_burst = BurstContext(
            is_burstable=True, baseline_cpu_pct=baseline, credits_per_hour_earned=cph, max_credits=max_cr,
            description=(f"Shared-core {mtype_short}: sustained CPU ~{baseline}% of the VM; bursts above that "
                         f"consume an internal (unexposed) credit pool, then the vCPU is throttled and "
                         f"scheduler wait time rises."))
    prof = NormalizedProfile(
        resource_size_label = f"{mtype_short} — {vcpus} vCPUs, {mem_gb} GB RAM" if vcpus else mtype_short,
        vcpus               = vcpus,
        memory_gb           = mem_gb,
        lifecycle_state     = status,
        is_running          = status == "RUNNING",
        is_idle_waste       = status == "TERMINATED",
        burst_context       = gcp_burst,
    )

    # Security — Shielded VM
    if not cfg.get("secure_boot"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Shielded VM Secure Boot is DISABLED. Boot firmware and OS kernel not verified on each boot.",
            remediation="Enable Secure Boot via GCP Console → Compute Engine → VM instance → Edit → Shielded VM.",
            context="Shielded VMs protect against boot-level rootkits and firmware attacks."
        ))

    if not cfg.get("integrity_monitoring"):
        prof.security_findings.append(Finding(
            severity="LOW", category="SECURITY",
            finding="Integrity Monitoring is DISABLED. Boot sequence integrity not being measured.",
            remediation="Enable Integrity Monitoring for the VM in Shielded VM settings.",
            context=""
        ))

    if cfg.get("can_ip_forward"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="IP forwarding (canIpForward) is ENABLED. Instance will forward packets not addressed to it.",
            remediation="Disable canIpForward unless this is a router/NAT/VPN instance.",
            context=""
        ))

    if cfg.get("boot_disk_auto_delete") is False:
        prof.reliability_findings.append(Finding(
            severity="INFO", category="COST",
            finding="Boot disk set to NOT auto-delete on VM termination. Manual cleanup required to avoid orphaned disk charges.",
            remediation="Review if boot disk retention is intentional (snapshots). If not, enable autoDelete.",
            context=""
        ))

    if cfg.get("preemptible") or cfg.get("provisioning_model") == "SPOT":
        prof.reliability_findings.append(Finding(
            severity="MEDIUM", category="RELIABILITY",
            finding="Instance is PREEMPTIBLE/SPOT. GCP can terminate it at any time with 30-second warning.",
            remediation="Ensure workload is fault-tolerant and idempotent. Add restart policies and health checks.",
            context="Spot VMs can be ~80% cheaper but require workloads that tolerate interruption."
        ))

    return prof


def _normalize_compute_oci(cfg: dict) -> NormalizedProfile:
    shape = cfg.get("shape", "unknown")
    vcpus = cfg.get("vcpus") or (cfg.get("ocpus") and int(float(cfg["ocpus"]) * 2)) or None
    mem_gb = cfg.get("memory_gb")
    state = cfg.get("lifecycle_state", "unknown")

    proc = cfg.get("processor_description", "")
    size_label = f"{shape} — {vcpus} vCPUs, {mem_gb} GB RAM ({proc})" if vcpus else shape

    prof = NormalizedProfile(
        resource_size_label = size_label,
        vcpus               = vcpus,
        memory_gb           = mem_gb,
        lifecycle_state     = state,
        is_running          = state == "RUNNING",
        is_idle_waste       = state in ("STOPPED", "TERMINATING"),
        is_encrypted        = bool(cfg.get("kms_key_id")),
        encryption_type     = "Customer-managed KMS" if cfg.get("kms_key_id") else "None",
        burst_context       = BurstContext(is_burstable=False),
    )

    if not cfg.get("legacy_imds_disabled"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="Legacy IMDS endpoints are NOT disabled. Older metadata API (v1) accessible without authentication headers.",
            remediation="Set instanceOptions.areLegacyImdsEndpointsDisabled=true via OCI CLI or console.",
            context="Similar to AWS IMDSv1 — SSRF + legacy IMDS can expose instance credentials."
        ))

    if cfg.get("monitoring_disabled"):
        prof.reliability_findings.append(Finding(
            severity="HIGH", category="OBSERVABILITY",
            finding="OCI Monitoring agent is DISABLED. No metrics flowing to OCI Monitoring service.",
            remediation="Enable monitoring agent in instance configuration: agentConfig.isMonitoringDisabled=false.",
            context="Without monitoring, CPU/memory/disk metrics are unavailable for alerting and this pipeline."
        ))

    if not cfg.get("encryption_in_transit"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Encryption in transit is NOT enabled. Block volume data transmitted between instance and storage unencrypted.",
            remediation="Enable isEncryptionInTransitEnabled in instance launch options (requires instance restart).",
            context=""
        ))

    return prof


def _normalize_ebs(cfg: dict) -> NormalizedProfile:
    vtype = cfg.get("volume_type", "unknown")
    size_gb = cfg.get("size_gb")
    iops = cfg.get("iops")
    status = cfg.get("status", "unknown")
    encrypted = _resolve_bool(cfg.get("encrypted"))
    is_orphaned = status == "available"  # "available" = not attached to any instance

    vspecs = _EBS_VOLUME_SPECS.get(vtype, {})
    size_label = f"EBS {vtype} {size_gb} GB"
    if iops:
        size_label += f" | {iops} IOPS"

    prof = NormalizedProfile(
        resource_size_label = size_label,
        storage_size_gb     = size_gb,
        iops_provisioned    = iops,
        lifecycle_state     = status,
        is_running          = status == "in-use",
        is_orphaned         = is_orphaned,
        is_encrypted        = encrypted,
        encryption_type     = "AES-256 (AWS managed)" if encrypted else "NONE",
        volume_type_specs   = vspecs,
    )

    # ── Security ─────────────────────────────────────────────────────────────
    if not encrypted:
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding=f"EBS volume is NOT encrypted. Data at rest is unprotected.",
            remediation=(
                "1. Create snapshot: aws ec2 create-snapshot --volume-id <id>\n"
                "2. Copy snapshot with encryption: aws ec2 copy-snapshot --encrypted --kms-key-id alias/aws/ebs\n"
                "3. Create new encrypted volume from snapshot and replace."
            ),
            context="Unencrypted EBS volumes violate most compliance frameworks (PCI-DSS, HIPAA, SOC 2). Enable default encryption in EC2 settings to prevent future unencrypted volumes."
        ))

    # ── Cost ─────────────────────────────────────────────────────────────────
    if is_orphaned:
        monthly_cost = round((size_gb or 0) * (vspecs.get("cost_per_gb") or 0.10), 2)
        prof.cost_findings.append(Finding(
            severity="HIGH", category="COST",
            finding=f"Volume status is 'available' — NOT ATTACHED to any instance. Orphaned disk accruing ${monthly_cost:.2f}/month.",
            remediation=(
                f"1. Verify it's truly unused: aws ec2 describe-volumes --volume-ids {cfg.get('volume_id', '<id>')}\n"
                "2. Create final snapshot if needed, then delete: aws ec2 delete-volume --volume-id <id>"
            ),
            context="Orphaned EBS volumes are a common cloud cost waste — they accumulate silently over time."
        ))

    if vtype == "gp2" and vspecs.get("upgrade_target") == "gp3":
        saving_pct = 20
        monthly_old = round((size_gb or 0) * 0.10, 2)
        monthly_new = round((size_gb or 0) * 0.08, 2)
        prof.cost_findings.append(Finding(
            severity="MEDIUM", category="COST",
            finding=f"Volume type gp2 — gp3 provides same/better performance at ${monthly_new:.2f}/month vs ${monthly_old:.2f}/month ({saving_pct}% saving).",
            remediation=f"aws ec2 modify-volume --volume-id {cfg.get('volume_id', '<id>')} --volume-type gp3  (zero-downtime, online conversion)",
            context="gp3 has 3,000 IOPS and 125 MB/s baseline included at no extra cost. gp2 burst model creates unpredictable latency under load."
        ))

    if vtype == "io1" and vspecs.get("upgrade_target") == "io2":
        prof.cost_findings.append(Finding(
            severity="LOW", category="COST",
            finding="io1 volume — io2 provides 100× better durability (99.999% vs 99.9%) at the same price.",
            remediation=f"aws ec2 modify-volume --volume-id {cfg.get('volume_id', '<id>')} --volume-type io2",
            context=""
        ))

    # ── Performance ───────────────────────────────────────────────────────────
    if vtype == "gp2" and size_gb and size_gb < 334:
        baseline_iops = size_gb * 3
        prof.performance_notes.append(Finding(
            severity="INFO", category="PERFORMANCE",
            finding=(
                f"gp2 volume ({size_gb} GB): baseline IOPS = {baseline_iops} (3 IOPS/GB). "
                f"Can burst to 3,000 IOPS for short periods using I/O credit model."
            ),
            remediation="If sustained IOPS > burst capacity is needed, convert to gp3 with explicit IOPS provisioning.",
            context="gp2 burst credit depletion causes sudden performance drops from 3,000 to baseline IOPS — this often manifests as application timeouts."
        ))

    if cfg.get("multi_attach") and vtype not in ("io1", "io2"):
        prof.reliability_findings.append(Finding(
            severity="HIGH", category="RELIABILITY",
            finding="Multi-Attach enabled on non-io1/io2 volume — unsupported configuration.",
            remediation="Multi-Attach is only supported on Provisioned IOPS (io1/io2) volumes. Disable or convert volume type.",
            context=""
        ))

    return prof


def _normalize_accounts(cfg: dict) -> NormalizedProfile:
    sku = cfg.get("sku_name", "unknown")
    prof = NormalizedProfile(
        resource_size_label = f"Azure Storage Account ({sku})",
        lifecycle_state     = cfg.get("status_primary", "unknown"),
        is_running          = cfg.get("status_primary") == "available",
        is_encrypted        = cfg.get("blob_encryption"),
        encryption_type     = cfg.get("encryption_key_source"),
    )

    if cfg.get("allow_blob_public_access"):
        prof.security_findings.append(Finding(
            severity="CRITICAL", category="SECURITY",
            finding="Public blob access is ALLOWED. Any container or blob can potentially be made public by any user with write access.",
            remediation="az storage account update --name <name> --resource-group <rg> --allow-blob-public-access false",
            context="Public blob access has been the root cause of numerous high-profile data breaches. Microsoft now defaults this to disabled."
        ))

    if cfg.get("network_default_action") == "Allow":
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="Storage Account network ACL default action is 'Allow' — accessible from ALL internet IPs.",
            remediation=(
                "Restrict to specific VNets/IPs:\n"
                "az storage account update --default-action Deny\n"
                "az storage account network-rule add --vnet-name <vnet> --subnet <subnet>"
            ),
            context="'Allow all' network policy on storage accounts means any credential leak (SAS token, key) grants worldwide access."
        ))

    tls = cfg.get("minimum_tls_version")
    if tls not in ("TLS1_2", "TLS1_3", None):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding=f"Minimum TLS version is '{tls}'. TLS 1.0/1.1 have known vulnerabilities (POODLE, BEAST).",
            remediation="az storage account update --name <name> --resource-group <rg> --min-tls-version TLS1_2",
            context=""
        ))

    if not cfg.get("https_only"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="HTTPS-only is NOT enforced. HTTP connections to this storage account are permitted.",
            remediation="az storage account update --name <name> --resource-group <rg> --https-only true",
            context="HTTP traffic transmits data and credentials in plaintext."
        ))

    if cfg.get("shared_key_access"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Shared Key (storage account key) access is enabled. If keys are leaked, full access to all data is possible.",
            remediation="Use Azure AD (RBAC) exclusively and disable shared key access once all applications use managed identities.",
            context=""
        ))

    return prof


def _normalize_storage_disks(cfg: dict) -> NormalizedProfile:
    sku = cfg.get("sku_name", "unknown")
    size_gb = cfg.get("disk_size_gb")
    iops = cfg.get("disk_iops")
    mbps = cfg.get("disk_mbps")
    state = cfg.get("disk_state", "unknown")
    enc = cfg.get("encryption_type")
    is_orphaned = state == "Unattached"

    size_label = f"Azure Managed Disk ({sku}) {size_gb} GB"
    if iops:
        size_label += f" | {iops} IOPS, {mbps} MB/s"

    prof = NormalizedProfile(
        resource_size_label      = size_label,
        storage_size_gb          = size_gb,
        iops_provisioned         = iops,
        throughput_mbps_provisioned = mbps,
        lifecycle_state          = state,
        is_running               = state in ("Attached", "ActiveSAS"),
        is_orphaned              = is_orphaned,
        is_encrypted             = enc is not None and "Unencrypted" not in (enc or ""),
        encryption_type          = enc,
    )

    if is_orphaned:
        monthly_cost = round((size_gb or 0) * 0.04, 2)
        prof.cost_findings.append(Finding(
            severity="HIGH", category="COST",
            finding=f"Disk state is 'Unattached'. Orphaned managed disk costing ~${monthly_cost:.2f}/month.",
            remediation=(
                "az disk delete --name <name> --resource-group <rg> --yes\n"
                "(Create a snapshot first if data may be needed: az snapshot create ...)"
            ),
            context="Unattached Azure disks are a common cost leak — they persist after VM deletion unless explicitly removed."
        ))

    if cfg.get("public_network_access") == "Enabled":
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="Public network access for disk export is ENABLED. Disk can be exported to unauthorized parties via SAS URL.",
            remediation="az disk update --name <name> --resource-group <rg> --public-network-access Disabled",
            context=""
        ))

    if enc and "PlatformManaged" in enc:
        prof.security_findings.append(Finding(
            severity="LOW", category="SECURITY",
            finding="Disk uses platform-managed encryption keys (PMK). Customer-managed keys (CMK) provide additional control.",
            remediation="Configure disk encryption set with customer-managed keys in Azure Key Vault for enhanced key control.",
            context=""
        ))

    return prof


def _normalize_efs(cfg: dict) -> NormalizedProfile:
    tmode = cfg.get("throughput_mode", "unknown")
    pmode = cfg.get("performance_mode", "unknown")
    size_bytes = cfg.get("size_bytes")
    size_gb = round(size_bytes / (1024**3), 2) if size_bytes else None
    mounts = cfg.get("number_of_mount_targets", 0)

    size_label = f"EFS ({pmode} / {tmode}) {size_gb} GB" if size_gb else f"EFS ({pmode} / {tmode})"
    prof = NormalizedProfile(
        resource_size_label = size_label,
        storage_size_gb     = int(size_gb) if size_gb else None,
        lifecycle_state     = cfg.get("lifecycle_state", "unknown"),
        is_running          = cfg.get("lifecycle_state") == "available",
        is_orphaned         = (mounts or 0) == 0,
        is_encrypted        = cfg.get("encrypted"),
        encryption_type     = "KMS" if cfg.get("kms_key_id") else ("SSE" if cfg.get("encrypted") else "None"),
    )

    if not cfg.get("encrypted"):
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding="EFS filesystem is NOT encrypted at rest.",
            remediation="EFS encryption cannot be enabled on existing filesystems. Create a new encrypted EFS and migrate data (AWS DataSync recommended).",
            context="Encryption at rest is required for HIPAA, PCI-DSS, SOC 2. Once created, EFS encryption cannot be toggled."
        ))

    if (mounts or 0) == 0 and cfg.get("lifecycle_state") == "available":
        prof.cost_findings.append(Finding(
            severity="HIGH", category="COST",
            finding="EFS filesystem has NO mount targets. No instances are mounting this filesystem — likely orphaned.",
            remediation="Verify no applications use this filesystem, then delete: aws efs delete-file-system --file-system-id <id>",
            context=f"EFS charges $0.30/GB-month (Standard). {size_gb} GB = ${round((size_gb or 0) * 0.30, 2):.2f}/month."
        ))

    if tmode == "bursting":
        prof.performance_notes.append(Finding(
            severity="INFO", category="PERFORMANCE",
            finding="EFS throughput mode is 'bursting'. Throughput scales with storage size and uses a burst credit model.",
            remediation="If sustained high throughput is needed, switch to 'elastic' or 'provisioned' throughput mode to avoid burst credit exhaustion.",
            context="Bursting mode provides 100 MiB/s burst per TB stored. Small filesystems (<1 TB) can burst to 100 MiB/s but may exhaust credits under sustained load."
        ))

    return prof


def _normalize_bucket_gcp(cfg: dict) -> NormalizedProfile:
    sc = cfg.get("storage_class", "STANDARD")
    pap = cfg.get("public_access_prevention")
    prof = NormalizedProfile(
        resource_size_label = f"GCP Storage Bucket ({sc})",
        lifecycle_state     = "active",
        is_running          = True,
        public_access_risk  = "none" if pap == "enforced" else ("medium" if pap == "inherited" else "high"),
    )

    if pap != "enforced":
        prof.security_findings.append(Finding(
            severity="HIGH", category="SECURITY",
            finding=f"Public access prevention is '{pap}' (not enforced). Bucket or individual objects can be made public.",
            remediation=(
                "gcloud storage buckets update gs://<bucket> --no-public-access-prevention  # ensure 'enforced'\n"
                "Or: gsutil pap set enforced gs://<bucket>"
            ),
            context="'Inherited' means IAM can still grant public access. 'Enforced' blocks all public IAM grants."
        ))

    if not cfg.get("uniform_bucket_level_access"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Uniform bucket-level access (UBLA) is DISABLED. Per-object ACLs coexist with IAM, increasing misconfiguration risk.",
            remediation="gsutil uniformbucketlevelaccess set on gs://<bucket>",
            context="Without UBLA, individual objects can have ACLs granting access beyond bucket IAM policies — hard to audit."
        ))

    if sc == "STANDARD":
        prof.cost_findings.append(Finding(
            severity="INFO", category="COST",
            finding="Storage class is STANDARD. If objects are accessed infrequently, cost savings are available.",
            remediation="Use Object Lifecycle Management to automatically migrate old objects to NEARLINE/COLDLINE/ARCHIVE.",
            context="STANDARD: $0.020/GB/month. NEARLINE (>30 days): $0.010. COLDLINE (>90 days): $0.004. ARCHIVE (>365 days): $0.0012."
        ))

    return prof


def _normalize_recovery_services(cfg: dict) -> NormalizedProfile:
    sku = cfg.get("sku_name", "unknown")
    pe_backup = cfg.get("private_endpoint_backup", "None")
    prof = NormalizedProfile(
        resource_size_label = f"Azure Recovery Services Vault ({sku})",
        lifecycle_state     = cfg.get("provisioning_state", "unknown"),
        is_running          = cfg.get("provisioning_state") == "Succeeded",
    )

    if pe_backup in ("None", None, ""):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="Recovery Services vault has no private endpoint for backup traffic. Backup data transits over public internet.",
            remediation="Configure Private Endpoint in the vault networking settings to route backup traffic through a private IP.",
            context="Without private endpoints, backup traffic traverses the public internet, increasing exposure during transmission."
        ))

    return prof


def _normalize_file_storage(cfg: dict) -> NormalizedProfile:
    metered = cfg.get("metered_bytes")
    size_gb = round(metered / (1024**3), 2) if metered else None
    state = cfg.get("lifecycle_state", "unknown")
    prof = NormalizedProfile(
        resource_size_label = f"OCI File Storage {size_gb} GB" if size_gb else "OCI File Storage",
        storage_size_gb     = int(size_gb) if size_gb else None,
        lifecycle_state     = state,
        is_running          = state == "ACTIVE",
        is_encrypted        = bool(cfg.get("kms_key_id")),
        encryption_type     = "Customer-managed KMS" if cfg.get("kms_key_id") else "None",
        is_orphaned         = state in ("DELETED", "DELETING"),
    )

    if not cfg.get("kms_key_id"):
        prof.security_findings.append(Finding(
            severity="MEDIUM", category="SECURITY",
            finding="OCI File Storage is using Oracle-managed encryption keys (not customer-managed).",
            remediation="Assign a customer-managed KMS key for full key lifecycle control and compliance.",
            context=""
        ))

    if cfg.get("is_clone_parent") and not cfg.get("is_hydrated"):
        prof.reliability_findings.append(Finding(
            severity="MEDIUM", category="RELIABILITY",
            finding="This file system is a clone parent and is NOT fully hydrated. Deleting the parent before child clones are hydrated risks data loss.",
            remediation="Ensure all dependent clones are hydrated (isHydrated=true) before any maintenance on this filesystem.",
            context=""
        ))

    return prof


def _normalize_s3(cfg: dict) -> NormalizedProfile:
    return NormalizedProfile(
        resource_size_label = f"S3 Bucket ({cfg.get('location', 'unknown region')})",
        lifecycle_state     = "active",
        is_running          = True,
    )


def _resolve_bool(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


_NORMALIZERS = {
    "EC2":               _normalize_ec2,
    "Lambda":            _normalize_lambda,
    "Virtual_Machines":  _normalize_virtual_machines,
    "Compute_Engine":    _normalize_compute_engine,
    "Compute":           _normalize_compute_oci,
    "EBS":               _normalize_ebs,
    "Accounts":          _normalize_accounts,
    "Storage_Disks":     _normalize_storage_disks,
    "EFS":               _normalize_efs,
    "Bucket":            _normalize_bucket_gcp,
    "Recovery_Services": _normalize_recovery_services,
    "File_Storage":      _normalize_file_storage,
    "S3":                _normalize_s3,
}
