"""
Playbooks -- the ONLY place where remediation advice is written.

A playbook turns a root-cause id (decided by analysis/rca.py) plus the resource's facts into
an ordered list of HUMAN-EXECUTED recommendations.  Nothing here runs anything:

  * every action carries `automated: False` and `requires_approval: True`;
  * commands are suggestions for an operator (read-only diagnostics are marked `mutating: False`,
    changes are marked `mutating: True`; anything disruptive is flagged `disruptive: True`);
  * `<placeholders>` mark values the pipeline cannot know (ASG / VMSS / MIG names, volume ids ...).

The LLM never writes or alters these actions - it only explains them (llm/explainer.py).
`validate_actions()` is the safety net: no playbook may contain a destroy/terminate/delete command.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

# ── resize ladders (next size in the same family) ─────────────────────────────
_NEXT_SIZE = {
    "AWS": {"t3.small": "t3.medium", "t3.medium": "t3.large", "m5.large": "m5.xlarge", "c5.large": "c5.xlarge",
            "r5.large": "r5.xlarge", "m5.xlarge": "m5.2xlarge"},
    "Azure": {"Standard_B2s": "Standard_B2ms", "Standard_B2ms": "Standard_B4ms",
              "Standard_D2s_v5": "Standard_D4s_v5", "Standard_D4s_v5": "Standard_D8s_v5",
              "Standard_E2s_v5": "Standard_E4s_v5", "Standard_F2s_v2": "Standard_F4s_v2"},
    "GCP": {"e2-small": "e2-medium", "e2-medium": "e2-standard-2", "e2-standard-2": "e2-standard-4",
            "n2-standard-2": "n2-standard-4", "n2-standard-4": "n2-standard-8"},
}
# non-burstable replacement for a burstable type
_NON_BURST = {"AWS": {"t3.small": "m5.large", "t3.medium": "m5.large"},
              "Azure": {"Standard_B2s": "Standard_D2s_v5", "Standard_B2ms": "Standard_D2s_v5"},
              "GCP": {"e2-small": "e2-standard-2", "e2-medium": "e2-standard-2"}}

_FORBIDDEN = re.compile(
    r"(terminate-instances|delete-|\bdelete\b|destroy|deallocate|--force|rm\s+-rf|drop\s+table|"
    r"instances\s+delete|vm\s+delete)", re.I)


@dataclass
class PB:
    """Playbook context: everything provider-specific in one place."""
    provider: str
    resource_id: str
    name: str
    resource_type: str
    region: str = ""
    zone: str = ""
    rg: str = ""
    instance_type: str = ""
    vcpus: Optional[int] = None
    mem_gb: Optional[float] = None
    data_volume: str = "<volume-id>"
    data_disk: str = "<data-disk-name>"
    data_disk_gb: Optional[int] = None
    facts: dict = field(default_factory=dict)
    root_facts: dict = field(default_factory=dict)      # rca.facts

    @property
    def next_size(self) -> str:
        return _NEXT_SIZE.get(self.provider, {}).get(self.instance_type, "<next-size-up>")

    @property
    def non_burst(self) -> str:
        return _NON_BURST.get(self.provider, {}).get(self.instance_type, "<non-burstable-size>")

    @property
    def new_disk_gb(self):
        return int(math.ceil(self.data_disk_gb * 1.5 / 10.0) * 10) if self.data_disk_gb else "<size-gb-plus-50%>"


def make_pb(profile: dict, provider: str, rca_facts: dict) -> PB:
    cfg = profile.get("config") or {}
    rid = profile["_id"]
    name = profile.get("resource_name") or rid
    if provider == "AWS":
        zone = cfg.get("availability_zone") or profile.get("location") or ""
        pb = PB(provider, rid, name, "EC2", region=zone[:-1] if zone[-1:].isalpha() else zone, zone=zone,
                instance_type=cfg.get("instance_type") or "")
        vols = cfg.get("data_volume_ids") or cfg.get("volume_ids") or []
        if vols:
            pb.data_volume = vols[-1]
    elif provider == "Azure":
        m = re.search(r"/resourceGroups/([^/]+)/", rid, re.I)
        pb = PB(provider, rid, name, "Virtual_Machines", region=profile.get("location") or "",
                rg=m.group(1) if m else "<resource-group>", instance_type=cfg.get("vm_size") or "")
        dd = cfg.get("data_disks") or []
        if dd:
            pb.data_disk, pb.data_disk_gb = dd[0].get("name") or pb.data_disk, dd[0].get("size_gb")
    else:
        zone = (cfg.get("zone") or profile.get("location") or "").split("/")[-1]
        pb = PB(provider, rid, cfg.get("instance_name") or name, "Compute_Engine", zone=zone,
                region=zone.rsplit("-", 1)[0] if zone.count("-") >= 2 else zone,
                instance_type=(cfg.get("machine_type") or "").split("/")[-1])
        dd = cfg.get("data_disks") or []
        if dd:
            pb.data_disk, pb.data_disk_gb = dd[0].get("name") or pb.data_disk, dd[0].get("size_gb")
    pb.root_facts = rca_facts or {}
    pb.facts = rca_facts or {}
    return pb


# ── command helpers ───────────────────────────────────────────────────────────

def _cmd(purpose, command, mutating=False):
    return {"purpose": purpose, "command": command, "mutating": mutating}


def sh(pb: PB, purpose: str, script: str) -> dict:
    """Run a (quote-free, read-only) shell script on the VM through the provider's remote-exec channel."""
    if pb.provider == "AWS":
        return _cmd(purpose, "aws ssm send-command --instance-ids " + pb.resource_id +
                    " --document-name AWS-RunShellScript --parameters '{\"commands\":[\"" + script + "\"]}'")
    if pb.provider == "Azure":
        return _cmd(purpose, f'az vm run-command invoke -g {pb.rg} -n {pb.name} --command-id RunShellScript --scripts "{script}"')
    return _cmd(purpose, f'gcloud compute ssh {pb.name} --zone {pb.zone} --command "{script}"')


