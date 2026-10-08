# Sample recommendations (deterministic template explanations, produced by `python main.py --no-llm`)

All recommendations of the full synthetic run:

```
first alert (UTC) cloud pri state    resource                         use case                 root cause                 conf  rev
2026-08-10 03:55  AWS   P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-10 03:55  Azure P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-10 03:55  GCP   P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-12 14:55  GCP   P2  resolved shop-prod-web-01                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-12 14:55  GCP   P2  resolved shop-prod-web-02                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-12 15:55  GCP   P2  resolved shop-prod-app-01                 CPU saturation           UPSTREAM_PROPAGATION       0.9   1
2026-08-13 14:55  AWS   P2  resolved shop-prod-app-01                 CPU saturation           UPSTREAM_PROPAGATION       0.9   1
2026-08-13 14:55  AWS   P2  resolved shop-prod-web-02                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-13 14:55  AWS   P2  resolved shop-prod-web-01                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-15 15:55  Azure P3  resolved shop-prod-web-01                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-15 15:55  Azure P3  resolved shop-prod-web-02                 CPU saturation           CPU_TRAFFIC_SURGE          0.92  1
2026-08-15 16:55  Azure P2  resolved shop-prod-app-01                 CPU saturation           UPSTREAM_PROPAGATION       0.9   1
2026-08-16 12:55  GCP   P2  resolved shop-prod-worker-01              Burst-credit exhaustion  CREDIT_EXHAUSTION          0.92  7
2026-08-17 03:55  AWS   P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-17 03:55  Azure P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-17 03:55  GCP   P2  resolved analytics-staging-worker-01      CPU saturation           CPU_RUNAWAY_PROCESS        0.72  1
2026-08-17 20:55  AWS   P2  resolved shop-prod-worker-01              Burst-credit exhaustion  CREDIT_EXHAUSTION          0.86  2
2026-08-19 17:55  Azure P2  resolved shop-prod-worker-01              Burst-credit exhaustion  CREDIT_EXHAUSTION          0.92  2
2026-08-20 12:55  GCP   P3  resolved analytics-staging-app-01         Memory pressure          MEMORY_STEP_CHANGE         0.92  2
2026-08-21 11:55  AWS   P3  resolved analytics-staging-app-01         Memory pressure          MEMORY_STEP_CHANGE         0.92  2
2026-08-23 12:55  Azure P3  resolved analytics-staging-app-01         Memory pressure          MEMORY_STEP_CHANGE         0.92  2
2026-08-23 21:55  GCP   P2  resolved analytics-staging-web-01         Network anomaly          NETWORK_EGRESS_ANOMALY     0.92  2
2026-08-24 03:55  AWS   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-24 03:55  Azure P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-24 03:55  GCP   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-24 21:55  AWS   P2  resolved analytics-staging-web-01         Network anomaly          NETWORK_EGRESS_ANOMALY     0.92  2
2026-08-25 10:55  GCP   P3  resolved shop-prod-web-02                 Cross-cutting            ALERT_FLAPPING             0.91  1
2026-08-26 10:55  AWS   P3  resolved shop-prod-web-02                 Cross-cutting            ALERT_FLAPPING             0.91  1
2026-08-26 12:55  GCP   P3  resolved shop-prod-db-01                  Disk capacity            DISK_SUDDEN_FILL           0.92  2
2026-08-26 21:55  Azure P2  resolved analytics-staging-web-01         Network anomaly          NETWORK_EGRESS_ANOMALY     0.92  2
2026-08-27 12:55  AWS   P3  resolved shop-prod-db-01                  Disk capacity            DISK_SUDDEN_FILL           0.92  2
2026-08-28 10:55  Azure P3  resolved shop-prod-web-02                 Cross-cutting            ALERT_FLAPPING             0.81  1
2026-08-28 14:55  GCP   P2  resolved shop-prod-app-01                 Memory pressure          MEMORY_LEAK                0.92  6
2026-08-28 16:55  AWS   P2  resolved shop-prod-app-01                 Memory pressure          MEMORY_LEAK                0.92  6
2026-08-29 12:55  Azure P3  resolved shop-prod-db-01                  Disk capacity            DISK_SUDDEN_FILL           0.92  2
2026-08-30 03:55  GCP   P2  resolved shop-prod-web-01                 Network anomaly          NETWORK_INGRESS_ANOMALY    0.92  1
2026-08-31 03:55  AWS   P2  resolved shop-prod-web-01                 Network anomaly          NETWORK_INGRESS_ANOMALY    0.92  1
2026-08-31 03:55  AWS   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-31 03:55  Azure P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-31 03:55  GCP   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.87  1
2026-08-31 15:55  Azure P2  resolved shop-prod-app-01                 Memory pressure          MEMORY_LEAK                0.92  6
2026-09-02 03:55  Azure P2  resolved shop-prod-web-01                 Network anomaly          NETWORK_INGRESS_ANOMALY    0.92  1
2026-09-03 11:55  GCP   P2  resolved analytics-staging-web-02         Network anomaly          NETWORK_TRAFFIC_LOSS       0.92  1
2026-09-04 11:55  AWS   P2  resolved analytics-staging-web-02         Network anomaly          NETWORK_TRAFFIC_LOSS       0.92  1
2026-09-05 12:55  GCP   P3  resolved shop-prod-worker-01              Cross-cutting            TRANSIENT_SPIKE            0.91  1
2026-09-06 11:55  Azure P2  resolved analytics-staging-web-02         Network anomaly          NETWORK_TRAFFIC_LOSS       0.92  1
2026-09-06 12:55  AWS   P3  resolved shop-prod-worker-01              Cross-cutting            TRANSIENT_SPIKE            0.91  1
2026-09-07 03:55  AWS   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-07 03:55  Azure P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-07 03:55  GCP   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-07 13:55  GCP   P1  open     analytics-staging-db-01          Disk capacity            DISK_LOG_GROWTH            0.92  2
2026-09-08 11:55  AWS   P1  open     analytics-staging-db-01          Disk capacity            DISK_LOG_GROWTH            0.92  2
2026-09-08 12:55  Azure P3  resolved shop-prod-worker-01              Cross-cutting            TRANSIENT_SPIKE            0.91  1
2026-09-10 05:55  Azure P2  open     analytics-staging-db-01          Disk capacity            DISK_LOG_GROWTH            0.92  1
2026-09-11 07:55  GCP   P2  resolved analytics-staging-app-01         CPU saturation           CPU_RUNAWAY_PROCESS        0.95  1
2026-09-12 07:55  AWS   P2  resolved analytics-staging-app-01         CPU saturation           CPU_RUNAWAY_PROCESS        0.95  1
2026-09-14 03:55  AWS   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-14 03:55  Azure P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-14 03:55  GCP   P3  resolved analytics-staging-worker-01      CPU saturation           CPU_RECURRING_LOAD         0.91  1
2026-09-14 07:55  Azure P2  resolved analytics-staging-app-01         CPU saturation           CPU_RUNAWAY_PROCESS        0.95  1
```

## One example per root cause (full detail)

