"""
Parses raw MongoDB documents into structured ParsedDoc objects.

Each MongoDB document covers one resource × one metric × one day (24 hourly points).
This module:
  1. Unpacks the 24-point time series from metric_value[]
  2. Maps the raw metric name to a canonical name via the registry
  3. Applies any unit transforms (e.g. GCP 0–1 ratio → percentage)
  4. Extracts infrastructure config from summary_details
  5. Parses the source-alert records (`alerts[]`) attached to the log
  6. Returns a ParsedDoc dataclass ready for the state manager

Cross-cloud canonicalisation (metrics/derive.py) happens here, so everything downstream sees
the same metric vocabulary and units for AWS, Azure and GCP - including inside alert records
(threshold / observed value are converted with the same transform as the metric values).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..metrics.registry import get_canonical
from ..metrics.config_extractor import extract_config
from ..metrics.derive import derive_metric
from ..config import SUPPORTED_CATEGORIES


@dataclass
class MetricPoint:
    timestamp: datetime
    value: Optional[float]        # transformed canonical value
    raw_value: Optional[float]    # pre-transform
    stat_field: Optional[str]     # which stat was used (average/maximum/total/…)
    daily_max: Optional[float]
    daily_min: Optional[float]
    daily_avg: Optional[float]


@dataclass
class SourceAlert:
    """One alert record as fired by the cloud's own alerting (CloudWatch / Azure Monitor / GCP)."""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: str                  # CRIT | WARN
    state: str                     # Fired | Resolved   (as of the end of the log's day)
    metric: str                    # canonical metric name
    raw_metric: str
    op: str                        # ">" | "<" | "surge" | "drop"   (canonical direction)
    threshold: Optional[float]
    observed: Optional[float]
    expected: Optional[float]      # dynamic-threshold baseline, if any
    fired_at: Optional[datetime]
    resolved_at: Optional[datetime]
    condition_type: str = "static"
    evaluation_periods: int = 1
    is_continuation: bool = False  # fired on an earlier day and still relevant today
    description: str = ""
    source: str = ""

    @property
    def active(self) -> bool:
        return self.state == "Fired"

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id, "rule_id": self.rule_id, "rule_name": self.rule_name,
            "severity": self.severity, "state": self.state, "metric": self.metric,
            "op": self.op, "threshold": self.threshold, "observed": self.observed,
            "expected": self.expected, "fired_at": self.fired_at, "resolved_at": self.resolved_at,
            "condition_type": self.condition_type, "evaluation_periods": self.evaluation_periods,
            "is_continuation": self.is_continuation, "description": self.description,
            "source": self.source,
        }


@dataclass
class ParsedDoc:
    resource_id: str
    project_id: Optional[str]
    resource_type: str
    category: str
    operation_id: Optional[str]
    service_name: Optional[str]
    account_id: Optional[str]
    account_name: Optional[str]
    resource_name: Optional[str]
    location: Optional[str]
    raw_metric: str
    canonical_metric: Optional[str]
    points: list = field(default_factory=list)   # List[MetricPoint]
    config: dict = field(default_factory=dict)
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    summary_details: Optional[dict] = None
    tags: Optional[list] = None
    alerts: list = field(default_factory=list)   # List[SourceAlert]
    source_metric_id: Optional[str] = None       # canonical name BEFORE derive (e.g. memory_available_bytes)


# ── Helpers ────────────────────────────────────────────────────────────────────

_STAT_PRIORITY = [
    "average", "delta", "maximum", "sum", "total",
    "minimum", "count", "samplecount", "value",
]


def _get_ci(d: dict, *keys):
    """Case-insensitive dict lookup — returns first match."""
    if not isinstance(d, dict):
        return None
    lowered = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        v = lowered.get(key.lower())
        if v is not None:
            return v
    return None