def metric_history(pb: PB, purpose="Pull the raw metric to confirm the pattern") -> dict:
    if pb.provider == "AWS":
        return _cmd(purpose, "aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization "
                    f"--dimensions Name=InstanceId,Value={pb.resource_id} --start-time <ISO-start> --end-time <ISO-end> "
                    "--period 300 --statistics Average Maximum")
    if pb.provider == "Azure":
        return _cmd(purpose, f'az monitor metrics list --resource "{pb.resource_id}" --metric "Percentage CPU" '
                    "--interval PT5M --aggregation Average Maximum --offset 24h")
    return _cmd(purpose, f"gcloud compute instances describe {pb.name} --zone {pb.zone} --format='value(status,machineType)'")


def resize_cmds(pb: PB, target: str):
    if pb.provider == "AWS":
        return [_cmd("Stop the instance (brief outage)", f"aws ec2 stop-instances --instance-ids {pb.resource_id}", True),
                _cmd("Change instance type", f"aws ec2 modify-instance-attribute --instance-id {pb.resource_id} "
                     f"--instance-type \"{{\\\"Value\\\": \\\"{target}\\\"}}\"", True),
                _cmd("Start the instance", f"aws ec2 start-instances --instance-ids {pb.resource_id}", True)]
    if pb.provider == "Azure":
        return [_cmd("Resize (the VM restarts)", f"az vm resize -g {pb.rg} -n {pb.name} --size {target}", True)]
    return [_cmd("Stop the instance (brief outage)", f"gcloud compute instances stop {pb.name} --zone {pb.zone}", True),
            _cmd("Change machine type", f"gcloud compute instances set-machine-type {pb.name} --zone {pb.zone} --machine-type {target}", True),
            _cmd("Start the instance", f"gcloud compute instances start {pb.name} --zone {pb.zone}", True)]


def scale_out_cmds(pb: PB):
    if pb.provider == "AWS":
        return [_cmd("Find the Auto Scaling group of this instance", f"aws autoscaling describe-auto-scaling-instances --instance-ids {pb.resource_id}"),
                _cmd("Add one node (set N+1)", "aws autoscaling set-desired-capacity --auto-scaling-group-name <asg-name> --desired-capacity <N+1>", True)]
    if pb.provider == "Azure":
        return [_cmd("Find the scale set / backend pool", f"az vmss list -g {pb.rg} -o table"),
                _cmd("Add one node (set N+1)", f"az vmss scale -g {pb.rg} -n <vmss-name> --new-capacity <N+1>", True)]
    return [_cmd("Find the managed instance group", f"gcloud compute instance-groups managed list --filter=zone:{pb.zone}"),
            _cmd("Add one node (set N+1)", f"gcloud compute instance-groups managed resize <mig-name> --zone {pb.zone} --size <N+1>", True)]


def flow_log_cmds(pb: PB, direction: str):
    key = "srcAddr" if direction == "in" else "dstAddr"
    if pb.provider == "AWS":
        return [_cmd("Top talkers from VPC flow logs (CloudWatch Logs Insights)",
                     "aws logs start-query --log-group-name <vpc-flow-log-group> --start-time <epoch-start> --end-time <epoch-end> "
                     f"--query-string \"filter interfaceId = '<eni-id>' | stats sum(bytes) as b by {key} | sort b desc | limit 20\"")]
    if pb.provider == "Azure":
        return [_cmd("Check NSG flow-log configuration (then query Traffic Analytics for top talkers)",
                     f"az network watcher flow-log list --location {pb.region} -o table")]
    return [_cmd("Top talkers from VPC flow logs",
                 "gcloud logging read 'resource.type=\"gce_subnetwork\" AND logName:\"vpc_flows\"' --freshness=3h --limit=50 --format=json")]


def change_audit_cmd(pb: PB):
    if pb.provider == "AWS":
        return _cmd("Recent control-plane changes touching this instance", "aws cloudtrail lookup-events --lookup-attributes "
                    f"AttributeKey=ResourceName,AttributeValue={pb.resource_id} --max-results 20")
    if pb.provider == "Azure":
        return _cmd("Recent control-plane changes in the resource group", f"az monitor activity-log list -g {pb.rg} --offset 6h -o table")
    return _cmd("Recent control-plane changes", "gcloud logging read 'protoPayload.serviceName=\"compute.googleapis.com\" AND protoPayload.methodName:\"compute.\"' --freshness=6h --limit=20")


