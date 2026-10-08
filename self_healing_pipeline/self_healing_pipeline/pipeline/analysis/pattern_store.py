"""
PatternStore -- remembers what each alert signature turned out to be.

A signature is the sorted set of (metric, direction, severity) alerts of an incident plus the
resource type.  For every signature we keep how many incidents there were, how many resolved,
the mean duration, and how often each root cause was diagnosed.  The RCA engine uses this as a
small, explainable confidence bonus ("the same alert pattern was diagnosed the same way twice
before") - never as a reason to skip the evidence checks.

Collection: alert_patterns
  _id, resource_type, total_incidents, resolved_incidents, total_duration_hours,
  root_cause_counts{rc: n}, first_seen, last_seen
"""
from datetime import datetime, timezone
from typing import Optional

import pymongo

from ..config import PATTERNS_COLLECTION


class PatternStore:
    def __init__(self, db: pymongo.database.Database):
        self.col = db[PATTERNS_COLLECTION]

    def record_open(self, signature: str, resource_type: str, when: Optional[datetime] = None) -> None:
        when = when or datetime.now(timezone.utc)
        self.col.update_one(
            {"_id": signature},
            {"$inc": {"total_incidents": 1},
             "$setOnInsert": {"resource_type": resource_type, "first_seen": when},
             "$set": {"last_seen": when}},
            upsert=True,
        )

    def record_diagnosis(self, signature: str, root_cause_id: str) -> None:
        self.col.update_one({"_id": signature}, {"$inc": {f"root_cause_counts.{root_cause_id}": 1}}, upsert=True)

    def record_close(self, signature: str, duration_hours: float) -> None:
        self.col.update_one(
            {"_id": signature},
            {"$inc": {"resolved_incidents": 1, "total_duration_hours": float(duration_hours or 0.0)}},
            upsert=True,
        )

    def get(self, signature: str) -> Optional[dict]:
        doc = self.col.find_one({"_id": signature})
        if doc:
            n = doc.get("resolved_incidents") or 0
            doc["mean_duration_hours"] = (doc.get("total_duration_hours", 0.0) / n) if n else None
        return doc
