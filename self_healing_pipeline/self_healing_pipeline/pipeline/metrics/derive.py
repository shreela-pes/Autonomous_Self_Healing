"""
Cross-cloud canonicalisation of metrics that providers expose in different shapes.

  Azure "Available Memory Bytes"          -> memory_used_pct        (needs VM memory size)
  Azure "disk/free_percent" / "% Free"    -> disk_used_pct
  Azure "CPU Credits Remaining"           -> cpu_credit_balance     (same meaning as AWS CPUCreditBalance)

After this step every provider speaks the same language (cpu_pct, memory_used_pct,
disk_used_pct, cpu_credit_balance, network_in_bytes, ...), so the correlation, RCA and ML
layers never need provider-specific branches.

`flip` is True when the transform reverses direction (free -> used), which turns a
"less than" alert rule into a "greater than" one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

GIB = 1024 ** 3


@dataclass
class Derived:
    canonical: str
    fn: Callable[[float], float]
    flip: bool = False


def _azure_vm_memory_gb(config: dict) -> Optional[float]:
    from .feature_normalizer import _AZURE_VM_SPECS
    spec = _AZURE_VM_SPECS.get(config.get("vm_size") or "")
    return spec[1] if spec else None


def derive_metric(resource_type: str, canonical: Optional[str], config: dict) -> Optional[Derived]:
    if canonical is None:
        return None
    if resource_type == "Virtual_Machines":
        if canonical == "memory_available_bytes":
            gb = _azure_vm_memory_gb(config)
            if gb:
                total = gb * GIB
                return Derived("memory_used_pct", lambda x, t=total: 100.0 - 100.0 * float(x) / t, flip=True)
            return None
        if canonical in ("disk_free_pct", "disk_free_pct_logical"):
            return Derived("disk_used_pct", lambda x: 100.0 - float(x), flip=True)
        if canonical == "cpu_credits_remaining":
            return Derived("cpu_credit_balance", float)
    return None