def _act(phase, kind, title, detail, commands=None, disruptive=False, effect=""):
    return {"phase": phase, "kind": kind, "title": title, "detail": detail,
            "commands": commands or [], "disruptive": disruptive, "expected_effect": effect,
            "requires_approval": True, "automated": False}


def _f(x, nd=1, unit=""):
    return "n/a" if x is None else f"{x:.{nd}f}{unit}"


# ── the playbooks ─────────────────────────────────────────────────────────────

def pb_cpu_traffic_surge(pb: PB):
    f = pb.facts
    cpu = (f.get("cpu_pct") or {})
    return dict(
        title=f"CPU saturation from a traffic surge on {pb.name}",
        summary=(f"CPU peaked at {_f(cpu.get('max'), 0, '%')} while inbound traffic ran well above its normal level - "
                 "the box is doing exactly what it should, it is simply out of capacity for the current load."),
        actions=[
            _act("now", "mitigate", "Add capacity to the tier behind the load balancer",
                 "Bring one extra node into service (or raise the autoscaling floor) so the load spreads. This is the "
                 "fastest, lowest-risk relief because the extra load is legitimate-looking traffic.",
                 scale_out_cmds(pb), effect="CPU per node drops roughly in proportion to the added nodes"),
            _act("now", "investigate", "Confirm the surge is legitimate",
                 "Check the load balancer / access logs for the top clients and paths. A marketing event or a retry storm "
                 "needs capacity; a single abusive client needs rate limiting instead.",
                 flow_log_cmds(pb, "in") + [sh(pb, "Live connection summary", "ss -s")]),
            _act("fix", "capacity", "Right-size or raise autoscaling limits if the surge repeats",
                 f"If this load level is the new normal, move to the next size ({pb.instance_type} -> {pb.next_size}) or "
                 "lower the CPU target of the scaling policy so nodes are added earlier.",
                 resize_cmds(pb, pb.next_size), disruptive=True),
            _act("prevent", "config", "Alert on the leading indicator",
                 "Add a network-in anomaly alert (already firing here) to the on-call route for this tier so the surge is "
                 "handled before CPU saturates."),
        ],
        do_not=["Do not restart the application - the process is healthy, it is overloaded.",
                "Do not resize only this one node if its peers are equally loaded; add nodes to the tier."],
        verify="CPU falls below 75% within ~15 minutes of the extra capacity joining and network-in per node drops.",
        risk={"1h": "Latency and error rates rise as requests queue on saturated CPUs.",
              "24h": "Timeouts cascade to downstream tiers.", "7d": "Repeated surges without capacity change cause customer-visible outages."},
    )


def pb_cpu_runaway(pb: PB):
    cpu = (pb.facts.get("cpu_pct") or {})
    return dict(
        title=f"Runaway process suspected on {pb.name}",
        summary=(f"CPU is pinned near {_f(cpu.get('max'), 0, '%')} on a flat plateau while traffic and memory are normal - "
                 "the load is coming from something running on the machine, not from users."),
        actions=[
            _act("now", "investigate", "Identify the consuming process",
                 "List the top CPU consumers with their start time; a process whose start time matches the moment the plateau "
                 "began (deploy, cron, backup, agent update) is the culprit.",
                 [sh(pb, "Top CPU processes", "ps -eo pid,ppid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"),
                  sh(pb, "Cron / timers that started recently", "systemctl list-timers --all | head -20")]),
            _act("now", "mitigate", "Stop or throttle the offending job (after confirming it is safe)",
                 "If the process is a batch / maintenance job, pause it or lower its priority (nice) first; restart the service "
                 "only if it is a spinning worker. Coordinate with the job's owner.",
                 [sh(pb, "Lower priority of a specific PID (replace <pid>)", "renice +10 -p <pid>")], disruptive=True),
            _act("fix", "config", "Review what changed at the plateau start",
                 "Compare the plateau start time with deployments and configuration changes.",
                 [change_audit_cmd(pb)]),
            _act("prevent", "config", "Cap the job's CPU (cgroup / systemd CPUQuota) and add a runtime limit",
                 "Prevents one process from taking the whole VM again."),
        ],
        do_not=["Do not scale the VM up - traffic is normal, more CPU would just be consumed by the same process.",
                "Do not reboot as a first step: it destroys the evidence (which process, which arguments)."],
        verify="CPU returns to its usual daily shape and the flat plateau disappears.",
        risk={"1h": "Legitimate work on the VM is starved and latency rises.", "24h": "Health checks may start failing and the node be taken out of service.",
              "7d": "If the job is a leak or a loop it will recur after every restart."},
    )


