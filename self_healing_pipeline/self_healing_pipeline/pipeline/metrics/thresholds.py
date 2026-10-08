"""
Static thresholds per (resource_type, canonical_metric).

direction:
  "upper"       — value above warn/crit is bad (cpu, latency, queue depth)
  "lower"       — value below warn/crit is bad (availability, free space, burst balance)
  "nonzero"     — any positive value is WARN; values ≥ crit count trigger CRIT
  "anomaly_only"— no static bound; rely solely on z-score from statistical engine

The statistical engine uses daily_max for "upper" checks and daily_min for "lower" checks.
"""

THRESHOLDS: dict = {
    # ── Compute ─────────────────────────────────────────────────────────────────
    "EC2": {
        "cpu_pct":                      {"warn": 75,        "crit": 90,        "direction": "upper"},
        "cpu_iowait_pct":               {"warn": 20,        "crit": 40,        "direction": "upper"},
        "cpu_user_pct":                 {"warn": 70,        "crit": 85,        "direction": "upper"},
        "cpu_system_pct":               {"warn": 30,        "crit": 50,        "direction": "upper"},
        "cpu_idle_pct":                 {"warn": 25,        "crit": 10,        "direction": "lower"},
        "memory_used_pct":              {"warn": 75,        "crit": 90,        "direction": "upper"},
        "disk_used_pct":                {"warn": 75,        "crit": 90,        "direction": "upper"},
        "swap_used_pct":                {"warn": 50,        "crit": 80,        "direction": "upper"},
        "status_check_failed":          {"warn": 1,         "crit": 1,         "direction": "nonzero"},
        "status_check_failed_instance": {"warn": 1,         "crit": 1,         "direction": "nonzero"},
        "status_check_failed_system":   {"warn": 1,         "crit": 1,         "direction": "nonzero"},
        "disk_io_time_ms":              {"warn": 200,       "crit": 500,       "direction": "upper"},
        "cpu_credit_balance":           {"warn": 20,        "crit": 5,         "direction": "lower"},
        "network_in_bytes":             {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "network_out_bytes":            {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "disk_read_bytes":              {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "disk_write_bytes":             {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "network_packets_in":           {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "network_packets_out":          {"warn": None,      "crit": None,      "direction": "anomaly_only"},
    },

    "Virtual_Machines": {
        "cpu_pct":                      {"warn": 75,        "crit": 90,        "direction": "upper"},
        "memory_available_bytes":       {"warn": 1073741824,"crit": 536870912, "direction": "lower"},  # 1 GB / 512 MB
        "disk_free_pct":                {"warn": 25,        "crit": 10,        "direction": "lower"},
        "disk_free_pct_logical":        {"warn": 25,        "crit": 10,        "direction": "lower"},
        "disk_free_mb":                 {"warn": 1024,      "crit": 512,       "direction": "lower"},
        "os_disk_queue_depth":          {"warn": 5,         "crit": 10,        "direction": "upper"},
        "data_disk_queue_depth":        {"warn": 5,         "crit": 10,        "direction": "upper"},
        "cpu_credits_remaining":        {"warn": 20,        "crit": 5,         "direction": "lower"},
        # cross-cloud canonical metrics produced by metrics/derive.py
        "memory_used_pct":              {"warn": 75,        "crit": 90,        "direction": "upper"},
        "disk_used_pct":                {"warn": 75,        "crit": 90,        "direction": "upper"},
        "cpu_credit_balance":           {"warn": 20,        "crit": 5,         "direction": "lower"},
        "disk_write_bytes":             {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "os_disk_read_ops_per_sec":     {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "os_disk_write_ops_per_sec":    {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "network_in_bytes":             {"warn": None,      "crit": None,      "direction": "anomaly_only"},
        "network_out_bytes":            {"warn": None,      "crit": None,      "direction": "anomaly_only"},
    },

    "Compute_Engine": {
        "cpu_pct":          {"warn": 75,   "crit": 90,  "direction": "upper"},
        "memory_used_pct":  {"warn": 75,   "crit": 90,  "direction": "upper"},
        "disk_used_pct":    {"warn": 75,   "crit": 90,  "direction": "upper"},
        "cpu_scheduler_wait_sec": {"warn": 300, "crit": 1200, "direction": "upper"},
        "disk_read_bytes":  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_write_bytes": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_in_bytes": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_out_bytes":{"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "Compute": {  # OCI
        "cpu_pct":                  {"warn": 75,   "crit": 90,  "direction": "upper"},
        "memory_used_pct":          {"warn": 75,   "crit": 90,  "direction": "upper"},
        "memory_allocation_stalls": {"warn": 100,  "crit": 500, "direction": "upper"},
        "load_average":             {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_read_iops":           {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_write_iops":          {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_in_bytes":         {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_out_bytes":        {"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "Lambda": {
        "lambda_error_count":    {"warn": 1,    "crit": 10,  "direction": "upper"},
        "lambda_throttle_count": {"warn": 1,    "crit": 10,  "direction": "upper"},
        "lambda_duration_ms":    {"warn": None, "crit": None,"direction": "anomaly_only"},
        "lambda_concurrent_exec":{"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    # ── Storage ──────────────────────────────────────────────────────────────────
    "EBS": {
        "volume_queue_length":        {"warn": 5,    "crit": 10,  "direction": "upper"},
        "burst_balance_pct":          {"warn": 25,   "crit": 10,  "direction": "lower"},
        "volume_read_bytes":          {"warn": None, "crit": None,"direction": "anomaly_only"},
        "volume_write_bytes":         {"warn": None, "crit": None,"direction": "anomaly_only"},
        "volume_read_ops":            {"warn": None, "crit": None,"direction": "anomaly_only"},
        "volume_write_ops":           {"warn": None, "crit": None,"direction": "anomaly_only"},
        "volume_total_read_time_sec": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "volume_total_write_time_sec":{"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "EFS": {
        "percent_io_limit":               {"warn": 80,   "crit": 95,  "direction": "upper"},
        "burst_credit_balance":           {"warn": None, "crit": None,"direction": "anomaly_only"},
        "client_connections":             {"warn": None, "crit": None,"direction": "anomaly_only"},
        "total_io_bytes":                 {"warn": None, "crit": None,"direction": "anomaly_only"},
        "data_read_io_bytes":             {"warn": None, "crit": None,"direction": "anomaly_only"},
        "data_write_io_bytes":            {"warn": None, "crit": None,"direction": "anomaly_only"},
        "permitted_throughput_bytes_per_sec":{"warn": None,"crit": None,"direction": "anomaly_only"},
    },

    "S3": {
        "bucket_size_bytes": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "bytes_downloaded":  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "bytes_uploaded":    {"warn": None, "crit": None,"direction": "anomaly_only"},
        "api_request_count": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_in_bytes":  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_out_bytes": {"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "Accounts": {
        "storage_used_capacity_bytes": {"warn": None, "crit": None, "direction": "anomaly_only"},
        "transaction_count":           {"warn": None, "crit": None, "direction": "anomaly_only"},
        "server_latency_ms":           {"warn": 100,  "crit": 500,  "direction": "upper"},
        "e2e_latency_ms":              {"warn": 200,  "crit": 1000, "direction": "upper"},
        "availability_pct":            {"warn": 99,   "crit": 95,   "direction": "lower"},
        "egress_bytes":                {"warn": None, "crit": None, "direction": "anomaly_only"},
        "ingress_bytes":               {"warn": None, "crit": None, "direction": "anomaly_only"},
    },

    # Thresholds relative to provisioned IOPS/throughput are computed
    # dynamically in the statistical engine using resource config fields.
    "Storage_Disks": {
        "disk_read_bytes_per_sec":  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_write_bytes_per_sec": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_read_ops_per_sec":    {"warn": None, "crit": None,"direction": "anomaly_only"},
        "disk_write_ops_per_sec":   {"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "Bucket": {
        "storage_byte_seconds": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_in_bytes":     {"warn": None, "crit": None,"direction": "anomaly_only"},
        "network_out_bytes":    {"warn": None, "crit": None,"direction": "anomaly_only"},
        "api_request_count":    {"warn": None, "crit": None,"direction": "anomaly_only"},
        "object_count":         {"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "File_Storage": {
        "filesystem_used_bytes":          {"warn": None, "crit": None,"direction": "anomaly_only"},
        "read_throughput_bytes_per_sec":  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "write_throughput_bytes_per_sec": {"warn": None, "crit": None,"direction": "anomaly_only"},
        "metadata_iops":                  {"warn": None, "crit": None,"direction": "anomaly_only"},
        "read_requests_by_size":          {"warn": None, "crit": None,"direction": "anomaly_only"},
        "write_requests_by_size":         {"warn": None, "crit": None,"direction": "anomaly_only"},
    },

    "Recovery_Services": {
        "backup_health_event": {"warn": 1, "crit": 1, "direction": "nonzero"},
    },
}


def get_threshold(resource_type: str, canonical_metric: str) -> dict | None:
    return THRESHOLDS.get(resource_type, {}).get(canonical_metric)
