"""
Mapping: resource_type → raw_metric_name → {canonical, transform}

transform(x) converts raw values to canonical units:
  - All % metrics in 0–100 range
  - GCP cpu/utilization is a 0–1 ratio → multiply by 100
  - Bytes stay as bytes, IOPS stay as ops/sec
"""


def _pct(x):
    """GCP ratio 0–1 → percentage 0–100."""
    return float(x) * 100.0


def _id(x):
    return float(x)


METRIC_REGISTRY = {
    # ── Compute ──────────────────────────────────────────────────────────────────
    "EC2": {
        "CPUUtilization":             {"canonical": "cpu_pct",                      "transform": _id},
        "cpu_usage_iowait":           {"canonical": "cpu_iowait_pct",               "transform": _id},
        "cpu_usage_user":             {"canonical": "cpu_user_pct",                 "transform": _id},
        "cpu_usage_system":           {"canonical": "cpu_system_pct",               "transform": _id},
        "cpu_usage_idle":             {"canonical": "cpu_idle_pct",                 "transform": _id},
        "mem_used_percent":           {"canonical": "memory_used_pct",              "transform": _id},
        "disk_used_percent":          {"canonical": "disk_used_pct",                "transform": _id},
        "swap_used_percent":          {"canonical": "swap_used_pct",                "transform": _id},
        "diskio_io_time":             {"canonical": "disk_io_time_ms",              "transform": _id},
        "disk_inodes_free":           {"canonical": "disk_inodes_free",             "transform": _id},
        "NetworkIn":                  {"canonical": "network_in_bytes",             "transform": _id},
        "NetworkOut":                 {"canonical": "network_out_bytes",            "transform": _id},
        "NetworkPacketsIn":           {"canonical": "network_packets_in",           "transform": _id},
        "NetworkPacketsOut":          {"canonical": "network_packets_out",          "transform": _id},
        "DiskReadBytes":              {"canonical": "disk_read_bytes",              "transform": _id},
        "DiskWriteBytes":             {"canonical": "disk_write_bytes",             "transform": _id},
        "DiskReadOps":                {"canonical": "disk_read_ops",                "transform": _id},
        "DiskWriteOps":               {"canonical": "disk_write_ops",              "transform": _id},
        "StatusCheckFailed":          {"canonical": "status_check_failed",          "transform": _id},
        "StatusCheckFailed_Instance": {"canonical": "status_check_failed_instance", "transform": _id},
        "StatusCheckFailed_System":   {"canonical": "status_check_failed_system",   "transform": _id},
        "CPUCreditBalance":           {"canonical": "cpu_credit_balance",           "transform": _id},
        "CPUCreditUsage":             {"canonical": "cpu_credit_usage",             "transform": _id},
        "CPUSurplusCreditsCharged":   {"canonical": "cpu_surplus_credits_charged",  "transform": _id},
        "CPUSurplusCreditBalance":    {"canonical": "cpu_surplus_credit_balance",   "transform": _id},
    },

    "Virtual_Machines": {
        "Percentage CPU":                         {"canonical": "cpu_pct",                          "transform": _id},
        "Available Memory Bytes":                 {"canonical": "memory_available_bytes",            "transform": _id},
        "disk/free_percent":                      {"canonical": "disk_free_pct",                    "transform": _id},
        "Inbound Flows":                          {"canonical": "network_inbound_flows",             "transform": _id},
        "Outbound Flows":                         {"canonical": "network_outbound_flows",            "transform": _id},
        "Network In Total":                       {"canonical": "network_in_bytes",                 "transform": _id},
        "Network Out Total":                      {"canonical": "network_out_bytes",                "transform": _id},
        "Network In":                             {"canonical": "network_in_bytes_legacy",          "transform": _id},
        "Network Out":                            {"canonical": "network_out_bytes_legacy",         "transform": _id},
        "OS Disk Queue Depth":                    {"canonical": "os_disk_queue_depth",              "transform": _id},
        "Data Disk Queue Depth":                  {"canonical": "data_disk_queue_depth",            "transform": _id},
        "OS Disk Read Operations/Sec":            {"canonical": "os_disk_read_ops_per_sec",         "transform": _id},
        "OS Disk Write Operations/Sec":           {"canonical": "os_disk_write_ops_per_sec",        "transform": _id},
        "Data Disk Read Operations/Sec":          {"canonical": "data_disk_read_ops_per_sec",       "transform": _id},
        "Data Disk Write Operations/Sec":         {"canonical": "data_disk_write_ops_per_sec",      "transform": _id},
        "OS Disk Read Bytes/sec":                 {"canonical": "os_disk_read_bytes_per_sec",       "transform": _id},
        "OS Disk Write Bytes/sec":                {"canonical": "os_disk_write_bytes_per_sec",      "transform": _id},
        "Data Disk Read Bytes/sec":               {"canonical": "data_disk_read_bytes_per_sec",     "transform": _id},
        "Data Disk Write Bytes/sec":              {"canonical": "data_disk_write_bytes_per_sec",    "transform": _id},
        "Disk Read Bytes":                        {"canonical": "disk_read_bytes",                  "transform": _id},
        "Disk Write Bytes":                       {"canonical": "disk_write_bytes",                 "transform": _id},
        "Disk Read Operations/Sec":               {"canonical": "disk_read_ops_per_sec",            "transform": _id},
        "Disk Write Operations/Sec":              {"canonical": "disk_write_ops_per_sec",           "transform": _id},
        "FreeSpaceMB":                            {"canonical": "disk_free_mb",                     "transform": _id},
        "\\LogicalDisk(_Total)\\% Free Space":   {"canonical": "disk_free_pct_logical",            "transform": _id},
        "CPU Credits Consumed":                   {"canonical": "cpu_credits_consumed",             "transform": _id},
        "CPU Credits Remaining":                  {"canonical": "cpu_credits_remaining",            "transform": _id},
        "Premium Data Disk Cache Read Miss":      {"canonical": "premium_data_disk_cache_miss_pct", "transform": _id},
        "Premium Data Disk Cache Read Hit":       {"canonical": "premium_data_disk_cache_hit_pct",  "transform": _id},
        "Premium OS Disk Cache Read Hit":         {"canonical": "premium_os_disk_cache_hit_pct",    "transform": _id},
        "Premium OS Disk Cache Read Miss":        {"canonical": "premium_os_disk_cache_miss_pct",   "transform": _id},
        "Inbound Flows Maximum Creation Rate":    {"canonical": "network_inbound_max_creation_rate","transform": _id},
        "Outbound Flows Maximum Creation Rate":   {"canonical": "network_outbound_max_creation_rate","transform": _id},
    },

    "Compute_Engine": {
        "compute.googleapis.com/instance/cpu/utilization":                        {"canonical": "cpu_pct",                "transform": _pct},
        "compute.googleapis.com/instance/cpu/usage_time":                         {"canonical": "cpu_usage_time_sec",     "transform": _id},
        "agent.googleapis.com/memory/percent_used":                               {"canonical": "memory_used_pct",        "transform": _id},
        "compute.googleapis.com/instance/disk/read_bytes_count":                  {"canonical": "disk_read_bytes",        "transform": _id},
        "compute.googleapis.com/instance/disk/write_bytes_count":                 {"canonical": "disk_write_bytes",       "transform": _id},
        "compute.googleapis.com/instance/network/sent_bytes_count":               {"canonical": "network_out_bytes",      "transform": _id},
        "compute.googleapis.com/instance/network/received_bytes_count":           {"canonical": "network_in_bytes",       "transform": _id},
        "agent.googleapis.com/disk/percent_used":                                 {"canonical": "disk_used_pct",          "transform": _id},
        "compute.googleapis.com/instance/cpu/scheduler_wait_time":                {"canonical": "cpu_scheduler_wait_sec","transform": _id},
        "compute.googleapis.com/instance/uptime":                                 {"canonical": "uptime_sec",             "transform": _id},
        "compute.googleapis.com/instance/integrity/early_boot_validation_status": {"canonical": "boot_validation_early",  "transform": _id},
        "compute.googleapis.com/instance/integrity/late_boot_validation_status":  {"canonical": "boot_validation_late",   "transform": _id},
    },

    "Compute": {  # OCI
        "CpuUtilization":          {"canonical": "cpu_pct",                  "transform": _id},
        "MemoryUtilization":       {"canonical": "memory_used_pct",          "transform": _id},
        "DiskBytesRead":           {"canonical": "disk_read_bytes",          "transform": _id},
        "DiskBytesWritten":        {"canonical": "disk_write_bytes",         "transform": _id},
        "DiskIopsRead":            {"canonical": "disk_read_iops",           "transform": _id},
        "DiskIopsWritten":         {"canonical": "disk_write_iops",          "transform": _id},
        "NetworksBytesIn":         {"canonical": "network_in_bytes",         "transform": _id},
        "NetworksBytesOut":        {"canonical": "network_out_bytes",        "transform": _id},
        "LoadAverage":             {"canonical": "load_average",             "transform": _id},
        "MemoryAllocationStalls":  {"canonical": "memory_allocation_stalls", "transform": _id},
    },

    "Lambda": {
        "Errors":               {"canonical": "lambda_error_count",     "transform": _id},
        "Duration":             {"canonical": "lambda_duration_ms",     "transform": _id},
        "Invocations":          {"canonical": "lambda_invocation_count","transform": _id},
        "Throttles":            {"canonical": "lambda_throttle_count",  "transform": _id},
        "ConcurrentExecutions": {"canonical": "lambda_concurrent_exec", "transform": _id},
    },

    # ── Storage ───────────────────────────────────────────────────────────────────
    "EBS": {
        "VolumeQueueLength":    {"canonical": "volume_queue_length",        "transform": _id},
        "VolumeReadBytes":      {"canonical": "volume_read_bytes",          "transform": _id},
        "VolumeWriteBytes":     {"canonical": "volume_write_bytes",         "transform": _id},
        "VolumeReadOps":        {"canonical": "volume_read_ops",            "transform": _id},
        "VolumeWriteOps":       {"canonical": "volume_write_ops",           "transform": _id},
        "VolumeTotalReadTime":  {"canonical": "volume_total_read_time_sec", "transform": _id},
        "VolumeTotalWriteTime": {"canonical": "volume_total_write_time_sec","transform": _id},
        "VolumeIdleTime":       {"canonical": "volume_idle_time_sec",       "transform": _id},
        "BurstBalance":         {"canonical": "burst_balance_pct",          "transform": _id},
    },

    "EFS": {
        "PercentIOLimit":       {"canonical": "percent_io_limit",               "transform": _id},
        "PermittedThroughput":  {"canonical": "permitted_throughput_bytes_per_sec","transform": _id},
        "TotalIOBytes":         {"canonical": "total_io_bytes",                 "transform": _id},
        "BurstCreditBalance":   {"canonical": "burst_credit_balance",           "transform": _id},
        "DataReadIOBytes":      {"canonical": "data_read_io_bytes",             "transform": _id},
        "DataWriteIOBytes":     {"canonical": "data_write_io_bytes",            "transform": _id},
        "ClientConnections":    {"canonical": "client_connections",             "transform": _id},
    },

    "S3": {
        "BucketSizeBytes":                                     {"canonical": "bucket_size_bytes", "transform": _id},
        "BytesDownloaded":                                     {"canonical": "bytes_downloaded",  "transform": _id},
        "BytesUploaded":                                       {"canonical": "bytes_uploaded",    "transform": _id},
        "storage.googleapis.com/api/request_count":            {"canonical": "api_request_count","transform": _id},
        "storage.googleapis.com/network/received_bytes_count": {"canonical": "network_in_bytes", "transform": _id},
        "storage.googleapis.com/network/sent_bytes_count":     {"canonical": "network_out_bytes","transform": _id},
    },

    "Accounts": {
        "UsedCapacity":         {"canonical": "storage_used_capacity_bytes", "transform": _id},
        "Transactions":         {"canonical": "transaction_count",           "transform": _id},
        "Egress":               {"canonical": "egress_bytes",                "transform": _id},
        "Ingress":              {"canonical": "ingress_bytes",               "transform": _id},
        "SuccessServerLatency": {"canonical": "server_latency_ms",          "transform": _id},
        "SuccessE2ELatency":    {"canonical": "e2e_latency_ms",             "transform": _id},
        "Availability":         {"canonical": "availability_pct",           "transform": _id},
    },

    "Storage_Disks": {
        "Composite Disk Read Bytes/sec":       {"canonical": "disk_read_bytes_per_sec",  "transform": _id},
        "Composite Disk Write Bytes/sec":      {"canonical": "disk_write_bytes_per_sec", "transform": _id},
        "Composite Disk Read Operations/sec":  {"canonical": "disk_read_ops_per_sec",    "transform": _id},
        "Composite Disk Write Operations/sec": {"canonical": "disk_write_ops_per_sec",   "transform": _id},
    },

    "Bucket": {
        "storage.googleapis.com/storage/total_byte_seconds":   {"canonical": "storage_byte_seconds","transform": _id},
        "storage.googleapis.com/network/received_bytes_count":  {"canonical": "network_in_bytes",    "transform": _id},
        "storage.googleapis.com/api/request_count":             {"canonical": "api_request_count",   "transform": _id},
        "storage.googleapis.com/storage/object_count":          {"canonical": "object_count",        "transform": _id},
        "storage.googleapis.com/network/sent_bytes_count":      {"canonical": "network_out_bytes",   "transform": _id},
    },

    "File_Storage": {
        "FileSystemUsage":               {"canonical": "filesystem_used_bytes",         "transform": _id},
        "FileSystemReadThroughput":      {"canonical": "read_throughput_bytes_per_sec", "transform": _id},
        "FileSystemWriteThroughput":     {"canonical": "write_throughput_bytes_per_sec","transform": _id},
        "FileSystemReadRequestsBySize":  {"canonical": "read_requests_by_size",         "transform": _id},
        "FileSystemWriteRequestsBySize": {"canonical": "write_requests_by_size",        "transform": _id},
        "MetadataIOPS":                  {"canonical": "metadata_iops",                "transform": _id},
    },

    "Recovery_Services": {
        "BackupHealthEvent": {"canonical": "backup_health_event", "transform": _id},
    },
}


def get_canonical(resource_type: str, raw_metric: str):
    """Return (canonical_name, transform_fn) or (None, None)."""
    entry = METRIC_REGISTRY.get(resource_type, {}).get(raw_metric)
    if entry:
        return entry["canonical"], entry["transform"]
    return None, None