def pb_cpu_recurring(pb: PB):
    cpu = (pb.facts.get("cpu_pct") or {})
    return dict(
        title=f"Scheduled load repeatedly saturates CPU on {pb.name}",
        summary=("The same alert fires at the same weekday and hour again and again - this is a schedule "
                 "(batch job, backup, report), not a fault."),
        actions=[
            _act("now", "investigate", "Find the scheduled job that starts at that time",
                 "Match the alert start time with cron / timers / orchestrator schedules.",
                 [sh(pb, "Cron entries", "crontab -l; ls /etc/cron.d"), sh(pb, "systemd timers", "systemctl list-timers --all | head -20")]),
            _act("fix", "capacity", "Give the job its own capacity or move it to an off-peak window",
                 f"Run it on a larger/separate node ({pb.instance_type} -> {pb.next_size}) or spread it over a longer window "
                 "with a lower CPU share.", resize_cmds(pb, pb.next_size), disruptive=True),
            _act("prevent", "config", "Tune the alert for the known window",
                 "Add a maintenance-window suppression or a job-aware threshold so the on-call is not paged for expected load, "
                 "and keep a paging alert for the job running longer than usual."),
        ],
        do_not=["Do not treat every occurrence as an incident - fix the schedule/capacity once.",
                "Do not disable the alert entirely; keep a duration-based alert."],
        verify="Next scheduled run finishes with CPU below 75%, or the alert is suppressed inside the agreed window.",
        risk={"1h": "Job duration stretches and overlaps other work.", "24h": "Recurring pages train on-call to ignore the alert.",
              "7d": "Job growth eventually causes a missed deadline."},
    )


def pb_upstream(pb: PB):
    rf = pb.root_facts
    up = rf.get("upstream_resource_name", "the upstream tier")
    nodes = ", ".join(rf.get("upstream_nodes") or [up])
    return dict(
        title=f"{pb.name}: symptoms are downstream of a problem on {up}",
        summary=(f"CPU here rose because the upstream tier ({nodes}) alerted first and passed the extra load down. "
                 "Fixing this resource alone would not remove the cause."),
        actions=[
            _act("now", "escalate", f"Work the incident on {up} first",
                 "Follow the recommendation on the upstream resource (add capacity / rate-limit at the edge). This resource is a "
                 "symptom; it will recover as the upstream load normalises."),
            _act("now", "investigate", "Watch this tier while the upstream fix lands",
                 "Track CPU and connection counts here; only if they stay high after the upstream load is back to normal treat "
                 "this as a separate problem.",
                 [sh(pb, "Connection summary", "ss -s"), sh(pb, "Top CPU processes", "ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -10")]),
            _act("prevent", "config", "Add back-pressure between the tiers",
                 "Connection limits / queue depth alerts between tiers keep an upstream surge from saturating this tier."),
        ],
        do_not=["Do not resize or restart this resource as the first move - it will not remove the cause.",
                "Do not open a separate root-cause investigation before the upstream incident is handled."],
        verify="This resource's CPU follows the upstream tier back below 75% without any change made here.",
        risk={"1h": "Errors propagate across tiers.", "24h": "Two teams debug the same incident separately.", "7d": "Same chain repeats."},
    )


def pb_memory_leak(pb: PB):
    m = pb.facts.get("memory_used_pct") or {}
    slope = m.get("slope_7d")
    days_left = None
    if slope and slope > 0 and m.get("avg") is not None:
        days_left = max((100.0 - m["avg"]) / slope, 0)
    txt = (f" At the current slope memory would reach 100% in about {days_left:.0f} day(s) (trend extrapolation, for urgency only)."
           if days_left is not None else "")
    return dict(
        title=f"Memory leak pattern on {pb.name}",
        summary=(f"Memory has grown {_f(slope, 2)} points/day for a week in a straight line (now ~{_f(m.get('avg'), 0, '%')}), "
                 f"independent of traffic - the signature of a leak.{txt}"),
        actions=[
            _act("now", "investigate", "Find the process that owns the growth",
                 "Compare resident memory of the top processes now vs. the deploy that started the climb; capture a heap "
                 "profile/dump of the suspect while it is still growing.",
                 [sh(pb, "Top memory consumers", "ps -eo pid,rss,pmem,etime,comm --sort=-rss | head -15; free -m")]),
            _act("now", "mitigate", "Schedule a controlled restart of the leaking service in a maintenance window",
                 "A rolling restart resets memory and buys time. Do it before memory reaches the OOM-kill zone (90%+), one node at a time.",
                 disruptive=True, effect="Memory drops back to its post-deploy level; the leak resumes unless fixed"),
            _act("fix", "capacity", "Temporary headroom: move to the next size while the fix is developed",
                 f"{pb.instance_type} -> {pb.next_size} gives days of headroom. Treat it as a stopgap, not a fix.",
                 resize_cmds(pb, pb.next_size), disruptive=True),
            _act("fix", "config", "Ship the code fix and set a memory limit / restart policy",
                 "Bisect releases around the moment the slope started; add a container/systemd memory limit so a leak cannot "
                 "take the whole VM."),
            _act("prevent", "config", "Alert on the slope, not just the level",
                 "A trend alert (memory rising >0.5 points/day for 3 days) catches leaks days before the threshold."),
        ],
        do_not=["Do not add CPU capacity - CPU pressure here is a consequence of garbage-collection/swap, not the cause.",
                "Do not restart during peak traffic hours."],
        verify="After the restart, memory returns to its pre-incident level and no longer climbs day over day.",
        risk={"1h": "Swap/GC thrash raises CPU and latency.", "24h": "OOM-killer terminates the process unexpectedly.",
              "7d": "Repeated crashes and data loss for in-memory state."},
    )


