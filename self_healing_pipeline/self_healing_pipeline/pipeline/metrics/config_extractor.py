"""
Config Extractor — production-grade extraction of high-signal configuration fields.

Each extractor returns a raw config dict with correct nested paths per resource type.
String booleans (AWS returns "true"/"false" as strings) are normalised to Python bool.
"""
from typing import Any


def _safe(d: Any, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def _bool(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_config(resource_type: str, sd: dict) -> dict:
    if not isinstance(sd, dict):
        return {}
    extractor = _EXTRACTORS.get(resource_type)
    if extractor is None:
        return {}
    try:
        return {k: v for k, v in extractor(sd).items()}
    except Exception:
        return {}


# ── EC2 ───────────────────────────────────────────────────────────────────────

def _ec2(sd: dict) -> dict:
    instances_set = sd.get("instancesSet") or {}
    item = (
        instances_set.get("item")
        if isinstance(instances_set, dict)
        else (instances_set[0] if isinstance(instances_set, list) and instances_set else {})
    )
    if not isinstance(item, dict):
        item = {}

    meta = item.get("metadataOptions") or {}
    placement = item.get("placement") or {}
    cpu_opts = item.get("cpuOptions") or {}
    monitoring = item.get("monitoring") or {}
    maintenance = item.get("maintenanceOptions") or {}
    cap_res = item.get("capacityReservationSpecification") or {}
    hibernate = item.get("hibernationOptions") or {}
    enclave = item.get("enclaveOptions") or {}
    net_perf = item.get("networkPerformanceOptions") or {}

    bdm = item.get("blockDeviceMapping") or {}
    bdm_items = bdm.get("item") if isinstance(bdm, dict) else bdm
    if isinstance(bdm_items, dict):
        bdm_items = [bdm_items]
    volume_ids = [
        (b.get("ebs") or {}).get("volumeId")
        for b in (bdm_items or []) if isinstance(b, dict) and (b.get("ebs") or {}).get("volumeId")
    ]
    root_name = item.get("rootDeviceName")
    data_volume_ids = [
        (b.get("ebs") or {}).get("volumeId")
        for b in (bdm_items or [])
        if isinstance(b, dict) and b.get("deviceName") != root_name and (b.get("ebs") or {}).get("volumeId")
    ]

    return {
        # Sizing / identity
        "instance_id":            item.get("instanceId"),
        "volume_ids":             volume_ids,
        "data_volume_ids":        data_volume_ids,
        "instance_type":          item.get("instanceType"),
        "architecture":           item.get("architecture"),
        "virtualization_type":    item.get("virtualizationType"),
        "hypervisor":             item.get("hypervisor"),
        "platform_details":       item.get("platformDetails"),
        "image_id":               item.get("imageId"),
        "root_device_type":       item.get("rootDeviceType"),
        "usage_operation":        item.get("usageOperation"),
        # Status / lifecycle
        "instance_state":         _safe(item, "instanceState", "name"),
        "instance_state_code":    _safe(item, "instanceState", "code"),
        # CPU
        "cpu_core_count":         _int(cpu_opts.get("coreCount")),
        "threads_per_core":       _int(cpu_opts.get("threadsPerCore")),
        # Placement / reliability
        "availability_zone":      placement.get("availabilityZone"),
        "availability_zone_id":   placement.get("availabilityZoneId"),
        "placement_tenancy":      placement.get("tenancy"),
        "capacity_reservation":   cap_res.get("capacityReservationPreference"),
        # Performance
        "ebs_optimized":          _bool(item.get("ebsOptimized")),
        "ena_support":            _bool(item.get("enaSupport")),
        "bandwidth_weighting":    net_perf.get("bandwidthWeighting"),
        # Security
        "imds_http_tokens":       meta.get("httpTokens"),          # "required"=v2, "optional"=v1 risk
        "imds_endpoint":          meta.get("httpEndpoint"),
        "imds_hop_limit":         _int(meta.get("httpPutResponseHopLimit")),
        "imds_state":             meta.get("state"),
        "source_dest_check":      _bool(item.get("sourceDestCheck")),
        # Observability
        "monitoring_state":       monitoring.get("state"),          # "enabled" = detailed CloudWatch
        # Reliability
        "auto_recovery":          maintenance.get("autoRecovery"),
        "reboot_migration":       maintenance.get("rebootMigration"),
        "hibernation_configured": _bool(_safe(hibernate, "configured")),
        "enclave_enabled":        _bool(_safe(enclave, "enabled")),
    }


# ── Lambda ────────────────────────────────────────────────────────────────────

_DEPRECATED_RUNTIMES = {
    "python2.7", "python3.6", "python3.7", "python3.8", "python3.9",
    "nodejs10.x", "nodejs12.x", "nodejs14.x", "nodejs16.x",
    "java8", "java8.al2",
    "dotnet5.0", "dotnet6",
    "ruby2.5", "ruby2.7",
    "go1.x",
}

def _lambda(sd: dict) -> dict:
    vpc = sd.get("VpcConfig") or {}
    snap = sd.get("SnapStart") or {}
    trace = sd.get("TracingConfig") or {}
    eph = sd.get("EphemeralStorage") or {}
    arch = sd.get("Architectures") or []
    logging_cfg = sd.get("LoggingConfig") or {}
    runtime = sd.get("Runtime")
    return {
        "memory_mb":            _int(sd.get("MemorySize")),
        "timeout_sec":          _int(sd.get("Timeout")),
        "ephemeral_storage_mb": _int(eph.get("Size")),
        "code_size_bytes":      _int(sd.get("CodeSize")),
        "runtime":              runtime,
        "runtime_deprecated":   runtime in _DEPRECATED_RUNTIMES if runtime else None,
        "package_type":         sd.get("PackageType"),
        "state":                sd.get("State"),
        "state_reason_code":    sd.get("StateReasonCode"),
        "architecture":         arch[0] if arch else None,
        "tracing_mode":         trace.get("Mode"),          # "Active" = X-Ray on
        "snap_start":           snap.get("ApplyOn"),
        "snap_start_optimized": snap.get("OptimizationStatus"),
        "vpc_configured":       bool(vpc.get("VpcId")),     # True = network-isolated
        "layers_count":         len(sd.get("Layers") or []),
        "log_format":           logging_cfg.get("LogFormat"),
        "app_log_level":        logging_cfg.get("ApplicationLogLevel"),
        "system_log_level":     logging_cfg.get("SystemLogLevel"),
    }


# ── Azure Virtual_Machines (single VM) ───────────────────────────────────────

def _virtual_machines(sd: dict) -> dict:
    props = sd.get("properties") or {}
    hw    = props.get("hardwareProfile") or {}
    sp    = props.get("storageProfile") or {}
    os_d  = sp.get("osDisk") or {}
    img   = sp.get("imageReference") or {}
    md    = os_d.get("managedDisk") or {}
    osp   = props.get("osProfile") or {}
    net_iface = _safe(sd, "extended_summary_details", "network_interfaces_details") or {}
    net_props = net_iface.get("properties") or {}
    data_disks = [
        {"name": d.get("name"), "size_gb": _int(d.get("diskSizeGB"))}
        for d in (sp.get("dataDisks") or []) if isinstance(d, dict)
    ]

    return {
        "vm_name":            sd.get("name"),
        "os_disk_name":       os_d.get("name"),
        "os_disk_size_gb":    _int(os_d.get("diskSizeGB")),
        "data_disks":         data_disks,
        "vm_size":            hw.get("vmSize"),
        "provisioning_state": props.get("provisioningState"),
        "vm_id":              props.get("vmId"),
        "power_state":        sd.get("status"),              # "VM running" / "VM deallocated"
        # Storage
        "os_disk_type":       os_d.get("osType"),
        "os_disk_caching":    os_d.get("caching"),
        "os_disk_managed":    bool(md.get("id")),            # False = unmanaged (risk)
        "os_image_publisher": img.get("publisher"),
        "os_image_offer":     img.get("offer"),
        "os_image_sku":       img.get("sku"),
        # Security / networking
        "ip_forwarding":      _bool(net_props.get("enableIPForwarding")),
        "accelerated_networking": _bool(net_props.get("enableAcceleratedNetworking")),
        "nic_type":           net_props.get("nicType"),
        # Identity
        "computer_name":      osp.get("computerName"),
        "admin_username":     osp.get("adminUsername"),
    }


# ── Azure Virtual_Machines (VMSS) ─────────────────────────────────────────────

def _vmss(sd: dict) -> dict:
    sku   = sd.get("sku") or {}
    props = sd.get("properties") or {}
    up    = props.get("upgradePolicy") or {}
    vmp   = props.get("virtualMachineProfile") or {}
    sp    = vmp.get("storageProfile") or {}
    os_d  = sp.get("osDisk") or {}
    md    = os_d.get("managedDisk") or {}
    osp   = vmp.get("osProfile") or {}
    linux = osp.get("linuxConfiguration") or {}
    net_cfgs = _safe(vmp, "networkProfile", "networkInterfaceConfigurations") or []
    net_p = {}
    if net_cfgs and isinstance(net_cfgs, list):
        net_p = (net_cfgs[0].get("properties") or {}) if isinstance(net_cfgs[0], dict) else {}

    return {
        "sku_name":              sku.get("name"),
        "sku_tier":              sku.get("tier"),
        "capacity":              _int(sku.get("capacity")),
        "orchestration_mode":    props.get("orchestrationMode"),
        "upgrade_policy":        up.get("mode"),             # "Manual" = drift risk
        "fault_domain_count":    _int(props.get("platformFaultDomainCount")),
        "single_placement":      _bool(props.get("singlePlacementGroup")),
        "provisioning_state":    props.get("provisioningState"),
        "os_disk_type":          os_d.get("osType"),
        "os_disk_size_gb":       _int(os_d.get("diskSizeGB")),
        "storage_account_type":  md.get("storageAccountType"),
        "disk_controller_type":  sp.get("diskControllerType"),
        "disable_password_auth": _bool(linux.get("disablePasswordAuthentication")),
        "provision_vm_agent":    _bool(linux.get("provisionVMAgent")),
        "ip_forwarding":         _bool(net_p.get("enableIPForwarding")),
        "accelerated_networking":_bool(net_p.get("enableAcceleratedNetworking")),
        "tcp_state_tracking":    not _bool(net_p.get("disableTcpStateTracking", False)),
    }


# ── GCP Compute_Engine ────────────────────────────────────────────────────────

def _compute_engine(sd: dict) -> dict:
    disks = sd.get("disks") or []
    boot_disk = next((d for d in disks if isinstance(d, dict) and d.get("boot")), {})
    sched = sd.get("scheduling") or {}
    shielded = sd.get("shieldedInstanceConfig") or {}
    confidential = sd.get("confidentialInstanceConfig") or {}
    net_ifaces = sd.get("networkInterfaces") or []
    net_p = (net_ifaces[0].get("accessConfigs", [{}]) or [{}])[0] if net_ifaces else {}
    data_disks = [
        {"name": (d.get("source") or "").split("/")[-1] or d.get("deviceName"), "size_gb": _int(d.get("diskSizeGb"))}
        for d in disks if isinstance(d, dict) and not d.get("boot")
    ]

    return {
        "instance_name":          sd.get("name"),
        "data_disks":             data_disks,
        "machine_type":           sd.get("machineType"),
        "cpu_platform":           sd.get("cpuPlatform"),
        "status":                 sd.get("status"),
        "zone":                   sd.get("zone"),
        "can_ip_forward":         _bool(sd.get("canIpForward")),
        "deletion_protection":    _bool(sd.get("deletionProtection")),
        "preemptible":            _bool(sched.get("preemptible")),
        "provisioning_model":     sched.get("provisioningModel"),
        "automatic_restart":      _bool(sched.get("automaticRestart")),
        "on_host_maintenance":    sched.get("onHostMaintenance"),
        # Boot disk
        "boot_disk_size_gb":      _int(boot_disk.get("diskSizeGb")),
        "boot_disk_type":         boot_disk.get("type"),
        "boot_disk_auto_delete":  _bool(boot_disk.get("autoDelete")),
        # Security
        "secure_boot":            _bool(shielded.get("enableSecureBoot")),
        "vtpm":                   _bool(shielded.get("enableVtpm")),
        "integrity_monitoring":   _bool(shielded.get("enableIntegrityMonitoring")),
        "confidential_compute":   _bool(confidential.get("enableConfidentialCompute")),
        # Network
        "network_tier":           net_p.get("networkTier"),
        "reservation_affinity":   _safe(sd, "reservationAffinity", "consumeReservationType"),
    }


# ── OCI Compute ───────────────────────────────────────────────────────────────

def _compute_oci(sd: dict) -> dict:
    sc = sd.get("shapeConfig") or {}
    launch = sd.get("launchOptions") or {}
    src = sd.get("sourceDetails") or {}
    agent = sd.get("agentConfig") or {}
    inst_opts = sd.get("instanceOptions") or {}
    platform = sd.get("platformConfig") or {}

    return {
        "shape":                 sd.get("shape"),
        "ocpus":                 _float(sc.get("ocpus")),
        "vcpus":                 _int(sc.get("vcpus")),
        "memory_gb":             _float(sc.get("memoryInGBs")),
        "gpu_count":             _int(sc.get("gpus")),
        "gpu_description":       sc.get("gpuDescription"),
        "local_disks":           _int(sc.get("localDisks")),
        "local_disks_size_gb":   _float(sc.get("localDisksTotalSizeInGBs")),
        "network_bandwidth_gbps":_float(sc.get("networkingBandwidthInGbps")),
        "baseline_ocpu_util":    sc.get("baselineOcpuUtilization"),
        "processor_description": sc.get("processorDescription"),
        "max_vnic_attachments":  _int(sc.get("maxVnicAttachments")),
        # Status
        "lifecycle_state":       sd.get("lifecycleState"),
        "availability_domain":   sd.get("availabilityDomain"),
        "fault_domain":          sd.get("faultDomain"),
        "is_cross_numa":         _bool(sd.get("isCrossNumaNode")),
        # Boot
        "boot_volume_size_gb":   _int(src.get("bootVolumeSizeInGBs")),
        "boot_volume_vpus_per_gb":_int(src.get("bootVolumeVpusPerGB")),
        "boot_volume_type":      launch.get("bootVolumeType"),
        "firmware":              launch.get("firmware"),
        # Security
        "encryption_in_transit": _bool(launch.get("isEncryptionInTransitEnabled")),
        "pv_encryption_transit": _bool(launch.get("isPvEncryptionInTransitEnabled")),
        "legacy_imds_disabled":  _bool(inst_opts.get("areLegacyImdsEndpointsDisabled")),
        "kms_key_id":            sd.get("kmsKeyId"),
        # Observability
        "monitoring_disabled":   _bool(agent.get("isMonitoringDisabled")),
        "management_disabled":   _bool(agent.get("isManagementDisabled")),
        "all_plugins_disabled":  _bool(agent.get("areAllPluginsDisabled")),
    }


# ── EBS ───────────────────────────────────────────────────────────────────────

def _ebs(sd: dict) -> dict:
    att_set = sd.get("attachmentSet") or {}
    att = att_set.get("item") if isinstance(att_set, dict) else None
    if isinstance(att, list):
        att = att[0] if att else None

    return {
        "volume_id":          sd.get("volumeId"),
        "size_gb":            _int(sd.get("size")),
        "volume_type":        sd.get("volumeType"),
        "iops":               _int(sd.get("iops")),
        "throughput":         _int(sd.get("throughput")),
        "encrypted":          _bool(sd.get("encrypted")),
        "multi_attach":       _bool(sd.get("multiAttachEnabled")),
        "status":             sd.get("status"),              # "in-use" | "available" (orphaned)
        "availability_zone":  sd.get("availabilityZone"),
        "availability_zone_id": sd.get("availabilityZoneId"),
        # Attachment info
        "attached_instance":  att.get("instanceId") if isinstance(att, dict) else None,
        "attached_device":    att.get("device") if isinstance(att, dict) else None,
        "delete_on_terminate":_bool(att.get("deleteOnTermination")) if isinstance(att, dict) else None,
    }


# ── Azure Storage Accounts ────────────────────────────────────────────────────

def _accounts(sd: dict) -> dict:
    props = sd.get("properties") or {}
    sku   = sd.get("sku") or {}
    enc   = props.get("encryption") or {}
    svcs  = enc.get("services") or {}
    blob  = svcs.get("blob") or {}
    file_ = svcs.get("file") or {}
    net   = props.get("networkAcls") or {}

    return {
        "kind":                   sd.get("kind"),
        "sku_name":               sku.get("name"),
        "sku_tier":               sku.get("tier"),
        "location":               sd.get("location"),
        "provisioning_state":     props.get("provisioningState"),
        "status_primary":         props.get("statusOfPrimary"),
        "primary_location":       props.get("primaryLocation"),
        "access_tier":            props.get("accessTier"),
        # Security — these are the top signals
        "minimum_tls_version":    props.get("minimumTlsVersion"),   # should be TLS1_2
        "allow_blob_public_access":_bool(props.get("allowBlobPublicAccess")), # must be false
        "https_only":             _bool(props.get("supportsHttpsTrafficOnly")),
        "network_default_action": net.get("defaultAction"),          # "Allow" = open risk
        "network_bypass":         net.get("bypass"),
        # Encryption
        "encryption_key_source":  enc.get("keySource"),
        "blob_encryption":        _bool(blob.get("enabled")),
        "blob_key_type":          blob.get("keyType"),
        "file_encryption":        _bool(file_.get("enabled")),
        "file_key_type":          file_.get("keyType"),
        "shared_key_access":      _bool(props.get("allowSharedKeyAccess")),
    }


# ── S3 ────────────────────────────────────────────────────────────────────────

def _s3(sd: dict) -> dict:
    return {
        "location": sd.get("location"),
        "name":     sd.get("Name"),
        "arn":      sd.get("arn"),
    }


# ── GCP Bucket ───────────────────────────────────────────────────────────────

def _bucket(sd: dict) -> dict:
    iam  = sd.get("iamConfiguration") or {}
    ubla = iam.get("uniformBucketLevelAccess") or {}
    bpo  = iam.get("bucketPolicyOnly") or {}
    soft = sd.get("softDeletePolicy") or {}

    return {
        "storage_class":               sd.get("storageClass"),
        "location":                    sd.get("location"),
        "location_type":               sd.get("locationType"),
        "public_access_prevention":    iam.get("publicAccessPrevention"),  # "enforced" = safe
        "uniform_bucket_level_access": _bool(ubla.get("enabled")),
        "bucket_policy_only":          _bool(bpo.get("enabled")),
        "soft_delete_retention_sec":   _int(soft.get("retentionDurationSeconds")),
    }


# ── Azure Storage_Disks ───────────────────────────────────────────────────────

def _storage_disks(sd: dict) -> dict:
    props = sd.get("properties") or {}
    sku   = sd.get("sku") or {}
    enc   = props.get("encryption") or {}
    cdata = props.get("creationData") or {}

    return {
        "sku_name":             sku.get("name"),
        "sku_tier":             sku.get("tier"),
        "disk_size_gb":         _int(props.get("diskSizeGB")),
        "disk_size_bytes":      props.get("diskSizeBytes"),
        "disk_iops":            _int(props.get("diskIOPSReadWrite")),
        "disk_mbps":            _int(props.get("diskMBpsReadWrite")),
        "disk_state":           props.get("diskState"),           # "Unattached" = orphaned cost
        "provisioning_state":   props.get("provisioningState"),
        "network_access_policy":props.get("networkAccessPolicy"),
        "public_network_access":props.get("publicNetworkAccess"),
        "encryption_type":      enc.get("type"),
        "create_option":        cdata.get("createOption"),
        "location":             sd.get("location"),
    }


# ── EFS ───────────────────────────────────────────────────────────────────────

def _efs(sd: dict) -> dict:
    sib = sd.get("SizeInBytes") or {}
    fsp = sd.get("FileSystemProtection") or {}

    return {
        "size_bytes":               _int(sib.get("Value")),
        "size_ia_bytes":            _int(sib.get("ValueInIA")),
        "size_archive_bytes":       _int(sib.get("ValueInArchive")),
        "size_standard_bytes":      _int(sib.get("ValueInStandard")),
        "performance_mode":         sd.get("PerformanceMode"),    # "generalPurpose" | "maxIO"
        "throughput_mode":          sd.get("ThroughputMode"),     # "bursting" | "provisioned" | "elastic"
        "provisioned_throughput_mibps": _float(sd.get("ProvisionedThroughputInMibps")),
        "encrypted":                _bool(sd.get("Encrypted")),
        "kms_key_id":               sd.get("KmsKeyId"),
        "lifecycle_state":          sd.get("LifeCycleState"),
        "number_of_mount_targets":  _int(sd.get("NumberOfMountTargets")),
        "replication_overwrite_protection": fsp.get("ReplicationOverwriteProtection"),
    }


# ── OCI File_Storage ──────────────────────────────────────────────────────────

def _file_storage(sd: dict) -> dict:
    src = sd.get("sourceDetails") or {}
    return {
        "metered_bytes":        _int(sd.get("meteredBytes")),
        "lifecycle_state":      sd.get("lifecycleState"),
        "lifecycle_details":    sd.get("lifecycleDetails"),
        "quota_enforcement":    sd.get("quotaEnforcementState"),
        "is_clone_parent":      _bool(sd.get("isCloneParent")),
        "is_hydrated":          _bool(sd.get("isHydrated")),
        "clone_attach_status":  sd.get("cloneAttachStatus"),
        "kms_key_id":           sd.get("kmsKeyId"),
        "replication_src_count":_int(sd.get("replicationSourceCount")),
        "source_fs_id":         src.get("parentFileSystemId"),
        "source_snapshot_id":   src.get("sourceSnapshotId"),
    }


# ── Azure Recovery_Services ───────────────────────────────────────────────────

def _recovery_services(sd: dict) -> dict:
    props = sd.get("properties") or {}
    sku   = sd.get("sku") or {}
    return {
        "sku_name":                      sku.get("name"),
        "sku_tier":                      sku.get("tier"),
        "location":                      sd.get("location"),
        "provisioning_state":            props.get("provisioningState"),
        "private_endpoint_backup":       props.get("privateEndpointStateForBackup"),
        "private_endpoint_site_recovery":props.get("privateEndpointStateForSiteRecovery"),
    }


_EXTRACTORS = {
    "EC2":               _ec2,
    "Lambda":            _lambda,
    "Virtual_Machines":  _virtual_machines,
    "Compute_Engine":    _compute_engine,
    "Compute":           _compute_oci,
    "EBS":               _ebs,
    "Accounts":          _accounts,
    "S3":                _s3,
    "Bucket":            _bucket,
    "Storage_Disks":     _storage_disks,
    "EFS":               _efs,
    "File_Storage":      _file_storage,
    "Recovery_Services": _recovery_services,
}
