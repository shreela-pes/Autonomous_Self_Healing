"""Timezone helpers.  Everything inside the pipeline is timezone-aware UTC."""
from datetime import datetime, timezone
from typing import Optional


def as_utc(dt) -> Optional[datetime]:
    """Naive datetimes coming back from MongoDB are UTC by convention; make them aware."""
    if dt is None:
        return None
    if isinstance(dt, dict) and "$date" in dt:
        dt = dt["$date"]
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hours_between(a, b) -> float:
    a, b = as_utc(a), as_utc(b)
    return (b - a).total_seconds() / 3600.0