def pb_memory_step(pb: PB):
    m = pb.facts.get("memory_used_pct") or {}
    return dict(
        title=f"Memory level stepped up on {pb.name}",
        summary=(f"Steady-state memory jumped to ~{_f(m.get('avg'), 0, '%')} in one step and is flat since - a release or configuration "
                 "change raised the footprint; it is not leaking."),
        actions=[
            _act("now", "investigate", "Correlate the step with a change",
                 "Find the deployment / config change that landed at the step time (new cache size, larger heap, new dependency).",
                 [change_audit_cmd(pb), sh(pb, "Top memory consumers", "ps -eo pid,rss,pmem,etime,comm --sort=-rss | head -15; free -m")]),
            _act("fix", "config", "Roll back or tune the change",
                 "If the extra memory is not intended, roll the release back or reduce the cache/heap setting. If intended, "
                 "update capacity and the alert baseline."),
            _act("fix", "capacity", "Right-size if the new footprint is permanent",
                 f"{pb.instance_type} -> {pb.next_size} restores headroom.", resize_cmds(pb, pb.next_size), disruptive=True),
        ],
        do_not=["Do not schedule restarts as a fix - memory will simply return to the new level.",
                "Do not hunt a leak: the flat shape after the step rules it out."],
        verify="Memory returns to its previous level after rollback, or stays flat with >=25% headroom after resizing.",
        risk={"1h": "Little immediate risk - memory is flat.", "24h": "Peak-hour usage may cross 90% and trigger swapping.",
              "7d": "No headroom for the next traffic increase."},
    )


def pb_credit(pb: PB):
    cpu = pb.facts.get("cpu_pct") or {}
    aws = pb.provider == "AWS"
    acts = [
        _act("now", "investigate", "Confirm throttling and see what drives the sustained demand",
             "CPU is pinned at the baseline while the credit balance is empty - work is being throttled. Find what is using CPU "
             "for hours a day.",
             [sh(pb, "Top CPU processes", "ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"), metric_history(pb)]),
    ]
    if aws:
        acts.append(_act("now", "mitigate", "Switch the instance to unlimited credit mode (immediate relief, may add cost)",
                         "Unlimited mode removes the throttle immediately; surplus credits are billed. No restart needed.",
                         [_cmd("Enable unlimited credits", f"aws ec2 modify-instance-credit-specification --instance-credit-specification \"InstanceId={pb.resource_id},CpuCredits=unlimited\"", True)],
                         effect="Throttling stops; CPU can burst above baseline again"))
    acts.append(_act("fix", "capacity", "Move the workload to a non-burstable size",
                     f"The sustained demand exceeds the burst baseline ({pb.instance_type}). {pb.non_burst} has no credit model and "
                     "is cheaper than paying for unlimited bursting long-term.", resize_cmds(pb, pb.non_burst), disruptive=True))
    acts.append(_act("prevent", "config", "Alert while there is still balance",
                     "Alert at ~50% of the maximum balance and on a falling multi-day trend, not only at empty."))
    return dict(
        title=f"Burstable CPU capacity exhausted on {pb.name}",
        summary=(f"Demand has exceeded the burst baseline for days, the credit balance reached zero and CPU is now capped "
                 f"at ~{_f(cpu.get('avg'), 0, '%')}. Performance drops even though CPU looks 'moderate'."),
        actions=acts,
        do_not=["Do not reboot - credits are not restored by a restart.",
                "Do not read the flat CPU line as 'healthy': it is the throttle."],
        verify="Credit balance (or scheduler wait) recovers and CPU can exceed the baseline during peaks.",
        risk={"1h": "Requests slow to baseline-speed CPU.", "24h": "Queues build, timeouts appear.", "7d": "Recurring degradation every busy day."},
    )