```
====================================================================================================
[P2] CPU saturation from a traffic surge on shop-prod-web-02   (AWS / EC2 / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC1 - CPU saturation
root cause      : CPU_TRAFFIC_SURGE - CPU saturated by a traffic surge (load-driven)   confidence 92%
incident window : first alert 2026-08-13 14:55  last alert 2026-08-13 17:55  resolved 2026-08-13 20:55   (revision 1)

ALERTS (source)
  - WARN cpu_pct                  >     thr=75.0 observed=100.0  fired 2026-08-13 14:55  resolved 2026-08-13 20:55
  - CRIT cpu_pct                  >     thr=90.0 observed=100.0  fired 2026-08-13 15:55  resolved 2026-08-13 19:55
  - WARN network_in_bytes         surge thr=451144494.73 observed=483036931.58  fired 2026-08-13 16:55  resolved 2026-08-13 19:55
  - WARN network_out_bytes        surge thr=1239937186.18 observed=1383510465.16  fired 2026-08-13 17:55  resolved 2026-08-13 18:55

WHY THIS ROOT CAUSE (evidence)
  + network-in averaged 2.5x its same-hour baseline while CPU was high
  + the hourly correlation of CPU with network-in is r=0.99
  + the largest hour-to-hour network-in jump is x1.7
  + memory peaked at 66.5%
  + no earlier alert at this weekday/hour
  + peer nodes of the same tier show the same alert
  considered and ranked lower
  ~ CPU saturated by a runaway process / job (traffic is normal) (score 0.43) - argued against by: expected normal traffic while CPU is high, but network-in averaged 2.5x its baseline during the CPU-high hours; expected a flat CPU plateau, but CPU sat at 95.3% with a standard deviation of 8.3 across 7 high hours; expected CPU not to follow network-in, but the hourly correlation of CPU with networ
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on cpu_pct, network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct. 1 peer node(s) of the same tier alerted in the same window (shared cause likely). Downstream resources alerting at the same time: shop-prod-app-01.
    2026-08-13 14:55  shop-prod-web-02         fired    cpu_pct (WARN)
    2026-08-13 14:55  shop-prod-app-01         fired    cpu_pct (WARN)
    2026-08-13 14:55  shop-prod-web-01         fired    cpu_pct (CRIT)
    2026-08-13 14:55  shop-prod-web-01         fired    cpu_pct (WARN)
    2026-08-13 15:55  shop-prod-web-02         fired    cpu_pct (CRIT)
    2026-08-13 15:55  shop-prod-app-01         fired    cpu_pct (CRIT)
    2026-08-13 16:55  shop-prod-web-02         fired    network_in_bytes (WARN)
    2026-08-13 16:55  shop-prod-web-01         fired    network_in_bytes (WARN)
    2026-08-13 16:55  shop-prod-web-01         fired    network_out_bytes (WARN)
    2026-08-13 17:55  shop-prod-web-02         fired    network_out_bytes (WARN)
    2026-08-13 17:55  shop-prod-app-01         fired    network_in_bytes (WARN)
    2026-08-13 17:55  shop-prod-app-01         fired    network_out_bytes (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=33d  7d slope=2.587/day  30d slope=0.113/day  shape(10d)=step  same-weekday median=35.3
  memory_used_pct          history=33d  7d slope=0.292/day  30d slope=0.033/day  shape(10d)=irregular  same-weekday median=58.2
  network_in_bytes         history=33d  7d slope=12770505.162/day  30d slope=602005.907/day  shape(10d)=step  same-weekday median=106013943.9
  network_out_bytes        history=33d  7d slope=35898647.254/day  30d slope=1844385.439/day  shape(10d)=step  same-weekday median=300052954.6

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Add capacity to the tier behind the load balancer
        Bring one extra node into service (or raise the autoscaling floor) so the load spreads. This is the fastest, lowest-risk relief because the extra load is legitimate-looking traffic.
        $ aws autoscaling describe-auto-scaling-instances --instance-ids i-35b4f54deecaba7e3   # Find the Auto Scaling group of this instance
        $! aws autoscaling set-desired-capacity --auto-scaling-group-name <asg-name> --desired-capacity <N+1>   # Add one node (set N+1)
  [NOW] Confirm the surge is legitimate
        Check the load balancer / access logs for the top clients and paths. A marketing event or a retry storm needs capacity; a single abusive client needs rate limiting instead.
        $ aws logs start-query --log-group-name <vpc-flow-log-group> --start-time <epoch-start> --end-time <epoch-end> --query-string "filter interfaceId = '<eni-id>' | stats sum(bytes) as b by srcAddr | sort b desc | limit 20"   # Top talkers from VPC flow logs (CloudWatch Logs Insights)
        $ aws ssm send-command --instance-ids i-35b4f54deecaba7e3 --document-name AWS-RunShellScript --parameters '{"commands":["ss -s"]}'   # Live connection summary
  [FIX] Right-size or raise autoscaling limits if the surge repeats  [disruptive]
        If this load level is the new normal, move to the next size (m5.large -> m5.xlarge) or lower the CPU target of the scaling policy so nodes are added earlier.
        $! aws ec2 stop-instances --instance-ids i-35b4f54deecaba7e3   # Stop the instance (brief outage)
        $! aws ec2 modify-instance-attribute --instance-id i-35b4f54deecaba7e3 --instance-type "{\"Value\": \"m5.xlarge\"}"   # Change instance type
        $! aws ec2 start-instances --instance-ids i-35b4f54deecaba7e3   # Start the instance
  [PREVENT] Alert on the leading indicator
        Add a network-in anomaly alert (already firing here) to the on-call route for this tier so the surge is handled before CPU saturates.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not restart the application - the process is healthy, it is overloaded.
  x Do not resize only this one node if its peers are equally loaded; add nodes to the tier.
VERIFY: CPU falls below 75% within ~15 minutes of the extra capacity joining and network-in per node drops.
IF IGNORED: 1h - Latency and error rates rise as requests queue on saturated CPUs.  |  24h - Timeouts cascade to downstream tiers.  |  7d - Repeated surges without capacity change cause customer-visible outages.

EXPLANATION (template)
  summary: shop-prod-web-02 raised 4 alert(s) on cpu_pct, network_in_bytes, network_out_bytes starting 2026-08-13 14:55 (already resolved). Diagnosis: CPU saturated by a traffic surge (load-driven) - priority P2. CPU peaked at 100% while inbound traffic ran well above its normal level - the box is doing exactly what it should, it is simply out of capacity for the current load.
  why_this_cause: This cause was chosen because: network-in averaged 2.5x its same-hour baseline while CPU was high; the hourly correlation of CPU with network-in is r=0.99; the largest hour-to-hour network-in jump is x1.7; memory peaked at 66.5%. Other explanations were considered and ranked lower: CPU saturated by a runaway process / job (traffic is normal) (score 0.43). Same resource: alerts on cpu_pct, network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct. 1 peer node(s) of the same tier alerted in the same window (shared cause likely). Downstream resources alerting at the same time: shop-prod-app-01.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Add capacity to the tier behind the load balancer; 2) Confirm the surge is legitimate; 3) Right-size or raise autoscaling limits if the surge repeats. Avoid: Do not restart the application - the process is healthy, it is overloaded. Do not resize only this one node if its peers are equally loaded; add nodes to the tier.
  what_to_watch: CPU falls below 75% within ~15 minutes of the extra capacity joining and network-in per node drops.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] shop-prod-app-01: symptoms are downstream of a problem on shop-prod-web-01   (Azure / Virtual_Machines / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC1 - CPU saturation
root cause      : UPSTREAM_PROPAGATION - Symptom propagated from an upstream tier - the cause is not on this resource   confidence 90%
origin resource : shop-prod-web-01
incident window : first alert 2026-08-15 16:55  last alert 2026-08-15 20:55  resolved 2026-08-15 21:55   (revision 1)

ALERTS (source)
  - WARN cpu_pct                  >     thr=75.0 observed=99.9  fired 2026-08-15 16:55  resolved 2026-08-15 20:55
  - WARN network_in_bytes         surge thr=42449238.76 observed=49181619.15  fired 2026-08-15 17:55  resolved 2026-08-15 18:55
  - CRIT cpu_pct                  >     thr=90.0 observed=99.9  fired 2026-08-15 17:55  resolved 2026-08-15 19:55
  - WARN network_out_bytes        surge thr=25680820.31 observed=30677081.35  fired 2026-08-15 19:55  resolved 2026-08-15 20:55
  - WARN network_in_bytes         surge thr=31427598.85 observed=36519167.97  fired 2026-08-15 20:55  resolved 2026-08-15 21:55

WHY THIS ROOT CAUSE (evidence)
  + the upstream alert fired 1.0h before this one
  + network-in here ran at 2.7x its baseline
  + 2 upstream node(s) alerted in the same window
  considered and ranked lower
  ~ CPU saturated by a traffic surge (load-driven) (local view, score 0.94) - same symptoms, but an upstream cause explains them with earlier timing
  ~ CPU saturated by a runaway process / job (traffic is normal) (score 0.29) - argued against by: expected normal traffic while CPU is high, but network-in averaged 2.7x its baseline during the CPU-high hours; expected a flat CPU plateau, but CPU sat at 89.6% with a standard deviation of 6.8 across 5 high hours; expected an abrupt onset, but CPU rose 16.9 points within a single hour; expected CP
  confidence parts: {'base': 0.3, 'evidence_score': 0.444, 'margin': 0.12, 'correlation_support': 0.04}

CORRELATION
  Same resource: alerts on cpu_pct, network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct. Upstream shop-prod-web-01 alerted first (CPU_TRAFFIC_SURGE); this resource is downstream of it.
    2026-08-15 15:55  shop-prod-web-01         fired    cpu_pct (WARN)
    2026-08-15 15:55  shop-prod-web-02         fired    cpu_pct (WARN)
    2026-08-15 16:55  shop-prod-app-01         fired    cpu_pct (WARN)
    2026-08-15 16:55  shop-prod-web-01         fired    network_in_bytes (WARN)
    2026-08-15 16:55  shop-prod-web-01         fired    network_out_bytes (WARN)
    2026-08-15 17:55  shop-prod-app-01         fired    network_in_bytes (WARN)
    2026-08-15 17:55  shop-prod-app-01         fired    cpu_pct (CRIT)
    2026-08-15 18:55  shop-prod-app-01         resolved network_in_bytes (WARN)
    2026-08-15 18:55  shop-prod-web-01         resolved network_in_bytes (WARN)
    2026-08-15 18:55  shop-prod-web-02         resolved cpu_pct (WARN)
    2026-08-15 19:55  shop-prod-app-01         resolved cpu_pct (CRIT)
    2026-08-15 19:55  shop-prod-app-01         fired    network_out_bytes (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=35d  7d slope=1.661/day  30d slope=0.107/day  shape(10d)=irregular  same-weekday median=32.2
  memory_used_pct          history=35d  7d slope=0.261/day  30d slope=0.029/day  shape(10d)=irregular  same-weekday median=56.7
  network_in_bytes         history=35d  7d slope=926310.316/day  30d slope=69128.727/day  shape(10d)=irregular  same-weekday median=10427444.0
  network_out_bytes        history=35d  7d slope=671004.435/day  30d slope=53270.649/day  shape(10d)=irregular  same-weekday median=7741239.7

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Work the incident on shop-prod-web-01 first
        Follow the recommendation on the upstream resource (add capacity / rate-limit at the edge). This resource is a symptom; it will recover as the upstream load normalises.
  [NOW] Watch this tier while the upstream fix lands
        Track CPU and connection counts here; only if they stay high after the upstream load is back to normal treat this as a separate problem.
        $ az vm run-command invoke -g shop-prod-rg -n shop-prod-app-01 --command-id RunShellScript --scripts "ss -s"   # Connection summary
        $ az vm run-command invoke -g shop-prod-rg -n shop-prod-app-01 --command-id RunShellScript --scripts "ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -10"   # Top CPU processes
  [PREVENT] Add back-pressure between the tiers
        Connection limits / queue depth alerts between tiers keep an upstream surge from saturating this tier.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not resize or restart this resource as the first move - it will not remove the cause.
  x Do not open a separate root-cause investigation before the upstream incident is handled.
VERIFY: This resource's CPU follows the upstream tier back below 75% without any change made here.
IF IGNORED: 1h - Errors propagate across tiers.  |  24h - Two teams debug the same incident separately.  |  7d - Same chain repeats.

EXPLANATION (template)
  summary: shop-prod-app-01 raised 5 alert(s) on cpu_pct, network_in_bytes, network_out_bytes starting 2026-08-15 16:55 (already resolved). Diagnosis: Symptom propagated from an upstream tier - the cause is not on this resource - priority P2. CPU here rose because the upstream tier (shop-prod-web-01, shop-prod-web-02) alerted first and passed the extra load down. Fixing this resource alone would not remove the cause.
  why_this_cause: This cause was chosen because: the upstream alert fired 1.0h before this one; network-in here ran at 2.7x its baseline; 2 upstream node(s) alerted in the same window. Other explanations were considered and ranked lower: CPU saturated by a traffic surge (load-driven) (local view, score 0.94) - same symptoms, but an upstream cause explains them with earlier timing | CPU saturated by a runaway process / job (traffic is normal) (score 0.29). Same resource: alerts on cpu_pct, network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct. Upstream shop-prod-web-01 alerted first (CPU_TRAFFIC_SURGE); this resource is downstream of it.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Work the incident on shop-prod-web-01 first; 2) Watch this tier while the upstream fix lands. Avoid: Do not resize or restart this resource as the first move - it will not remove the cause. Do not open a separate root-cause investigation before the upstream incident is handled.
  what_to_watch: This resource's CPU follows the upstream tier back below 75% without any change made here.
  confidence_note: Confidence 90%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Runaway process suspected on analytics-staging-worker-01   (GCP / Compute_Engine / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC1 - CPU saturation
root cause      : CPU_RUNAWAY_PROCESS - CPU saturated by a runaway process / job (traffic is normal)   confidence 72%
incident window : first alert 2026-08-10 03:55  last alert 2026-08-10 03:55  resolved 2026-08-10 05:55   (revision 1)

ALERTS (source)
  - CRIT cpu_pct                  >     thr=90.0 observed=92.91  fired 2026-08-10 03:55  resolved 2026-08-10 05:55
  - WARN cpu_pct                  >     thr=75.0 observed=92.91  fired 2026-08-10 03:55  resolved 2026-08-10 05:55

WHY THIS ROOT CAUSE (evidence)
  + CPU sat at 92.7% with a standard deviation of 0.2 across 3 high hours
  + CPU rose 67.6 points within a single hour
  + memory peaked at 55.9%
  + no earlier alert at this weekday/hour
  confidence parts: {'base': 0.3, 'evidence_score': 0.382, 'margin': 0.12, 'missing_data': -0.08}

CORRELATION
  Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
    2026-08-10 03:55  analytics-staging-worker-01 fired    cpu_pct (CRIT)
    2026-08-10 03:55  analytics-staging-worker-01 fired    cpu_pct (WARN)
    2026-08-10 05:55  analytics-staging-worker-01 resolved cpu_pct (CRIT)
    2026-08-10 05:55  analytics-staging-worker-01 resolved cpu_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=30d  7d slope=0.828/day  30d slope=0.059/day  shape(10d)=step  same-weekday median=15.0
  memory_used_pct          history=30d  7d slope=-0.23/day  30d slope=0.039/day  shape(10d)=irregular  same-weekday median=52.2
  cpu_scheduler_wait_sec   history=30d  7d slope=0.04/day  30d slope=-0.009/day  shape(10d)=irregular  same-weekday median=11.8

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Identify the consuming process
        List the top CPU consumers with their start time; a process whose start time matches the moment the plateau began (deploy, cron, backup, agent update) is the culprit.
        $ gcloud compute ssh analytics-staging-worker-01 --zone us-central1-a --command "ps -eo pid,ppid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"   # Top CPU processes
        $ gcloud compute ssh analytics-staging-worker-01 --zone us-central1-a --command "systemctl list-timers --all | head -20"   # Cron / timers that started recently
  [NOW] Stop or throttle the offending job (after confirming it is safe)  [disruptive]
        If the process is a batch / maintenance job, pause it or lower its priority (nice) first; restart the service only if it is a spinning worker. Coordinate with the job's owner.
        $ gcloud compute ssh analytics-staging-worker-01 --zone us-central1-a --command "renice +10 -p <pid>"   # Lower priority of a specific PID (replace <pid>)
  [FIX] Review what changed at the plateau start
        Compare the plateau start time with deployments and configuration changes.
        $ gcloud logging read 'protoPayload.serviceName="compute.googleapis.com" AND protoPayload.methodName:"compute."' --freshness=6h --limit=20   # Recent control-plane changes
  [PREVENT] Cap the job's CPU (cgroup / systemd CPUQuota) and add a runtime limit
        Prevents one process from taking the whole VM again.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not scale the VM up - traffic is normal, more CPU would just be consumed by the same process.
  x Do not reboot as a first step: it destroys the evidence (which process, which arguments).
VERIFY: CPU returns to its usual daily shape and the flat plateau disappears.
IF IGNORED: 1h - Legitimate work on the VM is starved and latency rises.  |  24h - Health checks may start failing and the node be taken out of service.  |  7d - If the job is a leak or a loop it will recur after every restart.

EXPLANATION (template)
  summary: analytics-staging-worker-01 raised 2 alert(s) on cpu_pct starting 2026-08-10 03:55 (already resolved). Diagnosis: CPU saturated by a runaway process / job (traffic is normal) - priority P2. CPU is pinned near 93% on a flat plateau while traffic and memory are normal - the load is coming from something running on the machine, not from users.
  why_this_cause: This cause was chosen because: CPU sat at 92.7% with a standard deviation of 0.2 across 3 high hours; CPU rose 67.6 points within a single hour; memory peaked at 55.9%; no earlier alert at this weekday/hour. Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Identify the consuming process; 2) Stop or throttle the offending job (after confirming it is safe); 3) Review what changed at the plateau start. Avoid: Do not scale the VM up - traffic is normal, more CPU would just be consumed by the same process. Do not reboot as a first step: it destroys the evidence (which process, which arguments).
  what_to_watch: CPU returns to its usual daily shape and the flat plateau disappears.
  confidence_note: Confidence 72%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P3] Scheduled load repeatedly saturates CPU on analytics-staging-worker-01   (AWS / EC2 / resolved)
priority reason : known scheduled load
use case        : UC1 - CPU saturation
root cause      : CPU_RECURRING_LOAD - Recurring scheduled load saturates CPU (seasonal pattern)   confidence 91%
incident window : first alert 2026-09-14 03:55  last alert 2026-09-14 03:55  resolved 2026-09-14 05:55   (revision 1)

ALERTS (source)
  - CRIT cpu_pct                  >     thr=90.0 observed=92.36  fired 2026-09-14 03:55  resolved 2026-09-14 05:55
  - WARN cpu_pct                  >     thr=75.0 observed=92.36  fired 2026-09-14 03:55  resolved 2026-09-14 05:55

WHY THIS ROOT CAUSE (evidence)
  + this is the 6th alert on this weekday/hour - a schedule, not a one-off incident
  + CPU plateau standard deviation is 0.8
  considered and ranked lower
  ~ CPU saturated by a runaway process / job (traffic is normal) (score 0.53) - argued against by: expected no repeating schedule, but 5 earlier alert(s) at this weekday/hour
  confidence parts: {'base': 0.3, 'evidence_score': 0.455, 'margin': 0.114, 'history_consistent': 0.04}

CORRELATION
  Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
    2026-09-14 03:55  analytics-staging-worker-01 fired    cpu_pct (CRIT)
    2026-09-14 03:55  analytics-staging-worker-01 fired    cpu_pct (WARN)
    2026-09-14 05:55  analytics-staging-worker-01 resolved cpu_pct (CRIT)
    2026-09-14 05:55  analytics-staging-worker-01 resolved cpu_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=65d  7d slope=0.796/day  30d slope=0.026/day  shape(10d)=step  same-weekday median=22.7
  memory_used_pct          history=65d  7d slope=0.077/day  30d slope=0.019/day  shape(10d)=flat  same-weekday median=52.7
  cpu_credit_balance       history=65d  7d slope=-8.799/day  30d slope=-0.19/day  shape(10d)=irregular  same-weekday median=413.3

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Find the scheduled job that starts at that time
        Match the alert start time with cron / timers / orchestrator schedules.
        $ aws ssm send-command --instance-ids i-33c31443a0c115b3a --document-name AWS-RunShellScript --parameters '{"commands":["crontab -l; ls /etc/cron.d"]}'   # Cron entries
        $ aws ssm send-command --instance-ids i-33c31443a0c115b3a --document-name AWS-RunShellScript --parameters '{"commands":["systemctl list-timers --all | head -20"]}'   # systemd timers
  [FIX] Give the job its own capacity or move it to an off-peak window  [disruptive]
        Run it on a larger/separate node (t3.small -> t3.medium) or spread it over a longer window with a lower CPU share.
        $! aws ec2 stop-instances --instance-ids i-33c31443a0c115b3a   # Stop the instance (brief outage)
        $! aws ec2 modify-instance-attribute --instance-id i-33c31443a0c115b3a --instance-type "{\"Value\": \"t3.medium\"}"   # Change instance type
        $! aws ec2 start-instances --instance-ids i-33c31443a0c115b3a   # Start the instance
  [PREVENT] Tune the alert for the known window
        Add a maintenance-window suppression or a job-aware threshold so the on-call is not paged for expected load, and keep a paging alert for the job running longer than usual.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not treat every occurrence as an incident - fix the schedule/capacity once.
  x Do not disable the alert entirely; keep a duration-based alert.
VERIFY: Next scheduled run finishes with CPU below 75%, or the alert is suppressed inside the agreed window.
IF IGNORED: 1h - Job duration stretches and overlaps other work.  |  24h - Recurring pages train on-call to ignore the alert.  |  7d - Job growth eventually causes a missed deadline.

EXPLANATION (template)
  summary: analytics-staging-worker-01 raised 2 alert(s) on cpu_pct starting 2026-09-14 03:55 (already resolved). Diagnosis: Recurring scheduled load saturates CPU (seasonal pattern) - priority P3. The same alert fires at the same weekday and hour again and again - this is a schedule (batch job, backup, report), not a fault.
  why_this_cause: This cause was chosen because: this is the 6th alert on this weekday/hour - a schedule, not a one-off incident; CPU plateau standard deviation is 0.8. Other explanations were considered and ranked lower: CPU saturated by a runaway process / job (traffic is normal) (score 0.53). Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Find the scheduled job that starts at that time; 2) Give the job its own capacity or move it to an off-peak window. Avoid: Do not treat every occurrence as an incident - fix the schedule/capacity once. Do not disable the alert entirely; keep a duration-based alert.
  what_to_watch: Next scheduled run finishes with CPU below 75%, or the alert is suppressed inside the agreed window.
  confidence_note: Confidence 91%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Memory leak pattern on shop-prod-app-01   (Azure / Virtual_Machines / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC2 - Memory pressure
root cause      : MEMORY_LEAK - Progressive memory growth (leak-like)   confidence 92%
incident window : first alert 2026-08-31 15:55  last alert 2026-09-10 12:55  resolved 2026-09-14 10:55   (revision 6)

ALERTS (source)
  - WARN memory_used_pct          >     thr=75.0 observed=75.63  fired 2026-08-31 15:55  resolved 2026-08-31 20:55
  - WARN memory_used_pct          >     thr=75.0 observed=79.33  fired 2026-09-01 13:55  resolved 2026-09-01 22:55
  - WARN memory_used_pct          >     thr=75.0 observed=76.48  fired 2026-09-02 11:55  resolved 2026-09-02 23:55
  - WARN memory_used_pct          >     thr=75.0 observed=76.99  fired 2026-09-03 10:55  resolved 2026-09-05 05:55
  - WARN memory_used_pct          >     thr=75.0 observed=76.5  fired 2026-09-05 07:55  resolved 2026-09-14 10:55
  - CRIT memory_used_pct          >     thr=90.0 observed=91.2  fired 2026-09-10 12:55  resolved 2026-09-10 19:55
  - CRIT memory_used_pct          >     thr=90.0 observed=91.58  fired 2026-09-11 12:55  resolved 2026-09-11 23:55
  - CRIT memory_used_pct          >     thr=90.0 observed=91.27  fired 2026-09-12 11:55  resolved 2026-09-12 21:55
  - CRIT memory_used_pct          >     thr=90.0 observed=91.35  fired 2026-09-13 08:55  resolved 2026-09-14 10:55

WHY THIS ROOT CAUSE (evidence)
  + memory grew 1.71 points/day over the last 7 days (linear fit r2=0.88)
  + the multi-day shape is 'linear_up'
  + the largest hourly rise is 2.9 points
  + the 10-day shape is 'linear_up'
  considered and ranked lower
  ~ Step increase in steady-state memory (release / config change) (score 0.40) - argued against by: expected a step change (or an hourly jump of 8+ points), but the daily series shape is 'linear_up' and the largest hourly jump is 2.9 points; expected memory to have stopped climbing, but the 7-day slope is 1.71 points/day
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on memory_used_pct.
    2026-08-31 15:55  shop-prod-app-01         fired    memory_used_pct (WARN)
    2026-08-31 20:55  shop-prod-app-01         resolved memory_used_pct (WARN)
    2026-09-01 13:55  shop-prod-app-01         fired    memory_used_pct (WARN)
    2026-09-01 22:55  shop-prod-app-01         resolved memory_used_pct (WARN)
    2026-09-02 11:55  shop-prod-app-01         fired    memory_used_pct (WARN)
    2026-09-02 23:55  shop-prod-app-01         resolved memory_used_pct (WARN)
    2026-09-03 10:55  shop-prod-app-01         fired    memory_used_pct (WARN)
    2026-09-05 05:55  shop-prod-app-01         resolved memory_used_pct (WARN)
    2026-09-05 07:55  shop-prod-app-01         fired    memory_used_pct (WARN)
    2026-09-10 12:55  shop-prod-app-01         fired    memory_used_pct (CRIT)
    2026-09-10 19:55  shop-prod-app-01         resolved memory_used_pct (CRIT)
TRENDS (seasonality-aware)
  cpu_pct                  history=61d  7d slope=1.386/day  30d slope=0.044/day  shape(10d)=irregular  same-weekday median=40.1
  memory_used_pct          history=61d  7d slope=1.715/day  30d slope=1.066/day  shape(10d)=linear_up  same-weekday median=59.5
  network_in_bytes         history=61d  7d slope=447067.435/day  30d slope=4650.179/day  shape(10d)=irregular  same-weekday median=14351341.7
  network_out_bytes        history=61d  7d slope=308208.381/day  30d slope=-612.178/day  shape(10d)=irregular  same-weekday median=10617806.9

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Find the process that owns the growth
        Compare resident memory of the top processes now vs. the deploy that started the climb; capture a heap profile/dump of the suspect while it is still growing.
        $ az vm run-command invoke -g shop-prod-rg -n shop-prod-app-01 --command-id RunShellScript --scripts "ps -eo pid,rss,pmem,etime,comm --sort=-rss | head -15; free -m"   # Top memory consumers
  [NOW] Schedule a controlled restart of the leaking service in a maintenance window  [disruptive]
        A rolling restart resets memory and buys time. Do it before memory reaches the OOM-kill zone (90%+), one node at a time.
  [FIX] Temporary headroom: move to the next size while the fix is developed  [disruptive]
        Standard_D2s_v5 -> Standard_D4s_v5 gives days of headroom. Treat it as a stopgap, not a fix.
        $! az vm resize -g shop-prod-rg -n shop-prod-app-01 --size Standard_D4s_v5   # Resize (the VM restarts)
  [FIX] Ship the code fix and set a memory limit / restart policy
        Bisect releases around the moment the slope started; add a container/systemd memory limit so a leak cannot take the whole VM.
  [PREVENT] Alert on the slope, not just the level
        A trend alert (memory rising >0.5 points/day for 3 days) catches leaks days before the threshold.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not add CPU capacity - CPU pressure here is a consequence of garbage-collection/swap, not the cause.
  x Do not restart during peak traffic hours.
VERIFY: After the restart, memory returns to its pre-incident level and no longer climbs day over day.
IF IGNORED: 1h - Swap/GC thrash raises CPU and latency.  |  24h - OOM-killer terminates the process unexpectedly.  |  7d - Repeated crashes and data loss for in-memory state.

EXPLANATION (template)
  summary: shop-prod-app-01 raised 6 alert(s) on memory_used_pct starting 2026-08-31 15:55 (still active). Diagnosis: Progressive memory growth (leak-like) - priority P1. Memory has grown 1.71 points/day for a week in a straight line (now ~88%), independent of traffic - the signature of a leak. At the current slope memory would reach 100% in about 7 day(s) (trend extrapolation, for urgency only).
  why_this_cause: This cause was chosen because: memory grew 1.71 points/day over the last 7 days (linear fit r2=0.88); the multi-day shape is 'linear_up'; the largest hourly rise is 2.9 points; the 10-day shape is 'linear_up'. Other explanations were considered and ranked lower: Step increase in steady-state memory (release / config change) (score 0.40). Same resource: alerts on memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Find the process that owns the growth; 2) Schedule a controlled restart of the leaking service in a maintenance window; 3) Temporary headroom: move to the next size while the fix is developed; 4) Ship the code fix and set a memory limit / restart policy. Avoid: Do not add CPU capacity - CPU pressure here is a consequence of garbage-collection/swap, not the cause. Do not restart during peak traffic hours.
  what_to_watch: After the restart, memory returns to its pre-incident level and no longer climbs day over day.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P3] Memory level stepped up on analytics-staging-app-01   (GCP / Compute_Engine / resolved)
priority reason : highest source alert severity is Warning; alerts already resolved
use case        : UC2 - Memory pressure
root cause      : MEMORY_STEP_CHANGE - Step increase in steady-state memory (release / config change)   confidence 92%
incident window : first alert 2026-08-20 12:55  last alert 2026-08-20 12:55  resolved 2026-09-06 09:55   (revision 2)

ALERTS (source)
  - WARN memory_used_pct          >     thr=75.0 observed=84.85  fired 2026-08-20 12:55  resolved 2026-09-06 09:55

WHY THIS ROOT CAUSE (evidence)
  + average memory is 14.3 points above its pre-incident level
  + the daily series shape is 'step' and the largest hourly jump is 14.7 points
  + the 7-day slope is 1.76 points/day
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on memory_used_pct; quiet metrics: cpu_pct, network_in_bytes, network_out_bytes.
    2026-08-20 12:55  analytics-staging-app-01 fired    memory_used_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=40d  7d slope=0.981/day  30d slope=0.004/day  shape(10d)=irregular  same-weekday median=39.8
  memory_used_pct          history=40d  7d slope=1.759/day  30d slope=0.127/day  shape(10d)=step  same-weekday median=59.0
  network_in_bytes         history=40d  7d slope=501434.592/day  30d slope=11754.154/day  shape(10d)=irregular  same-weekday median=14439246.9
  network_out_bytes        history=40d  7d slope=433137.534/day  30d slope=9665.562/day  shape(10d)=irregular  same-weekday median=10731075.6

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Correlate the step with a change
        Find the deployment / config change that landed at the step time (new cache size, larger heap, new dependency).
        $ gcloud logging read 'protoPayload.serviceName="compute.googleapis.com" AND protoPayload.methodName:"compute."' --freshness=6h --limit=20   # Recent control-plane changes
        $ gcloud compute ssh analytics-staging-app-01 --zone us-central1-a --command "ps -eo pid,rss,pmem,etime,comm --sort=-rss | head -15; free -m"   # Top memory consumers
  [FIX] Roll back or tune the change
        If the extra memory is not intended, roll the release back or reduce the cache/heap setting. If intended, update capacity and the alert baseline.
  [FIX] Right-size if the new footprint is permanent  [disruptive]
        n2-standard-2 -> n2-standard-4 restores headroom.
        $! gcloud compute instances stop analytics-staging-app-01 --zone us-central1-a   # Stop the instance (brief outage)
        $! gcloud compute instances set-machine-type analytics-staging-app-01 --zone us-central1-a --machine-type n2-standard-4   # Change machine type
        $! gcloud compute instances start analytics-staging-app-01 --zone us-central1-a   # Start the instance
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not schedule restarts as a fix - memory will simply return to the new level.
  x Do not hunt a leak: the flat shape after the step rules it out.
VERIFY: Memory returns to its previous level after rollback, or stays flat with >=25% headroom after resizing.
IF IGNORED: 1h - Little immediate risk - memory is flat.  |  24h - Peak-hour usage may cross 90% and trigger swapping.  |  7d - No headroom for the next traffic increase.

EXPLANATION (template)
  summary: analytics-staging-app-01 raised 1 alert(s) on memory_used_pct starting 2026-08-20 12:55 (still active). Diagnosis: Step increase in steady-state memory (release / config change) - priority P2. Steady-state memory jumped to ~74% in one step and is flat since - a release or configuration change raised the footprint; it is not leaking.
  why_this_cause: This cause was chosen because: average memory is 14.3 points above its pre-incident level; the daily series shape is 'step' and the largest hourly jump is 14.7 points; the 7-day slope is 1.76 points/day. Same resource: alerts on memory_used_pct; quiet metrics: cpu_pct, network_in_bytes, network_out_bytes.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Correlate the step with a change; 2) Roll back or tune the change; 3) Right-size if the new footprint is permanent. Avoid: Do not schedule restarts as a fix - memory will simply return to the new level. Do not hunt a leak: the flat shape after the step rules it out.
  what_to_watch: Memory returns to its previous level after rollback, or stays flat with >=25% headroom after resizing.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Burstable CPU capacity exhausted on shop-prod-worker-01   (AWS / EC2 / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC3 - Burst-credit exhaustion
root cause      : CREDIT_EXHAUSTION - Burstable CPU credits exhausted - instance throttled to baseline   confidence 86%
incident window : first alert 2026-08-17 20:55  last alert 2026-08-17 21:55  resolved 2026-08-24 10:55   (revision 2)

ALERTS (source)
  - WARN cpu_credit_balance       <     thr=20.0 observed=8.71  fired 2026-08-17 20:55  resolved 2026-08-24 10:55
  - CRIT cpu_credit_balance       <     thr=5.0 observed=0.01  fired 2026-08-17 21:55  resolved 2026-08-18 23:55
  - CRIT cpu_credit_balance       <     thr=5.0 observed=3.27  fired 2026-08-19 01:55  resolved 2026-08-19 23:55
  - CRIT cpu_credit_balance       <     thr=5.0 observed=4.66  fired 2026-08-20 03:55  resolved 2026-08-21 23:55
  - CRIT cpu_credit_balance       <     thr=5.0 observed=0.56  fired 2026-08-22 02:55  resolved 2026-08-22 23:55
  - CRIT cpu_credit_balance       <     thr=5.0 observed=0.0  fired 2026-08-23 07:55  resolved 2026-08-24 08:55

WHY THIS ROOT CAUSE (evidence)
  + the credit balance fell to 0.0 (critical below 5)
  + peak CPU was 45.7% against an instance baseline of 20.0%
  + the balance is -392.9 versus its pre-incident level (max 576)
  facts that do not fit perfectly
  - expected a prolonged episode, but the incident has lasted 3.1h
  confidence parts: {'base': 0.3, 'evidence_score': 0.441, 'margin': 0.12}

CORRELATION
  Same resource: alerts on cpu_credit_balance; quiet metrics: memory_used_pct.
    2026-08-17 20:55  shop-prod-worker-01      fired    cpu_credit_balance (WARN)
    2026-08-17 21:55  shop-prod-worker-01      fired    cpu_credit_balance (CRIT)
TRENDS (seasonality-aware)
  cpu_pct                  history=37d  7d slope=2.748/day  30d slope=0.188/day  shape(10d)=step  same-weekday median=15.3
  memory_used_pct          history=37d  7d slope=0.169/day  30d slope=0.024/day  shape(10d)=irregular  same-weekday median=52.4
  cpu_credit_balance       history=37d  7d slope=-51.769/day  30d slope=-3.297/day  shape(10d)=step  same-weekday median=568.1

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Confirm throttling and see what drives the sustained demand
        CPU is pinned at the baseline while the credit balance is empty - work is being throttled. Find what is using CPU for hours a day.
        $ aws ssm send-command --instance-ids i-9fa5580ba5f47d783 --document-name AWS-RunShellScript --parameters '{"commands":["ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"]}'   # Top CPU processes
        $ aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-9fa5580ba5f47d783 --start-time <ISO-start> --end-time <ISO-end> --period 300 --statistics Average Maximum   # Pull the raw metric to confirm the pattern
  [NOW] Switch the instance to unlimited credit mode (immediate relief, may add cost)
        Unlimited mode removes the throttle immediately; surplus credits are billed. No restart needed.
        $! aws ec2 modify-instance-credit-specification --instance-credit-specification "InstanceId=i-9fa5580ba5f47d783,CpuCredits=unlimited"   # Enable unlimited credits
  [FIX] Move the workload to a non-burstable size  [disruptive]
        The sustained demand exceeds the burst baseline (t3.small). m5.large has no credit model and is cheaper than paying for unlimited bursting long-term.
        $! aws ec2 stop-instances --instance-ids i-9fa5580ba5f47d783   # Stop the instance (brief outage)
        $! aws ec2 modify-instance-attribute --instance-id i-9fa5580ba5f47d783 --instance-type "{\"Value\": \"m5.large\"}"   # Change instance type
        $! aws ec2 start-instances --instance-ids i-9fa5580ba5f47d783   # Start the instance
  [PREVENT] Alert while there is still balance
        Alert at ~50% of the maximum balance and on a falling multi-day trend, not only at empty.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not reboot - credits are not restored by a restart.
  x Do not read the flat CPU line as 'healthy': it is the throttle.
VERIFY: Credit balance (or scheduler wait) recovers and CPU can exceed the baseline during peaks.
IF IGNORED: 1h - Requests slow to baseline-speed CPU.  |  24h - Queues build, timeouts appear.  |  7d - Recurring degradation every busy day.

EXPLANATION (template)
  summary: shop-prod-worker-01 raised 2 alert(s) on cpu_credit_balance starting 2026-08-17 20:55 (still active). Diagnosis: Burstable CPU credits exhausted - instance throttled to baseline - priority P1. Demand has exceeded the burst baseline for days, the credit balance reached zero and CPU is now capped at ~31%. Performance drops even though CPU looks 'moderate'.
  why_this_cause: This cause was chosen because: the credit balance fell to 0.0 (critical below 5); peak CPU was 45.7% against an instance baseline of 20.0%; the balance is -392.9 versus its pre-incident level (max 576). Points that do not fit perfectly: expected a prolonged episode, but the incident has lasted 3.1h. Same resource: alerts on cpu_credit_balance; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Confirm throttling and see what drives the sustained demand; 2) Switch the instance to unlimited credit mode (immediate relief, may add cost); 3) Move the workload to a non-burstable size. Avoid: Do not reboot - credits are not restored by a restart. Do not read the flat CPU line as 'healthy': it is the throttle.
  what_to_watch: Credit balance (or scheduler wait) recovers and CPU can exceed the baseline during peaks.
  confidence_note: Confidence 86%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Burstable CPU capacity exhausted on shop-prod-worker-01   (GCP / Compute_Engine / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC3 - Burst-credit exhaustion
root cause      : CREDIT_EXHAUSTION - Burstable CPU credits exhausted - instance throttled to baseline   confidence 92%
incident window : first alert 2026-08-16 12:55  last alert 2026-08-16 15:55  resolved 2026-08-22 22:55   (revision 7)

ALERTS (source)
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1259.16  fired 2026-08-16 12:55  resolved 2026-08-16 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1336.65  fired 2026-08-16 15:55  resolved 2026-08-16 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1696.01  fired 2026-08-17 07:55  resolved 2026-08-17 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1696.01  fired 2026-08-17 08:55  resolved 2026-08-17 15:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1296.67  fired 2026-08-17 17:55  resolved 2026-08-17 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1941.21  fired 2026-08-18 07:55  resolved 2026-08-18 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1941.21  fired 2026-08-18 08:55  resolved 2026-08-18 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1732.68  fired 2026-08-19 07:55  resolved 2026-08-19 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1744.1  fired 2026-08-19 08:55  resolved 2026-08-19 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1809.4  fired 2026-08-20 07:55  resolved 2026-08-20 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1809.4  fired 2026-08-20 08:55  resolved 2026-08-20 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1692.13  fired 2026-08-21 07:55  resolved 2026-08-21 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1692.13  fired 2026-08-21 08:55  resolved 2026-08-21 22:55
  - WARN cpu_scheduler_wait_sec   >     thr=300.0 observed=1996.22  fired 2026-08-22 07:55  resolved 2026-08-22 22:55
  - CRIT cpu_scheduler_wait_sec   >     thr=1200.0 observed=1996.22  fired 2026-08-22 08:55  resolved 2026-08-22 22:55

WHY THIS ROOT CAUSE (evidence)
  + vCPU scheduler wait reached 1486.5 s/h (alert at 300)
  + average CPU is 31.0% against a ~25.0% shared-core baseline
  + scheduler wait is 564.1 s/h above its pre-incident level
  + the incident has lasted 10.0h
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on cpu_scheduler_wait_sec; quiet metrics: memory_used_pct.
    2026-08-16 12:55  shop-prod-worker-01      fired    cpu_scheduler_wait_sec (WARN)
    2026-08-16 15:55  shop-prod-worker-01      fired    cpu_scheduler_wait_sec (CRIT)
    2026-08-16 22:55  shop-prod-worker-01      resolved cpu_scheduler_wait_sec (WARN)
    2026-08-16 22:55  shop-prod-worker-01      resolved cpu_scheduler_wait_sec (CRIT)
TRENDS (seasonality-aware)
  cpu_pct                  history=36d  7d slope=3.706/day  30d slope=0.292/day  shape(10d)=step  same-weekday median=13.8
  memory_used_pct          history=36d  7d slope=0.086/day  30d slope=0.026/day  shape(10d)=irregular  same-weekday median=51.8
  cpu_scheduler_wait_sec   history=36d  7d slope=60.408/day  30d slope=3.643/day  shape(10d)=step  same-weekday median=11.7

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Confirm throttling and see what drives the sustained demand
        CPU is pinned at the baseline while the credit balance is empty - work is being throttled. Find what is using CPU for hours a day.
        $ gcloud compute ssh shop-prod-worker-01 --zone us-central1-a --command "ps -eo pid,pcpu,pmem,etime,comm --sort=-pcpu | head -15"   # Top CPU processes
        $ gcloud compute instances describe shop-prod-worker-01 --zone us-central1-a --format='value(status,machineType)'   # Pull the raw metric to confirm the pattern
  [FIX] Move the workload to a non-burstable size  [disruptive]
        The sustained demand exceeds the burst baseline (e2-small). e2-standard-2 has no credit model and is cheaper than paying for unlimited bursting long-term.
        $! gcloud compute instances stop shop-prod-worker-01 --zone us-central1-a   # Stop the instance (brief outage)
        $! gcloud compute instances set-machine-type shop-prod-worker-01 --zone us-central1-a --machine-type e2-standard-2   # Change machine type
        $! gcloud compute instances start shop-prod-worker-01 --zone us-central1-a   # Start the instance
  [PREVENT] Alert while there is still balance
        Alert at ~50% of the maximum balance and on a falling multi-day trend, not only at empty.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not reboot - credits are not restored by a restart.
  x Do not read the flat CPU line as 'healthy': it is the throttle.
VERIFY: Credit balance (or scheduler wait) recovers and CPU can exceed the baseline during peaks.
IF IGNORED: 1h - Requests slow to baseline-speed CPU.  |  24h - Queues build, timeouts appear.  |  7d - Recurring degradation every busy day.

EXPLANATION (template)
  summary: shop-prod-worker-01 raised 2 alert(s) on cpu_scheduler_wait_sec starting 2026-08-16 12:55 (already resolved). Diagnosis: Burstable CPU credits exhausted - instance throttled to baseline - priority P2. Demand has exceeded the burst baseline for days, the credit balance reached zero and CPU is now capped at ~31%. Performance drops even though CPU looks 'moderate'.
  why_this_cause: This cause was chosen because: vCPU scheduler wait reached 1486.5 s/h (alert at 300); average CPU is 31.0% against a ~25.0% shared-core baseline; scheduler wait is 564.1 s/h above its pre-incident level; the incident has lasted 10.0h. Same resource: alerts on cpu_scheduler_wait_sec; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Confirm throttling and see what drives the sustained demand; 2) Move the workload to a non-burstable size. Avoid: Do not reboot - credits are not restored by a restart. Do not read the flat CPU line as 'healthy': it is the throttle.
  what_to_watch: Credit balance (or scheduler wait) recovers and CPU can exceed the baseline during peaks.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P3] Disk filled suddenly on shop-prod-db-01   (GCP / Compute_Engine / resolved)
priority reason : highest source alert severity is Warning; alerts already resolved
use case        : UC4 - Disk capacity
root cause      : DISK_SUDDEN_FILL - Sudden disk fill (dump / export / runaway writer)   confidence 92%
incident window : first alert 2026-08-26 12:55  last alert 2026-08-26 12:55  resolved 2026-08-28 15:55   (revision 2)

ALERTS (source)
  - WARN disk_used_pct            >     thr=75.0 observed=82.37  fired 2026-08-26 12:55  resolved 2026-08-28 15:55

WHY THIS ROOT CAUSE (evidence)
  + disk usage rose 19.7 points within hours (shape 'step')
  + disk usage is 19.7 points above its pre-incident level
  + disk writes peaked at 6.5x their baseline
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on disk_used_pct; quiet metrics: cpu_pct, memory_used_pct.
    2026-08-26 12:55  shop-prod-db-01          fired    disk_used_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=46d  7d slope=0.005/day  30d slope=0.008/day  shape(10d)=irregular  same-weekday median=25.2
  memory_used_pct          history=46d  7d slope=-0.213/day  30d slope=0.025/day  shape(10d)=irregular  same-weekday median=66.7
  disk_used_pct            history=46d  7d slope=2.101/day  30d slope=0.17/day  shape(10d)=step  same-weekday median=45.2
  disk_write_bytes         history=46d  7d slope=4067524.58/day  30d slope=255645.33/day  shape(10d)=step  same-weekday median=42296090.2

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Find the newly created large files and the writer
        Look for files created in the last day and the process holding them open.
        $ gcloud compute ssh shop-prod-db-01 --zone us-central1-a --command "find / -xdev -type f -size +200M -mmin -1440 | head -20"   # Big recent files
        $ gcloud compute ssh shop-prod-db-01 --zone us-central1-a --command "df -h; du -xh / --max-depth=2 2>/dev/null | sort -rh | head -20"   # Largest directories
        $ gcloud compute ssh shop-prod-db-01 --zone us-central1-a --command "ps -eo pid,pcpu,comm --sort=-pcpu | head -10"   # Who is writing
  [NOW] Stop the writer, then move or remove the artifact (after confirming what it is)  [disruptive]
        If it is a core dump / failed export / stuck backup, stop the job first, then archive the file off-box before removing it.
  [FIX] Prevent recurrence
        Cap core dumps (ulimit / systemd-coredump limits), add quotas or a size guard to the export/backup job.
  [PREVENT] Alert on write rate spikes
        A disk-write anomaly alert would have fired hours before the volume filled.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not simply extend the volume before identifying the writer - a runaway writer will fill the larger disk too.
  x Do not delete database files or logs blindly.
VERIFY: Disk usage returns to its previous level and the write rate returns to baseline.
IF IGNORED: 1h - Writes start failing if usage passes 95%.  |  24h - Application and database errors.  |  7d - Repeat when the job runs again.

EXPLANATION (template)
  summary: shop-prod-db-01 raised 1 alert(s) on disk_used_pct starting 2026-08-26 12:55 (still active). Diagnosis: Sudden disk fill (dump / export / runaway writer) - priority P2. Disk usage jumped within a few hours to ~82% together with a burst of writes - a dump, export, backup or runaway writer, not gradual growth.
  why_this_cause: This cause was chosen because: disk usage rose 19.7 points within hours (shape 'step'); disk usage is 19.7 points above its pre-incident level; disk writes peaked at 6.5x their baseline. Same resource: alerts on disk_used_pct; quiet metrics: cpu_pct, memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Find the newly created large files and the writer; 2) Stop the writer, then move or remove the artifact (after confirming what it is); 3) Prevent recurrence. Avoid: Do not simply extend the volume before identifying the writer - a runaway writer will fill the larger disk too. Do not delete database files or logs blindly.
  what_to_watch: Disk usage returns to its previous level and the write rate returns to baseline.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Disk filling steadily on analytics-staging-db-01   (Azure / Virtual_Machines / open)
priority reason : highest source alert severity is Warning
use case        : UC4 - Disk capacity
root cause      : DISK_LOG_GROWTH - Steady disk growth (logs / temp / data accumulation)   confidence 92%
incident window : first alert 2026-09-10 05:55  last alert 2026-09-10 09:55  resolved -   (revision 1)

ALERTS (source)
  - WARN disk_used_pct            >     thr=75.0 observed=75.06  fired 2026-09-10 05:55  resolved 2026-09-10 06:55
  - WARN disk_used_pct            >     thr=75.0 observed=75.19  fired 2026-09-10 09:55  resolved -

WHY THIS ROOT CAUSE (evidence)
  + disk usage grew 1.48 points/day (linear fit r2=1.00)
  + the largest hourly rise is 0.5 points and the multi-day shape is 'linear_up'
  + disk writes peaked at 1.7x their baseline
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on disk_used_pct; quiet metrics: cpu_pct, memory_used_pct.
    2026-09-10 05:55  analytics-staging-db-01  fired    disk_used_pct (WARN)
    2026-09-10 06:55  analytics-staging-db-01  resolved disk_used_pct (WARN)
    2026-09-10 09:55  analytics-staging-db-01  fired    disk_used_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=61d  7d slope=0.347/day  30d slope=0.025/day  shape(10d)=irregular  same-weekday median=25.2
  memory_used_pct          history=61d  7d slope=0.057/day  30d slope=0.024/day  shape(10d)=irregular  same-weekday median=67.4
  disk_used_pct            history=61d  7d slope=1.483/day  30d slope=1.117/day  shape(10d)=linear_up  same-weekday median=45.6
  disk_write_bytes         history=61d  7d slope=1540189.39/day  30d slope=716287.025/day  shape(10d)=irregular  same-weekday median=44604354.5

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Find what is growing
        Largest directories and the log volume; steady growth is almost always unrotated logs, temp files or a data set.
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-db-01 --command-id RunShellScript --scripts "df -h; du -xh / --max-depth=2 2>/dev/null | sort -rh | head -25"   # Largest directories
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-db-01 --command-id RunShellScript --scripts "du -sh /var/log/* 2>/dev/null | sort -rh | head; journalctl --disk-usage"   # Log volume
  [NOW] Free space safely (rotate/compress/archive - never delete blindly)
        Force a log rotation, compress or ship old logs to object storage, vacuum the journal. Keep at least 15% free.
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-db-01 --command-id RunShellScript --scripts "logrotate -f /etc/logrotate.conf"   # Rotate logs now
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-db-01 --command-id RunShellScript --scripts "journalctl --vacuum-time=7d"   # Trim the journal to 7 days
  [FIX] Extend the volume (online)
        Add ~50% capacity so the retention fix is not urgent.
        $! az disk update -g analytics-staging-rg -n analytics-staging-db-01_datadisk_0 --size-gb 390   # Grow the data disk
        $! sudo growpart /dev/<disk> <part#> && sudo resize2fs /dev/<partition>   # xfs: sudo xfs_growfs -d <mountpoint>   # Then extend the partition/filesystem on the host (check lsblk first)
  [PREVENT] Fix retention at the source
        Add/repair logrotate, set retention on the data, and add a disk-growth-rate alert.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not delete files by hand to 'free space' without identifying them - open handles keep space allocated anyway.
  x Do not ignore it because the alert is only a Warning: growth is linear and will hit 100%.
VERIFY: Disk usage drops below 75% and the daily growth rate falls to near zero.
IF IGNORED: 1h - Low if below 90%.  |  24h - Writes fail (logs, database) once the volume is full.  |  7d - Service outage / database corruption risk when the disk hits 100%.

EXPLANATION (template)
  summary: analytics-staging-db-01 raised 2 alert(s) on disk_used_pct starting 2026-09-10 05:55 (still active). Diagnosis: Steady disk growth (logs / temp / data accumulation) - priority P2. Disk usage climbs 1.48 points/day in a smooth line (now ~75%) - logs/temp/data accumulating faster than it is cleaned. At this rate the volume is full in about 17 day(s) (trend extrapolation, for urgency only).
  why_this_cause: This cause was chosen because: disk usage grew 1.48 points/day (linear fit r2=1.00); the largest hourly rise is 0.5 points and the multi-day shape is 'linear_up'; disk writes peaked at 1.7x their baseline. Same resource: alerts on disk_used_pct; quiet metrics: cpu_pct, memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Find what is growing; 2) Free space safely (rotate/compress/archive - never delete blindly); 3) Extend the volume (online). Avoid: Do not delete files by hand to 'free space' without identifying them - open handles keep space allocated anyway. Do not ignore it because the alert is only a Warning: growth is linear and will hit 100%.
  what_to_watch: Disk usage drops below 75% and the daily growth rate falls to near zero.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Abrupt inbound traffic anomaly on shop-prod-web-01   (AWS / EC2 / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC5 - Network anomaly
root cause      : NETWORK_INGRESS_ANOMALY - Abrupt inbound-traffic anomaly (attack / scan / misbehaving client)   confidence 92%
incident window : first alert 2026-08-31 03:55  last alert 2026-08-31 03:55  resolved 2026-08-31 05:55   (revision 1)

ALERTS (source)
  - CRIT network_in_bytes         surge thr=235736678.64 observed=368713339.85  fired 2026-08-31 03:55  resolved 2026-08-31 05:55
  - WARN network_in_bytes         surge thr=117868339.32 observed=368713339.85  fired 2026-08-31 03:55  resolved 2026-08-31 05:55

WHY THIS ROOT CAUSE (evidence)
  + network-in peaked at 7.9x its same-hour baseline
  + network-in changed by x6.6 between two consecutive hours
  + CPU stayed below its alert thresholds
  + network-out peaked at 1.2x baseline
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on network_in_bytes; quiet metrics: memory_used_pct, network_out_bytes.
    2026-08-31 03:55  shop-prod-web-01         fired    network_in_bytes (CRIT)
    2026-08-31 03:55  shop-prod-web-01         fired    network_in_bytes (WARN)
    2026-08-31 05:55  shop-prod-web-01         resolved network_in_bytes (CRIT)
    2026-08-31 05:55  shop-prod-web-01         resolved network_in_bytes (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=51d  7d slope=-0.936/day  30d slope=0.001/day  shape(10d)=irregular  same-weekday median=35.9
  memory_used_pct          history=51d  7d slope=-0.066/day  30d slope=0.021/day  shape(10d)=irregular  same-weekday median=57.9
  network_in_bytes         history=51d  7d slope=-545847.712/day  30d slope=217529.771/day  shape(10d)=irregular  same-weekday median=110206425.0
  network_out_bytes        history=51d  7d slope=-13273926.118/day  30d slope=-143306.67/day  shape(10d)=step  same-weekday median=306686822.0

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Identify the sources
        Top source addresses / paths from flow logs and access logs; check whether they are known clients.
        $ aws logs start-query --log-group-name <vpc-flow-log-group> --start-time <epoch-start> --end-time <epoch-end> --query-string "filter interfaceId = '<eni-id>' | stats sum(bytes) as b by srcAddr | sort b desc | limit 20"   # Top talkers from VPC flow logs (CloudWatch Logs Insights)
        $ aws ssm send-command --instance-ids i-9bf1b988d6e0e7680 --document-name AWS-RunShellScript --parameters '{"commands":["ss -s"]}'   # Connections by state
  [NOW] Rate-limit or block at the edge (WAF / firewall), not on the VM
        Apply a rate rule or a source block at the load balancer / WAF / firewall for the offending sources.
        $ aws ec2 describe-security-groups --filters Name=group-name,Values=<sg-name>   # Review security group rules
  [FIX] Add a WAF / rate-limit policy permanently
        Cloud WAF or Cloud Armor style rules and per-client rate limits.
  [PREVENT] Route the network anomaly alert to security
        This pattern is a security signal even when CPU is fine.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not scale the VM up to absorb it - you would pay to serve unwanted traffic.
  x Do not block by broad ranges before you know the sources (risk of blocking real customers).
VERIFY: Inbound traffic returns to its seasonal band and the step disappears from the hourly series.
IF IGNORED: 1h - CPU and bandwidth costs rise; service may degrade if the traffic grows.  |  24h - Possible application-layer abuse or data scraping.  |  7d - Repeated probing may turn into a targeted attack.

EXPLANATION (template)
  summary: shop-prod-web-01 raised 2 alert(s) on network_in_bytes starting 2026-08-31 03:55 (already resolved). Diagnosis: Abrupt inbound-traffic anomaly (attack / scan / misbehaving client) - priority P2. Inbound traffic stepped up to about 7.9x its normal level within an hour and stayed flat - human traffic ramps, this looks like automation (scan, bot, attack or a misbehaving client).
  why_this_cause: This cause was chosen because: network-in peaked at 7.9x its same-hour baseline; network-in changed by x6.6 between two consecutive hours; CPU stayed below its alert thresholds; network-out peaked at 1.2x baseline. Same resource: alerts on network_in_bytes; quiet metrics: memory_used_pct, network_out_bytes.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Identify the sources; 2) Rate-limit or block at the edge (WAF / firewall), not on the VM; 3) Add a WAF / rate-limit policy permanently. Avoid: Do not scale the VM up to absorb it - you would pay to serve unwanted traffic. Do not block by broad ranges before you know the sources (risk of blocking real customers).
  what_to_watch: Inbound traffic returns to its seasonal band and the step disappears from the hourly series.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Outbound traffic spike on analytics-staging-web-01 with normal inbound   (Azure / Virtual_Machines / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC5 - Network anomaly
root cause      : NETWORK_EGRESS_ANOMALY - Outbound-traffic spike with normal inbound (bulk transfer / exfiltration-like)   confidence 92%
incident window : first alert 2026-08-26 21:55  last alert 2026-08-26 21:55  resolved 2026-08-27 08:55   (revision 2)

ALERTS (source)
  - CRIT network_out_bytes        surge thr=258192524.14 observed=346980749.4  fired 2026-08-26 21:55  resolved 2026-08-27 08:55
  - WARN network_out_bytes        surge thr=129096262.07 observed=346980749.4  fired 2026-08-26 21:55  resolved 2026-08-27 08:55

WHY THIS ROOT CAUSE (evidence)
  + network-out peaked at 7.1x its same-hour baseline
  + network-in peaked at 1.3x baseline
  + CPU averaged 1.0x its baseline
  + the outbound rate stayed 2.5x+ above baseline for 4 or more hours
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on network_out_bytes; quiet metrics: cpu_pct, memory_used_pct, network_in_bytes.
    2026-08-26 21:55  analytics-staging-web-01 fired    network_out_bytes (CRIT)
    2026-08-26 21:55  analytics-staging-web-01 fired    network_out_bytes (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=46d  7d slope=0.417/day  30d slope=0.018/day  shape(10d)=irregular  same-weekday median=35.6
  memory_used_pct          history=46d  7d slope=-0.057/day  30d slope=0.03/day  shape(10d)=irregular  same-weekday median=58.2
  network_in_bytes         history=46d  7d slope=339252.785/day  30d slope=17336.274/day  shape(10d)=irregular  same-weekday median=21451121.3
  network_out_bytes        history=46d  7d slope=5673535.716/day  30d slope=328607.397/day  shape(10d)=step  same-weekday median=60410944.9

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Find the destination and the process
        Which remote addresses receive the data, and which process opened the connections?
        $ az network watcher flow-log list --location centralus -o table   # Check NSG flow-log configuration (then query Traffic Analytics for top talkers)
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-web-01 --command-id RunShellScript --scripts "ss -tnp state established | head -30"   # Established connections
  [NOW] If the destination is unknown, restrict outbound from this VM and involve security  [disruptive]
        Tighten egress rules to the known destinations until the transfer is explained.
  [FIX] Confirm or fix legitimate causes
        Scheduled backups, sync jobs, log shipping to a new target, or a mirrored data store commonly cause this.
        $ az vm run-command invoke -g analytics-staging-rg -n analytics-staging-web-01 --command-id RunShellScript --scripts "crontab -l; systemctl list-timers --all | head -20"   # Recent scheduled jobs
  [PREVENT] Egress guard rails
        Egress allow-lists and a network-out anomaly alert that pages security, plus a data-transfer cost alert.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not treat this as a capacity problem - CPU and inbound are normal.
  x Do not wipe the VM before evidence (connections, process list) is captured.
VERIFY: Outbound traffic returns to its seasonal band and the destination is accounted for.
IF IGNORED: 1h - Unexplained data leaving the environment.  |  24h - Data-transfer cost spike / compliance exposure.  |  7d - Repeat transfers if unresolved.

EXPLANATION (template)
  summary: analytics-staging-web-01 raised 2 alert(s) on network_out_bytes starting 2026-08-26 21:55 (still active). Diagnosis: Outbound-traffic spike with normal inbound (bulk transfer / exfiltration-like) - priority P1. Outbound traffic ran about 7.1x its baseline for hours while inbound and CPU stayed normal - data is leaving the VM without a matching request load (bulk copy, backup, or exfiltration-like behaviour).
  why_this_cause: This cause was chosen because: network-out peaked at 7.1x its same-hour baseline; network-in peaked at 1.3x baseline; CPU averaged 1.0x its baseline; the outbound rate stayed 2.5x+ above baseline for 4 or more hours. Same resource: alerts on network_out_bytes; quiet metrics: cpu_pct, memory_used_pct, network_in_bytes.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Find the destination and the process; 2) If the destination is unknown, restrict outbound from this VM and involve security; 3) Confirm or fix legitimate causes. Avoid: Do not treat this as a capacity problem - CPU and inbound are normal. Do not wipe the VM before evidence (connections, process list) is captured.
  what_to_watch: Outbound traffic returns to its seasonal band and the destination is accounted for.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P2] Traffic to analytics-staging-web-02 vanished while the VM is healthy   (GCP / Compute_Engine / resolved)
priority reason : highest source alert severity is Critical; alerts already resolved (post-incident review)
use case        : UC5 - Network anomaly
root cause      : NETWORK_TRAFFIC_LOSS - Traffic vanished while the VM is alive (upstream routing / LB / DNS / NSG issue)   confidence 92%
incident window : first alert 2026-09-03 11:55  last alert 2026-09-03 11:55  resolved 2026-09-03 15:55   (revision 1)

ALERTS (source)
  - CRIT network_in_bytes         drop  thr=4287097.03 observed=673514.83  fired 2026-09-03 11:55  resolved 2026-09-03 15:55
  - CRIT network_out_bytes        drop  thr=10693944.02 observed=1603806.33  fired 2026-09-03 11:55  resolved 2026-09-03 15:55

WHY THIS ROOT CAUSE (evidence)
  + network traffic fell to 0.03x of its normal level
  + the VM is running and still reports CPU/memory - not an outage of the VM itself
  + memory averaged 1.01x its usual level
  confidence parts: {'base': 0.3, 'evidence_score': 0.5, 'margin': 0.12}

CORRELATION
  Same resource: alerts on network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct.
    2026-09-03 11:55  analytics-staging-web-02 fired    network_in_bytes (CRIT)
    2026-09-03 11:55  analytics-staging-web-02 fired    network_out_bytes (CRIT)
    2026-09-03 15:55  analytics-staging-web-02 resolved network_in_bytes (CRIT)
    2026-09-03 15:55  analytics-staging-web-02 resolved network_out_bytes (CRIT)
TRENDS (seasonality-aware)
  cpu_pct                  history=54d  7d slope=-0.05/day  30d slope=0.003/day  shape(10d)=irregular  same-weekday median=35.6
  memory_used_pct          history=54d  7d slope=0.257/day  30d slope=0.045/day  shape(10d)=irregular  same-weekday median=58.7
  network_in_bytes         history=54d  7d slope=-51875.465/day  30d slope=22131.102/day  shape(10d)=irregular  same-weekday median=21848251.0
  network_out_bytes        history=54d  7d slope=-359827.122/day  30d slope=-7043.722/day  shape(10d)=irregular  same-weekday median=62279211.6

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Check the path in front of the VM
        Load-balancer health of this backend, DNS records, and recent network/security-rule changes.
        $ gcloud compute backend-services get-health <backend-service> --global   # Backend health
        $ gcloud logging read 'protoPayload.serviceName="compute.googleapis.com" AND protoPayload.methodName:"compute."' --freshness=6h --limit=20   # Recent control-plane changes
  [NOW] Verify the app answers locally
        If the local health endpoint answers, the fault is upstream of the VM.
        $ gcloud compute ssh analytics-staging-web-02 --zone us-central1-a --command "curl -s -o /dev/null -w %{http_code} http://localhost/health"   # Local health check
  [FIX] Revert the network/LB change or fix the health-check path
        Restore the previous rule / listener / DNS record; if a health probe was failing, correct the probe or the app path.
  [PREVENT] Alert on traffic drops per tier
        A sudden fall in traffic is as important as a rise; keep the drop alert on the on-call route.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not stop, deallocate or delete this VM because it looks idle - the idleness is a symptom of an upstream problem.
  x Do not restart the application: it is healthy and idle.
VERIFY: Traffic returns to its seasonal level and target/backend health shows healthy.
IF IGNORED: 1h - Customers cannot reach this node; the remaining capacity is overloaded.  |  24h - Lost transactions and SLA breach.  |  7d - n/a - this is an outage-class event.

EXPLANATION (template)
  summary: analytics-staging-web-02 raised 2 alert(s) on network_in_bytes, network_out_bytes starting 2026-09-03 11:55 (already resolved). Diagnosis: Traffic vanished while the VM is alive (upstream routing / LB / DNS / NSG issue) - priority P2. Network traffic collapsed to a few percent of normal while the VM keeps reporting CPU and memory - the VM is fine; requests are not reaching it (load balancer, DNS, routing or security-rule change).
  why_this_cause: This cause was chosen because: network traffic fell to 0.03x of its normal level; the VM is running and still reports CPU/memory - not an outage of the VM itself; memory averaged 1.01x its usual level. Same resource: alerts on network_in_bytes, network_out_bytes; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Check the path in front of the VM; 2) Verify the app answers locally; 3) Revert the network/LB change or fix the health-check path. Avoid: Do not stop, deallocate or delete this VM because it looks idle - the idleness is a symptom of an upstream problem. Do not restart the application: it is healthy and idle.
  what_to_watch: Traffic returns to its seasonal level and target/backend health shows healthy.
  confidence_note: Confidence 92%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P3] Short self-resolving spike on shop-prod-worker-01   (AWS / EC2 / resolved)
priority reason : self-resolving / alert-tuning issue
use case        : X - Cross-cutting
root cause      : TRANSIENT_SPIKE - Short self-resolving spike with no corroborating deviation   confidence 91%
incident window : first alert 2026-09-06 12:55  last alert 2026-09-06 12:55  resolved 2026-09-06 13:55   (revision 1)

ALERTS (source)
  - CRIT cpu_pct                  >     thr=90.0 observed=93.01  fired 2026-09-06 12:55  resolved 2026-09-06 13:55
  - WARN cpu_pct                  >     thr=75.0 observed=93.01  fired 2026-09-06 12:55  resolved 2026-09-06 13:55

WHY THIS ROOT CAUSE (evidence)
  + one episode of about 2.0h that resolved by itself
  + no other metric deviated from its baseline
  + no earlier alert on this metric in the previous 7 days
  confidence parts: {'base': 0.3, 'evidence_score': 0.49, 'margin': 0.12}

CORRELATION
  Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
    2026-09-06 12:55  shop-prod-worker-01      fired    cpu_pct (CRIT)
    2026-09-06 12:55  shop-prod-worker-01      fired    cpu_pct (WARN)
    2026-09-06 13:55  shop-prod-worker-01      resolved cpu_pct (CRIT)
    2026-09-06 13:55  shop-prod-worker-01      resolved cpu_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=57d  7d slope=0.546/day  30d slope=-0.063/day  shape(10d)=step  same-weekday median=14.4
  memory_used_pct          history=57d  7d slope=-0.221/day  30d slope=0.048/day  shape(10d)=irregular  same-weekday median=52.1
  cpu_credit_balance       history=57d  7d slope=-4.858/day  30d slope=2.914/day  shape(10d)=step  same-weekday median=572.6

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] No action needed - note it
        Record the time; look at what ran then (deploy, cron, health probe) only if it repeats.
  [PREVENT] Consider a longer evaluation window
        If these pages are frequent, require the condition to hold for more consecutive periods.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not resize, restart or otherwise change the resource for a single self-resolved spike.
VERIFY: The metric stays inside its normal band.
IF IGNORED: 1h - None.  |  24h - None.  |  7d - If it recurs at the same hour, re-evaluate as a scheduled load.

EXPLANATION (template)
  summary: shop-prod-worker-01 raised 2 alert(s) on cpu_pct starting 2026-09-06 12:55 (already resolved). Diagnosis: Short self-resolving spike with no corroborating deviation - priority P3. A brief spike fired the alert and cleared by itself; nothing else deviated. No corrective action is required.
  why_this_cause: This cause was chosen because: one episode of about 2.0h that resolved by itself; no other metric deviated from its baseline; no earlier alert on this metric in the previous 7 days. Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) No action needed - note it. Avoid: Do not resize, restart or otherwise change the resource for a single self-resolved spike.
  what_to_watch: The metric stays inside its normal band.
  confidence_note: Confidence 91%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

```
====================================================================================================
[P3] Alert rule flapping on shop-prod-web-02   (GCP / Compute_Engine / resolved)
priority reason : self-resolving / alert-tuning issue
use case        : X - Cross-cutting
root cause      : ALERT_FLAPPING - Alert rule flapping around its threshold (rule tuning issue, not a capacity issue)   confidence 91%
incident window : first alert 2026-08-25 10:55  last alert 2026-08-25 16:55  resolved 2026-08-25 17:55   (revision 1)

