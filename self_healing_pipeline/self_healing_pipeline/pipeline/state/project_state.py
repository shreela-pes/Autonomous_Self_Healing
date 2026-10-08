"""
ProjectStateManager — maintains per-project aggregated snapshots.

A project snapshot is a lightweight view of ALL resources in a project:
which are alerting, at what severity, and which correlated event sets
have been detected by the correlation engine.

Schema (project_snapshots collection):
  _id                  : project_id
  resources            : {resource_id → {type, category, status, alerts, last_updated}}
  active_alert_count   : total number of WARN/CRIT/ANOMALY alerts across all resources
  degraded_categories  : {Compute: [rid, …], Storage: [rid, …]}
  correlated_sets      : [{set_id, resources, rule_name, root_cause, confidence, detected_at}]
  last_updated         : datetime
"""

from datetime import datetime, timezone
import uuid
import pymongo

from ..config import PROJECT_SNAPSHOTS_COLLECTION


class ProjectStateManager:
    def __init__(self, db: pymongo.database.Database):
        self.col = db[PROJECT_SNAPSHOTS_COLLECTION]
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.col.create_index("last_updated")

    def update_resource_status(
        self,
        project_id: str,
        resource_id: str,
        resource_type: str,
        category: str,
        status: str,
        active_alerts: list[dict],
    ) -> None:
        """Called by the recommendation engine after statistical analysis."""
        now = datetime.now(timezone.utc)
        self.col.update_one(
            {"_id": project_id},
            {
                "$set": {
                    f"resources.{_safe_key(resource_id)}.resource_type": resource_type,
                    f"resources.{_safe_key(resource_id)}.category":      category,
                    f"resources.{_safe_key(resource_id)}.status":        status,
                    f"resources.{_safe_key(resource_id)}.active_alerts": active_alerts,
                    f"resources.{_safe_key(resource_id)}.last_updated":  now,
                    "last_updated": now,
                }
            },
            upsert=True,
        )
        self._recompute_summary(project_id)

    def add_correlated_set(self, project_id: str, correlated_set: dict) -> None:
        """Append a detected correlated event set to the project snapshot."""
        correlated_set["set_id"]      = str(uuid.uuid4())
        correlated_set["detected_at"] = datetime.now(timezone.utc)
        self.col.update_one(
            {"_id": project_id},
            {
                "$push": {
                    "correlated_sets": {
                        "$each":  [correlated_set],
                        "$slice": -20,          # keep last 20 sets per project
                    }
                },
                "$set": {"last_updated": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    def get(self, project_id: str) -> dict | None:
        return self.col.find_one({"_id": project_id})

    def get_all_resource_statuses(self, project_id: str) -> dict:
        """Return {resource_id → resource_status_dict}."""
        doc = self.col.find_one({"_id": project_id}, {"resources": 1})
        if not doc:
            return {}
        return {
            _unsafe_key(k): v
            for k, v in (doc.get("resources") or {}).items()
        }

    def get_degraded_resources(self, project_id: str, min_status: str = "WARN") -> list[dict]:
        """Return resources whose status is at or above min_status."""
        rank = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}
        min_rank = rank.get(min_status, 1)
        resources = self.get_all_resource_statuses(project_id)
        return [
            {"resource_id": rid, **info}
            for rid, info in resources.items()
            if rank.get(info.get("status", "OK"), 0) >= min_rank
        ]

    def _recompute_summary(self, project_id: str) -> None:
        doc = self.col.find_one({"_id": project_id}, {"resources": 1})
        if not doc:
            return
        resources = doc.get("resources") or {}
        degraded_compute = []
        degraded_storage = []
        alert_count = 0
        rank = {"OK": 0, "NO_DATA": 0, "ANOMALY": 1, "WARN": 2, "CRIT": 3}
        for rid_safe, info in resources.items():
            rid = _unsafe_key(rid_safe)
            status = info.get("status", "OK")
            n_alerts = len(info.get("active_alerts", []))
            alert_count += n_alerts
            if rank.get(status, 0) >= 1:
                cat = info.get("category", "")
                if cat == "Compute":
                    degraded_compute.append(rid)
                elif cat == "Storage":
                    degraded_storage.append(rid)
        self.col.update_one(
            {"_id": project_id},
            {"$set": {
                "active_alert_count":  alert_count,
                "degraded_categories": {
                    "Compute": degraded_compute,
                    "Storage": degraded_storage,
                },
            }},
        )


def _safe_key(s: str) -> str:
    """MongoDB field keys cannot contain dots. Replace with Unicode middle dot."""
    return s.replace(".", "·").replace("$", "＄")


def _unsafe_key(s: str) -> str:
    return s.replace("·", ".").replace("＄", "$")