def pb_disk_growth(pb: PB):
    d = pb.facts.get("disk_used_pct") or {}
    slope = d.get("slope_7d")
    days_left = (100.0 - d["avg"]) / slope if slope and slope > 0 and d.get("avg") is not None else None
    txt = f" At this rate the volume is full in about {days_left:.0f} day(s) (trend extrapolation, for urgency only)." if days_left is not None else ""
    grow = [_cmd("Grow the data disk", {"AWS": f"aws ec2 modify-volume --volume-id {pb.data_volume} --size {pb.new_disk_gb}",
                                      "Azure": f"az disk update -g {pb.rg} -n {pb.data_disk} --size-gb {pb.new_disk_gb}",
                                      "GCP": f"gcloud compute disks resize {pb.data_disk} --zone {pb.zone} --size {pb.new_disk_gb}"}[pb.provider], True),
            _cmd("Then extend the partition/filesystem on the host (check lsblk first)",
                 "sudo growpart /dev/<disk> <part#> && sudo resize2fs /dev/<partition>   # xfs: sudo xfs_growfs -d <mountpoint>", True)]
    return dict(
        title=f"Disk filling steadily on {pb.name}",
        summary=(f"Disk usage climbs {_f(slope, 2)} points/day in a smooth line (now ~{_f(d.get('avg'), 0, '%')}) - "
                 f"logs/temp/data accumulating faster than it is cleaned.{txt}"),
        actions=[
            _act("now", "investigate", "Find what is growing",
                 "Largest directories and the log volume; steady growth is almost always unrotated logs, temp files or a data set.",
                 [sh(pb, "Largest directories", "df -h; du -xh / --max-depth=2 2>/dev/null | sort -rh | head -25"),
                  sh(pb, "Log volume", "du -sh /var/log/* 2>/dev/null | sort -rh | head; journalctl --disk-usage")]),
            _act("now", "mitigate", "Free space safely (rotate/compress/archive - never delete blindly)",
                 "Force a log rotation, compress or ship old logs to object storage, vacuum the journal. Keep at least 15% free.",
                 [sh(pb, "Rotate logs now", "logrotate -f /etc/logrotate.conf"),
                  sh(pb, "Trim the journal to 7 days", "journalctl --vacuum-time=7d")], effect="Immediate headroom; growth continues"),
            _act("fix", "capacity", "Extend the volume (online)",
                 "Add ~50% capacity so the retention fix is not urgent.", grow, disruptive=False),
            _act("prevent", "config", "Fix retention at the source",
                 "Add/repair logrotate, set retention on the data, and add a disk-growth-rate alert."),
        ],
        do_not=["Do not delete files by hand to 'free space' without identifying them - open handles keep space allocated anyway.",
                "Do not ignore it because the alert is only a Warning: growth is linear and will hit 100%."],
        verify="Disk usage drops below 75% and the daily growth rate falls to near zero.",
        risk={"1h": "Low if below 90%.", "24h": "Writes fail (logs, database) once the volume is full.",
              "7d": "Service outage / database corruption risk when the disk hits 100%."},
    )


def pb_disk_sudden(pb: PB):
    d = pb.facts.get("disk_used_pct") or {}
    return dict(
        title=f"Disk filled suddenly on {pb.name}",
        summary=(f"Disk usage jumped within a few hours to ~{_f(d.get('max'), 0, '%')} together with a burst of writes - a dump, export, "
                 "backup or runaway writer, not gradual growth."),
        actions=[
            _act("now", "investigate", "Find the newly created large files and the writer",
                 "Look for files created in the last day and the process holding them open.",
                 [sh(pb, "Big recent files", "find / -xdev -type f -size +200M -mmin -1440 | head -20"),
                  sh(pb, "Largest directories", "df -h; du -xh / --max-depth=2 2>/dev/null | sort -rh | head -20"),
                  sh(pb, "Who is writing", "ps -eo pid,pcpu,comm --sort=-pcpu | head -10")]),
            _act("now", "mitigate", "Stop the writer, then move or remove the artifact (after confirming what it is)",
                 "If it is a core dump / failed export / stuck backup, stop the job first, then archive the file off-box before "
                 "removing it.", disruptive=True),
            _act("fix", "config", "Prevent recurrence",
                 "Cap core dumps (ulimit / systemd-coredump limits), add quotas or a size guard to the export/backup job."),
            _act("prevent", "config", "Alert on write rate spikes",
                 "A disk-write anomaly alert would have fired hours before the volume filled."),
        ],
        do_not=["Do not simply extend the volume before identifying the writer - a runaway writer will fill the larger disk too.",
                "Do not delete database files or logs blindly."],
        verify="Disk usage returns to its previous level and the write rate returns to baseline.",
        risk={"1h": "Writes start failing if usage passes 95%.", "24h": "Application and database errors.", "7d": "Repeat when the job runs again."},
    )


def pb_net_ingress(pb: PB):
    n = pb.facts.get("network_in_bytes") or {}
    return dict(
        title=f"Abrupt inbound traffic anomaly on {pb.name}",
        summary=(f"Inbound traffic stepped up to about {_f(n.get('ratio_max'), 1)}x its normal level within an hour and stayed flat - "
                 "human traffic ramps, this looks like automation (scan, bot, attack or a misbehaving client)."),
        actions=[
            _act("now", "investigate", "Identify the sources",
                 "Top source addresses / paths from flow logs and access logs; check whether they are known clients.",
                 flow_log_cmds(pb, "in") + [sh(pb, "Connections by state", "ss -s")]),
            _act("now", "mitigate", "Rate-limit or block at the edge (WAF / firewall), not on the VM",
                 "Apply a rate rule or a source block at the load balancer / WAF / firewall for the offending sources.",
                 [{"AWS": _cmd("Review security group rules", "aws ec2 describe-security-groups --filters Name=group-name,Values=<sg-name>"),
                   "Azure": _cmd("Review NSG rules", f"az network nsg rule list -g {pb.rg} --nsg-name <nsg-name> -o table"),
                   "GCP": _cmd("Review firewall rules", "gcloud compute firewall-rules list --format=table(name,sourceRanges.list(),allowed[].map().firewall_rule().list())")}[pb.provider]],
                 effect="Inbound rate returns to normal without touching the VM"),
            _act("fix", "config", "Add a WAF / rate-limit policy permanently",
                 "Cloud WAF or Cloud Armor style rules and per-client rate limits."),
            _act("prevent", "config", "Route the network anomaly alert to security",
                 "This pattern is a security signal even when CPU is fine."),
        ],
        do_not=["Do not scale the VM up to absorb it - you would pay to serve unwanted traffic.",
                "Do not block by broad ranges before you know the sources (risk of blocking real customers)."],
        verify="Inbound traffic returns to its seasonal band and the step disappears from the hourly series.",
        risk={"1h": "CPU and bandwidth costs rise; service may degrade if the traffic grows.", "24h": "Possible application-layer abuse or data scraping.",
              "7d": "Repeated probing may turn into a targeted attack."},
    )