ALERTS (source)
  - WARN cpu_pct                  >     thr=75.0 observed=78.35  fired 2026-08-25 10:55  resolved 2026-08-25 11:55
  - WARN cpu_pct                  >     thr=75.0 observed=78.45  fired 2026-08-25 13:55  resolved 2026-08-25 14:55
  - WARN cpu_pct                  >     thr=75.0 observed=78.29  fired 2026-08-25 16:55  resolved 2026-08-25 17:55

WHY THIS ROOT CAUSE (evidence)
  + the same alert rule fired 3 time(s) within 24h
  + the longest episode lasted 2.0h
  + observed values were at most 4.6% above the threshold
  + no other metric deviates from its baseline
  considered and ranked lower
  ~ CPU saturated by a traffic surge (load-driven) (score 0.58) - argued against by: expected network-in elevated during the CPU-high hours, but network-in averaged 1.1x its same-hour baseline while CPU was high; expected peer nodes of the same tier to alert too (shared traffic source), but no peer node of the same tier alerts
  confidence parts: {'base': 0.3, 'evidence_score': 0.49, 'margin': 0.12}

CORRELATION
  Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct, network_in_bytes, network_out_bytes.
    2026-08-25 10:55  shop-prod-web-02         fired    cpu_pct (WARN)
    2026-08-25 11:55  shop-prod-web-02         resolved cpu_pct (WARN)
    2026-08-25 13:55  shop-prod-web-02         fired    cpu_pct (WARN)
    2026-08-25 14:55  shop-prod-web-02         resolved cpu_pct (WARN)
    2026-08-25 16:55  shop-prod-web-02         fired    cpu_pct (WARN)
    2026-08-25 17:55  shop-prod-web-02         resolved cpu_pct (WARN)
