# Dataset reference

## Document schema (identical for AWS, Azure, GCP)

One document = one resource x one metric x one UTC day (`from_date` 00:00:00.000Z .. `to_date` 23:59:59.999Z), 24 hourly points.
Mongo extended JSON (`{"$date": ...}`, `{"$oid": ...}`), one document per line.

| field | meaning |
|---|---|
| `_id`, `inventory_id` | ObjectIds |
| `category` | `Compute` |
| `config_type` | `default_monitoring` |
| `metric` | provider-native metric name (e.g. `CPUUtilization`, `Available Memory Bytes`, `compute.googleapis.com/instance/cpu/utilization`) |
| `resourceId`, `element_id` | instance id (AWS) / ARM id (Azure) / `projects/<p>/zones/<z>/instances/<name>` (GCP) |
| `project`, `account_id`, `account_name` | project id groups resources; account metadata |
| `display_name`, `group_name`, `metric_group_name` | display label (both spellings of the group field are present so one schema fits all clouds) |
| `metric_value[]` | 24 points `{timeStamp, average, minimum, maximum}` (+ `total`, `count` for volume metrics); a missing hour has only `timeStamp` |
| `unit` | Percent / Bytes / Count / Seconds / Ratio |
| `namespace`, `name`, `resource_name`, `resource_filter`, `uri`, `operation_id`, `component`, `resource`, `resource_type` | inventory-style metadata (`resource_type` in `EC2`, `Virtual_Machines`, `Compute_Engine`) |
| `location`, `region` | zone / region |
| `summary_details` | provider-shaped configuration (EC2 `instancesSet.item`, Azure VM properties + `status`, GCE machineType/disks/labels) |
| `extended_summary_details` | NIC details |
| `tags[]` | `{key,value}` incl. `app`, `tier` (web/app/worker/db), `env` - **the pipeline infers topology from `app`+`tier`** |
| `created_at`, `updated_at`, `created_by`, `custom_metrics`, `meta_data`, `third_party_integration`, `service_name`, `service_type` | as in the real logs |
| **`alerts[]`** | alert records active for this metric during the day (empty list otherwise) |

### `alerts[]` record

```
alert_id, alert_name, alert_rule_id, alert_source (CloudWatch Alarm | Azure Monitor Metric Alert | Cloud Monitoring Alert Policy),
severity (Critical|Warning), provider_severity (ALARM | Sev1/Sev2 | CRITICAL/WARNING),
state (Fired|Resolved - as of the END of this document's day), metric (native), operator (provider-native),
aggregation, threshold (native units), expected_value (dynamic rules: seasonal baseline), observed_value,
condition_type (static|dynamic), evaluation_periods, period_minutes, fired_at, resolved_at (null until resolved),
duration_minutes, is_continuation (fired on an earlier day), description
```

Native units differ by design (Azure memory is *available bytes* with a `LessThan` rule; GCP CPU is a 0-1 ratio; network
`average` is bytes per sampling interval) - `pipeline/metrics/derive.py` and the registry canonicalise them.

## Use case x provider main metrics
See `dataset_manifest.json -> main_metrics_per_use_case_and_provider`.

## Fleet
`dataset_manifest.json -> fleet` lists every resource (id, tier, instance type, recorded metrics).  Tiers record:
web/app = cpu, memory, network in/out; worker = cpu, memory, credit balance (GCP: scheduler wait); db = cpu, memory, disk used, disk write.

## Scenarios (per provider; days are offsets in the 70-day window, shifted by -1/0/+2 days per cloud)

| project | resource | scenario | day | expected root cause |
|---|---|---|---|---|
| p1 prod/shop | web-01 | traffic_surge (fleet-wide) | 33 | CPU_TRAFFIC_SURGE |
| | web-01 | net_ingress_anomaly | 51 | NETWORK_INGRESS_ANOMALY |
| | web-01 | anomaly_no_alert (CPU blip to ~66%) | 60 | *none* |
| | web-02 | traffic_surge | 33 | CPU_TRAFFIC_SURGE |
| | web-02 | cpu_flapping | 46 | ALERT_FLAPPING |
| | app-01 | downstream_surge (1 h lag) | 33 | UPSTREAM_PROPAGATION (origin: web tier) |
| | app-01 | memory_leak (42 -> restart 63) | 42 | MEMORY_LEAK |
| | worker-01 | credit_exhaustion (8 days) | 36 | CREDIT_EXHAUSTION |
| | worker-01 | transient_spike (2 h) | 57 | TRANSIENT_SPIKE |
| | db-01 | disk_sudden_fill (cleanup day 49) | 47 | DISK_SUDDEN_FILL |
| p2 staging/analytics | web-01 | net_egress_anomaly (12 h) | 44 | NETWORK_EGRESS_ANOMALY |
| | web-02 | net_traffic_loss (6 h) | 55 | NETWORK_TRAFFIC_LOSS |
| | app-01 | memory_step (+23 pts, rollback 58) | 41 | MEMORY_STEP_CHANGE |
| | app-01 | data_gap (6 missing hours) | 50 | *none* |
| | app-01 | cpu_runaway (9 h @ 97%) | 63 | CPU_RUNAWAY_PROCESS |
| | worker-01 | recurring_batch (Mondays 02:00-05:00, 6x) | 28+ | CPU_RECURRING_LOAD (from the 3rd; 1st/2nd: RUNAWAY or RECURRING) |
| | db-01 | disk_log_growth (+1.45 pts/day, open at end) | 40 | DISK_LOG_GROWTH |

`ground_truth.json` has one entry per scenario (per episode for the recurring batch) with the effect window, expected root
cause, accepted alternatives, expected origin resources for cross-resource cases, and how many alert episodes it produced.