def pb_net_egress(pb: PB):
    n = pb.facts.get("network_out_bytes") or {}
    return dict(
        title=f"Outbound traffic spike on {pb.name} with normal inbound",
        summary=(f"Outbound traffic ran about {_f(n.get('ratio_max'), 1)}x its baseline for hours while inbound and CPU stayed normal - "
                 "data is leaving the VM without a matching request load (bulk copy, backup, or exfiltration-like behaviour)."),
        actions=[
            _act("now", "investigate", "Find the destination and the process",
                 "Which remote addresses receive the data, and which process opened the connections?",
                 flow_log_cmds(pb, "out") + [sh(pb, "Established connections", "ss -tnp state established | head -30")]),
            _act("now", "mitigate", "If the destination is unknown, restrict outbound from this VM and involve security",
                 "Tighten egress rules to the known destinations until the transfer is explained.", disruptive=True),
            _act("fix", "config", "Confirm or fix legitimate causes",
                 "Scheduled backups, sync jobs, log shipping to a new target, or a mirrored data store commonly cause this.",
                 [sh(pb, "Recent scheduled jobs", "crontab -l; systemctl list-timers --all | head -20")]),
            _act("prevent", "config", "Egress guard rails",
                 "Egress allow-lists and a network-out anomaly alert that pages security, plus a data-transfer cost alert."),
        ],
        do_not=["Do not treat this as a capacity problem - CPU and inbound are normal.",
                "Do not wipe the VM before evidence (connections, process list) is captured."],
        verify="Outbound traffic returns to its seasonal band and the destination is accounted for.",
        risk={"1h": "Unexplained data leaving the environment.", "24h": "Data-transfer cost spike / compliance exposure.", "7d": "Repeat transfers if unresolved."},
    )


def pb_net_loss(pb: PB):
    return dict(
        title=f"Traffic to {pb.name} vanished while the VM is healthy",
        summary=("Network traffic collapsed to a few percent of normal while the VM keeps reporting CPU and memory - the VM is fine; "
                 "requests are not reaching it (load balancer, DNS, routing or security-rule change)."),
        actions=[
            _act("now", "investigate", "Check the path in front of the VM",
                 "Load-balancer health of this backend, DNS records, and recent network/security-rule changes.",
                 [{"AWS": _cmd("Target health", "aws elbv2 describe-target-health --target-group-arn <target-group-arn>"),
                   "Azure": _cmd("Backend health", f"az network application-gateway show-backend-health -g {pb.rg} -n <appgw-name>"),
                   "GCP": _cmd("Backend health", "gcloud compute backend-services get-health <backend-service> --global")}[pb.provider],
                  change_audit_cmd(pb)]),
            _act("now", "investigate", "Verify the app answers locally",
                 "If the local health endpoint answers, the fault is upstream of the VM.",
                 [sh(pb, "Local health check", "curl -s -o /dev/null -w %{http_code} http://localhost/health")]),
            _act("fix", "mitigate", "Revert the network/LB change or fix the health-check path",
                 "Restore the previous rule / listener / DNS record; if a health probe was failing, correct the probe or the app path."),
            _act("prevent", "config", "Alert on traffic drops per tier",
                 "A sudden fall in traffic is as important as a rise; keep the drop alert on the on-call route."),
        ],
        do_not=["Do not stop, deallocate or delete this VM because it looks idle - the idleness is a symptom of an upstream problem.",
                "Do not restart the application: it is healthy and idle."],
        verify="Traffic returns to its seasonal level and target/backend health shows healthy.",
        risk={"1h": "Customers cannot reach this node; the remaining capacity is overloaded.", "24h": "Lost transactions and SLA breach.",
              "7d": "n/a - this is an outage-class event."},
    )