TRENDS (seasonality-aware)
  cpu_pct                  history=45d  7d slope=0.793/day  30d slope=0.096/day  shape(10d)=step  same-weekday median=36.4
  memory_used_pct          history=45d  7d slope=-0.356/day  30d slope=0.031/day  shape(10d)=irregular  same-weekday median=58.3
  network_in_bytes         history=45d  7d slope=-312409.483/day  30d slope=21846.562/day  shape(10d)=irregular  same-weekday median=22125538.7
  network_out_bytes        history=45d  7d slope=-1118436.048/day  30d slope=42053.888/day  shape(10d)=irregular  same-weekday median=63315669.6

RECOMMENDED ACTIONS - human executed, nothing is automated
  [NOW] Look at the metric shape around the threshold
        Confirm the metric oscillates within a few percent of the threshold.
        $ gcloud compute instances describe shop-prod-web-02 --zone us-central1-a --format='value(status,machineType)'   # Pull the raw metric to confirm the pattern
  [FIX] Add hysteresis / a longer evaluation window
        Fire after more consecutive periods and resolve only when clearly below (e.g. fire >=75% for 5 periods, clear <=70%).
  [PREVENT] Group the notifications
        Notify once per incident instead of per flap.
  ($ = read-only diagnostic, $! = changes the system)

