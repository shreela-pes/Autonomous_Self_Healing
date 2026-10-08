# Field reference

## 1. Source log document (`distinct logs` collection, `data/synthetic_logs.ndjson.gz`)

Identical top-level fields for AWS, Azure and GCP. One document = one resource x one metric x one UTC day.

| field | type | description |
|---|---|---|
| `_id` | ObjectId | document id |
| `category` | str | `Compute` |
| `config_type` | str | `default_monitoring` |
| `metric` | str | provider-native metric name |
| `resourceId` / `element_id` | str | instance id (AWS), ARM id (Azure), `projects/<p>/zones/<z>/instances/<n>` (GCP) |
| `account_id` | str | account object id |
| `account_name` | str | account / subscription / GCP project label |
| `project` | str | project id (groups the resources) |
| `from_date` / `to_date` | date | day start `00:00:00.000Z` / day end `23:59:59.999Z` |
| `display_name`, `group_name`, `metric_group_name` | str | metric display label (both group-field spellings kept so one schema fits all clouds) |
| `metric_value` | list[24] | hourly points (see 2) |
| `unit` | str | Percent / Bytes / Count / Seconds / Ratio |
| `namespace` | str | e.g. `AWS/EC2`, `CWAgent`, `Microsoft.Compute/virtualMachines`, `compute.googleapis.com` |
| `name` | str | VPC name (AWS) / resource group (Azure) / GCP project id |
| `resource_name` | str | VM name |
| `resource_filter` | str | region / resource group / zone |
| `uri`, `operation_id`, `component`, `resource`, `resource_type` | str | inventory metadata; `resource_type` = `EC2` \| `Virtual_Machines` \| `Compute_Engine` |
| `location`, `region` | str | zone or region |
| `service_name`, `service_type` | str | `AWS`/`Azure`/`GCP`, `Cloud` |
| `summary_details` | dict | provider-shaped VM configuration (see 4) |
| `extended_summary_details` | dict | NIC details |
| `tags` | list[{key,value}] | includes `app`, `tier` (web/app/worker/db), `env`, `owner`, `cost-center`, `Name` |
| `custom_metrics`, `meta_data`, `third_party_integration` | dict | empty placeholders (as in the real logs) |
| `created_at`, `updated_at`, `created_by` | date / str | ingestion metadata |
| **`alerts`** | list | alert records active for this metric on this day; `[]` when none (see 3) |

## 2. `metric_value[]` point

`timeStamp` (date), `average`, `minimum`, `maximum` (float); for volume metrics (network, disk write) also `total`, `count`.
A missing hour has only `timeStamp`. With `--aws-native-points`, AWS points use `Timestamp`, `SampleCount`, `Unit`, `Average`, `Minimum`, `Maximum`, `Sum`.

## 3. `alerts[]` record

`alert_id`, `alert_name`, `alert_rule_id`, `alert_source`, `severity` (Critical|Warning), `provider_severity`,
`state` (Fired|Resolved as of the end of the day), `metric`, `operator`, `aggregation`, `threshold`, `expected_value`,
`observed_value`, `condition_type` (static|dynamic), `evaluation_periods`, `period_minutes`, `fired_at`, `resolved_at`,
`duration_minutes`, `is_continuation`, `description`.

## 4. `summary_details` / `extended_summary_details` by provider

| provider | `summary_details` keys | `extended_summary_details` keys |
|---|---|---|
| AWS | `reservationId`, `ownerId`, `instancesSet.item` (instanceId, instanceType, placement, monitoring, blockDeviceMapping, metadataOptions, tagSet, ...) | `network_interfaces` |
| Azure | `name`, `id`, `type`, `location`, `tags`, `properties` (hardwareProfile.vmSize, storageProfile, osProfile, ...), `zones`, `status` | `network_interfaces_details` |
| GCP | `id`, `name`, `zone`, `machineType`, `status`, `cpuPlatform`, `canIpForward`, `deletionProtection`, `scheduling`, `disks`, `shieldedInstanceConfig`, `networkInterfaces`, `labels` | `network_interface_details` |

## 5. Native metric names used

| role | AWS | Azure | GCP |
|---|---|---|---|
| cpu | `CPUUtilization` | `Percentage CPU` | `compute.googleapis.com/instance/cpu/utilization` |
| memory | `mem_used_percent` | `Available Memory Bytes` | `agent.googleapis.com/memory/percent_used` |
| disk | `disk_used_percent` | `disk/free_percent` | `agent.googleapis.com/disk/percent_used` |
| disk write | `DiskWriteBytes` | `Disk Write Bytes` | `compute.googleapis.com/instance/disk/write_bytes_count` |
| credits | `CPUCreditBalance` | `CPU Credits Remaining` | - (uses `.../cpu/scheduler_wait_time`) |
| network in / out | `NetworkIn` / `NetworkOut` | `Network In Total` / `Network Out Total` | `.../network/received_bytes_count` / `.../sent_bytes_count` |

## 6. `ground_truth.json` entry

`incident_id`, `provider`, `project_key`, `project_id`, `resource_id`, `resource_name`, `tier`, `use_case`, `scenario`, `note`,
`window_start`, `window_end`, `expects_alert`, `expects_recommendation`, `expected_root_cause`, `acceptable_root_causes`,
`root_resource_ids`, `n_alert_episodes`, `alert_metrics` (+ `episode_index` for the recurring batch).

## 7. `dataset_manifest.json`

`generated_with`, `counts`, `use_cases`, `main_metrics_per_use_case_and_provider`, `fleet[]`
(`provider`, `project_key`, `project_id`, `resource_id`, `resource_name`, `tier`, `instance_type`, `roles`, `native_metrics`).

## 8. Pipeline output: `recommendations` collection

`_id`/`incident_id`, `project_id`, `resource_id`, `resource_name`, `resource_type`, `provider`, `tier`, `app`,
`use_case`, `use_case_title`, `status` (open|resolved), `priority` (P1-P3), `priority_reason`, `title`, `summary`,
`root_cause` {`id`, `label`, `confidence`, `confidence_parts`, `evidence`, `counter_evidence`, `alternatives`, `hypotheses`, `root_resource_id`, `root_resource_name`},
`alerts[]`, `correlation` {`summary`, `intra_resource`, `same_tier_peers`, `upstream`, `downstream`, `domain_rules`, `learned_correlations`, `timeline`},
`statistics` {`metrics`, `trends`}, `ml`, `actions[]` (+ `immediate_actions`, `corrective_actions`, `preventive_actions`),
`do_not_do`, `verification`, `risk_if_ignored`, `explanation` {`sections`, `source`, `note`},
`automated_remediation` (always false), `requires_human_approval` (always true), `analysis_mode`,
`observation_date`, `first_alert_at`, `last_alert_at`, `resolved_at`, `created_at`, `updated_at`, `revision`, `revisions[]`.

Other collections: `incidents` (grouped alerts), `resource_profiles` (baselines/history/tags), `project_snapshots`, `alert_patterns`.