def pb_transient(pb: PB):
    return dict(
        title=f"Short self-resolving spike on {pb.name}",
        summary=("A brief spike fired the alert and cleared by itself; nothing else deviated. No corrective action is required."),
        actions=[
            _act("now", "investigate", "No action needed - note it",
                 "Record the time; look at what ran then (deploy, cron, health probe) only if it repeats."),
            _act("prevent", "config", "Consider a longer evaluation window",
                 "If these pages are frequent, require the condition to hold for more consecutive periods."),
        ],
        do_not=["Do not resize, restart or otherwise change the resource for a single self-resolved spike."],
        verify="The metric stays inside its normal band.",
        risk={"1h": "None.", "24h": "None.", "7d": "If it recurs at the same hour, re-evaluate as a scheduled load."},
    )


def pb_flapping(pb: PB):
    return dict(
        title=f"Alert rule flapping on {pb.name}",
        summary=("The metric hovers just around the alert threshold, so the same alert fires and clears repeatedly. "
                 "This is an alert-tuning problem, not a capacity problem."),
        actions=[
            _act("now", "investigate", "Look at the metric shape around the threshold",
                 "Confirm the metric oscillates within a few percent of the threshold.", [metric_history(pb)]),
            _act("fix", "config", "Add hysteresis / a longer evaluation window",
                 "Fire after more consecutive periods and resolve only when clearly below (e.g. fire >=75% for 5 periods, clear <=70%)."),
            _act("prevent", "config", "Group the notifications",
                 "Notify once per incident instead of per flap."),
        ],
        do_not=["Do not add capacity or restart because of the flapping alone."],
        verify="The rule stops re-firing while the metric stays in the same range.",
        risk={"1h": "Alert fatigue.", "24h": "Real alerts get ignored.", "7d": "Loss of trust in monitoring."},
    )


def pb_undetermined(pb: PB):
    return dict(
        title=f"Alert confirmed on {pb.name}; cause not yet isolated",
        summary=("The alert is real but the available metrics do not single out one cause. Gather the diagnostics below before "
                 "changing anything."),
        actions=[
            _act("now", "investigate", "Collect the standard diagnostics",
                 "CPU/memory/disk/network snapshot from the VM.",
                 [sh(pb, "Snapshot", "uptime; free -m; df -h; ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -10"), change_audit_cmd(pb)]),
            _act("now", "escalate", "Escalate to the service owner",
                 "Share the alert timeline and this analysis; ask for recent changes."),
        ],
        do_not=["Do not apply capacity or restart changes before the diagnostics identify the cause."],
        verify="A specific cause is identified from the diagnostics.",
        risk={"1h": "Unknown.", "24h": "Unknown.", "7d": "Unknown."},
    )


PLAYBOOKS = {
    "CPU_TRAFFIC_SURGE": pb_cpu_traffic_surge, "CPU_RUNAWAY_PROCESS": pb_cpu_runaway,
    "CPU_RECURRING_LOAD": pb_cpu_recurring, "UPSTREAM_PROPAGATION": pb_upstream,
    "MEMORY_LEAK": pb_memory_leak, "MEMORY_STEP_CHANGE": pb_memory_step,
    "CREDIT_EXHAUSTION": pb_credit, "DISK_LOG_GROWTH": pb_disk_growth, "DISK_SUDDEN_FILL": pb_disk_sudden,
    "NETWORK_INGRESS_ANOMALY": pb_net_ingress, "NETWORK_EGRESS_ANOMALY": pb_net_egress,
    "NETWORK_TRAFFIC_LOSS": pb_net_loss, "TRANSIENT_SPIKE": pb_transient, "ALERT_FLAPPING": pb_flapping,
    "UNDETERMINED": pb_undetermined,
}


# ── priority ───────────────────────────────────────────────────────────────────

_PRI = ["P1", "P2", "P3"]


def decide_priority(root_cause_id: str, severities: set, all_resolved: bool) -> tuple[str, str]:
    """(priority, reason).  Severity from the source alerts, adjusted by what the diagnosis means."""
    base = "P1" if "CRIT" in severities else "P2"
    reason = f"highest source alert severity is {'Critical' if base == 'P1' else 'Warning'}"
    if root_cause_id in ("TRANSIENT_SPIKE", "ALERT_FLAPPING"):
        return "P3", "self-resolving / alert-tuning issue"
    if root_cause_id == "CPU_RECURRING_LOAD":
        return "P3" if all_resolved else "P2", "known scheduled load"
    if root_cause_id == "NETWORK_TRAFFIC_LOSS" and not all_resolved:
        return "P1", "traffic loss on a running VM is outage-class"
    if all_resolved and base == "P1":
        return "P2", reason + "; alerts already resolved (post-incident review)"
    if all_resolved:
        return "P3", reason + "; alerts already resolved"
    return base, reason


def build_recommendation_body(root_cause_id: str, pb: PB) -> dict:
    body = PLAYBOOKS.get(root_cause_id, pb_undetermined)(pb)
    validate_actions(body["actions"])
    return body


def validate_actions(actions: list) -> None:
    """Safety net: no destructive command may ever be recommended."""
    for a in actions:
        assert a["automated"] is False and a["requires_approval"] is True
        for c in a.get("commands", []):
            if _FORBIDDEN.search(c["command"]):
                raise ValueError(f"forbidden command in playbook: {c['command']}")