DO NOT
  x Do not add capacity or restart because of the flapping alone.
VERIFY: The rule stops re-firing while the metric stays in the same range.
IF IGNORED: 1h - Alert fatigue.  |  24h - Real alerts get ignored.  |  7d - Loss of trust in monitoring.

EXPLANATION (template)
  summary: shop-prod-web-02 raised 3 alert(s) on cpu_pct starting 2026-08-25 10:55 (already resolved). Diagnosis: Alert rule flapping around its threshold (rule tuning issue, not a capacity issue) - priority P3. The metric hovers just around the alert threshold, so the same alert fires and clears repeatedly. This is an alert-tuning problem, not a capacity problem.
  why_this_cause: This cause was chosen because: the same alert rule fired 3 time(s) within 24h; the longest episode lasted 2.0h; observed values were at most 4.6% above the threshold; no other metric deviates from its baseline. Other explanations were considered and ranked lower: CPU saturated by a traffic surge (load-driven) (score 0.58). Same resource: alerts on cpu_pct; quiet metrics: memory_used_pct, network_in_bytes, network_out_bytes.
  what_to_do: Recommended steps for a human to review and approve (nothing is executed automatically): 1) Look at the metric shape around the threshold; 2) Add hysteresis / a longer evaluation window. Avoid: Do not add capacity or restart because of the flapping alone.
  what_to_watch: The rule stops re-firing while the metric stays in the same range.
  confidence_note: Confidence 91%: it comes from how many of the checks for this cause passed and how far ahead of the runner-up it is (not from a language model).
```