def _parse_datetime(raw) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, dict) and "$date" in raw:
        raw = raw["$date"]
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        import pandas as pd
        parsed = pd.to_datetime(raw, utc=True, errors="coerce")
        if not hasattr(parsed, 'to_pydatetime'):
            return datetime.now(timezone.utc)
        result = parsed.to_pydatetime()
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _extract_stat(item: dict):
    """Extract (primary_value, stat_field) from a single metric_value item."""
    if not isinstance(item, dict):
        return None, None
    lowered = {str(k).lower(): (k, v) for k, v in item.items()}
    for stat in _STAT_PRIORITY:
        entry = lowered.get(stat)
        if entry is not None and entry[1] is not None:
            try:
                return float(entry[1]), stat
            except (TypeError, ValueError):
                continue
    return None, None


def _extract_bundle(item: dict):
    """Extract avg, max, min from a metric_value item."""
    if not isinstance(item, dict):
        return None, None, None
    lowered = {str(k).lower(): v for k, v in item.items()}
    def _f(k):
        v = lowered.get(k)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    return _f("average"), _f("maximum"), _f("minimum")


def _resource_id(doc: dict) -> str:
    rid = (
        doc.get("element_id")
        or doc.get("resourceId")
        or doc.get("resource_id")
        or str(doc.get("inventory_id") or doc.get("_id") or "unknown")
    )
    # inventory_id may be a dict {"$oid": "..."}
    if isinstance(rid, dict):
        rid = rid.get("$oid") or str(rid)
    return str(rid)


def _resource_name(doc: dict) -> str:
    return (
        doc.get("resource_name")
        or doc.get("display_name")
        or doc.get("name")
        or _resource_id(doc)
    )


def _unpack_points(doc: dict, transform, swap_minmax: bool = False) -> list[MetricPoint]:
    """Unpack metric_value[] into MetricPoint list, applying transform to value AND avg/max/min."""
    def _tx(v):
        if v is None:
            return None
        try:
            return transform(v)
        except Exception:
            return v

    def _bundle(avg, mx, mn):
        avg, mx, mn = _tx(avg), _tx(mx), _tx(mn)
        if swap_minmax:
            mx, mn = mn, mx
        return avg, mx, mn

    mv = doc.get("metric_value")
    if not isinstance(mv, list):
        # Single-value doc
        raw_val, stat = _extract_stat(doc)
        avg, mx, mn = _bundle(*_extract_bundle(doc.get("metric_value") or doc))
        ts = _parse_datetime(doc.get("from_date") or doc.get("created_at"))
        return [MetricPoint(
            timestamp=ts, value=_tx(raw_val), raw_value=raw_val,
            stat_field=stat, daily_max=mx, daily_min=mn, daily_avg=avg,
        )]

    points = []
    for item in mv:
        if not isinstance(item, dict):
            continue
        ts_raw = (
            _get_ci(item, "timestamp", "timeStamp")
            or doc.get("from_date")
            or doc.get("created_at")
        )
        ts = _parse_datetime(ts_raw)
        raw_val, stat = _extract_stat(item)
        avg, mx, mn = _bundle(*_extract_bundle(item))
        points.append(MetricPoint(
            timestamp=ts, value=_tx(raw_val), raw_value=raw_val,
            stat_field=stat, daily_max=mx, daily_min=mn, daily_avg=avg,
        ))
    return points


def _canonical_op(operator: str, condition_type: str) -> str:
    o = (operator or "").lower()
    greater = ("greater" in o) or o.endswith("_gt") or o in (">", "gt")
    if condition_type == "dynamic":
        return "surge" if greater else "drop"
    return ">" if greater else "<"


def _parse_alerts(doc: dict, canonical_metric: Optional[str], value_fn, flip: bool,
                  day_start: datetime) -> list:
    """Parse `alerts[]`.  Thresholds/observed values are converted to canonical units."""
    raw_alerts = doc.get("alerts")
    if not isinstance(raw_alerts, list):
        return []
    out = []
    for a in raw_alerts:
        if not isinstance(a, dict):
            continue

        def _cv(v):
            if v is None:
                return None
            try:
                return float(value_fn(v))
            except Exception:
                return None

        ctype = a.get("condition_type") or "static"
        op = _canonical_op(a.get("operator", ""), ctype)
        if flip and ctype == "static":
            op = ">" if op == "<" else "<"
        sev_raw = str(a.get("severity") or "").lower()
        severity = "CRIT" if sev_raw in ("critical", "crit", "error", "sev0", "sev1") else "WARN"
        fired = _parse_datetime(a["fired_at"]) if a.get("fired_at") else None
        resolved = _parse_datetime(a["resolved_at"]) if a.get("resolved_at") else None
        thr = _cv(a.get("threshold"))
        exp = _cv(a.get("expected_value"))
        out.append(SourceAlert(
            alert_id=str(a.get("alert_id") or f"{doc.get('resourceId')}|{a.get('alert_name')}|{a.get('fired_at')}"),
            rule_id=str(a.get("alert_rule_id") or a.get("alert_name") or ""),
            rule_name=str(a.get("alert_name") or ""),
            severity=severity,
            state=str(a.get("state") or "Fired").capitalize(),
            metric=canonical_metric or str(a.get("metric") or ""),
            raw_metric=str(a.get("metric") or ""),
            op=op, threshold=thr, observed=_cv(a.get("observed_value")), expected=exp,
            fired_at=fired, resolved_at=resolved, condition_type=ctype,
            evaluation_periods=int(a.get("evaluation_periods") or 1),
            is_continuation=bool(a.get("is_continuation")) or bool(fired and fired < day_start),
            description=str(a.get("description") or ""), source=str(a.get("alert_source") or ""),
        ))
    return out


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_document(doc: dict) -> Optional[ParsedDoc]:
    """
    Parse a single MongoDB log document into a ParsedDoc.
    Returns None if the document category/resource_type is unsupported
    or if the metric field is missing.
    """
    category = doc.get("category")
    if category not in SUPPORTED_CATEGORIES:
        return None

    resource_type = doc.get("resource_type")
    raw_metric    = doc.get("metric")
    if not resource_type or not raw_metric:
        return None

    canonical_metric, transform = get_canonical(resource_type, raw_metric)
    if transform is None:
        transform = float  # identity fallback

    # Config first: derive_metric() needs e.g. the VM size to turn free-memory bytes into % used.
    sd = dict(doc.get("summary_details") or {})
    if doc.get("extended_summary_details"):
        sd["extended_summary_details"] = doc["extended_summary_details"]
    config = extract_config(resource_type, sd)

    source_metric_id = canonical_metric
    value_fn, flip = transform, False
    derived = derive_metric(resource_type, canonical_metric, config)
    if derived is not None:
        base_tx = transform
        canonical_metric = derived.canonical
        value_fn = lambda x, b=base_tx, d=derived.fn: d(b(x))
        flip = derived.flip

    points = _unpack_points(doc, value_fn, swap_minmax=flip)
    from_date = _parse_datetime(doc.get("from_date"))

    return ParsedDoc(
        resource_id      = _resource_id(doc),
        project_id       = doc.get("project"),
        resource_type    = resource_type,
        category         = category,
        operation_id     = doc.get("operation_id"),
        service_name     = doc.get("service_name"),
        account_id       = doc.get("account_id"),
        account_name     = doc.get("account_name"),
        resource_name    = _resource_name(doc),
        location         = doc.get("location"),
        raw_metric       = raw_metric,
        canonical_metric = canonical_metric,
        points           = points,
        config           = config,
        from_date        = from_date,
        to_date          = _parse_datetime(doc.get("to_date")),
        summary_details  = doc.get("summary_details"),
        tags             = doc.get("tags"),
        alerts           = _parse_alerts(doc, canonical_metric, value_fn, flip, from_date),
        source_metric_id = source_metric_id,
    )
