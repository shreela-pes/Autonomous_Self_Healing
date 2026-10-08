"""
ChangeStreamListener -- feeds log documents to the engine in DAY BATCHES, in event-time order.

Modes
  batch   read the whole collection sorted by from_date (oldest first) -> replays history exactly as
          it would have arrived in real time (needed so baselines, incident grouping and recurrence
          detection see the past before the future).
  stream  MongoDB change stream (needs a replica set / Atlas).  Documents are buffered and flushed
          when the day changes or after `settle_seconds` of silence, so all metrics of a resource for
          that day are ingested before diagnosis.
  poll    same as stream but by polling `created_at` - works on a standalone mongod.

The engine's `process_batch(list[ParsedDoc])` is called once per flush.
"""

import logging
import time
from typing import Callable, Optional

import pymongo

from ..config import MONGO_DB_NAME, MONGO_COLLECTION, BATCH_SIZE, SUPPORTED_CATEGORIES
from ..ingestion.normalizer import parse_document

logger = logging.getLogger(__name__)


def _day_key(parsed):
    d = parsed.from_date
    return d.strftime("%Y-%m-%d") if d else "unknown"


class ChangeStreamListener:
    def __init__(self, client: pymongo.MongoClient, process_batch_fn: Callable, settle_seconds: float = 5.0):
        """process_batch_fn: callable(list[ParsedDoc]) -> list[recommendation dict]"""
        self.client = client
        self.db = client[MONGO_DB_NAME]
        self.col = self.db[MONGO_COLLECTION]
        self.process_batch_fn = process_batch_fn
        self.settle_seconds = settle_seconds

    # -- helpers ----------------------------------------------------------------

    def _flush(self, batch: list, totals: dict) -> None:
        if not batch:
            return
        try:
            recs = self.process_batch_fn(batch) or []
            totals["processed"] += len(batch)
            totals["recommendations"] += len(recs)
            for r in recs:
                logger.info("recommendation %s  %s  %s/%s  %s  rev=%d  conf=%.2f", r["_id"][:8], r["priority"],
                            r["resource_name"], r["root_cause"]["id"], r["status"], r["revision"],
                            r["root_cause"]["confidence"])
        except Exception as exc:
            totals["errors"] += len(batch)
            logger.error("batch failed (%d docs, day %s): %s", len(batch), _day_key(batch[0]), exc, exc_info=True)

    def _parse(self, raw, totals):
        try:
            return parse_document(raw)
        except Exception as exc:
            logger.debug("parse_document failed for %s: %s", raw.get("_id", "?"), exc)
            totals["errors"] += 1
            return None

    # -- Batch mode -------------------------------------------------------------

    def run_batch(self, query_filter: Optional[dict] = None, limit: int = 0, skip: int = 0) -> dict:
        filt = {"category": {"$in": list(SUPPORTED_CATEGORIES)}}
        if query_filter:
            filt.update(query_filter)
        total = self.col.count_documents(filt)
        logger.info("Batch mode: %d documents (skip=%d, limit=%d), replayed oldest-first in day batches",
                    total, skip, limit)
        try:
            self.col.create_index("from_date")
        except Exception:
            pass
        cursor = self.col.find(filt).sort([("from_date", 1), ("project", 1), ("resourceId", 1), ("metric", 1)])
        try:
            cursor = cursor.allow_disk_use(True)
        except Exception:
            pass
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)

        totals = {"processed": 0, "recommendations": 0, "errors": 0}
        batch, cur_day = [], None
        for raw in cursor:
            parsed = self._parse(raw, totals)
            if parsed is None:
                continue
            day = _day_key(parsed)
            if cur_day is not None and (day != cur_day or len(batch) >= max(BATCH_SIZE, 1) * 4):
                self._flush(batch, totals)
                logger.info("day %s done  processed=%d/%d  recs=%d", cur_day, totals["processed"], total,
                            totals["recommendations"])
                batch = []
            cur_day = day
            batch.append(parsed)
        self._flush(batch, totals)
        logger.info("Batch complete: %s", totals)
        return totals

    # -- Stream mode ------------------------------------------------------------

    def run_stream(self, resume_token: Optional[dict] = None) -> None:
        """Change stream (replica set required).  Blocks until Ctrl-C."""
        pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "replace"]},
                                "fullDocument.category": {"$in": list(SUPPORTED_CATEGORIES)}}}]
        opts = {"full_document": "updateLookup"}
        if resume_token:
            opts["resume_after"] = resume_token
        logger.info("Stream mode: listening on '%s' (flush on day change or %.0fs idle)...", MONGO_COLLECTION,
                    self.settle_seconds)
        totals = {"processed": 0, "recommendations": 0, "errors": 0}
        batch, cur_day, last_doc_t = [], None, time.time()
        try:
            with self.col.watch(pipeline, **opts) as stream:
                while stream.alive:
                    event = stream.try_next()
                    if event is None:
                        if batch and time.time() - last_doc_t >= self.settle_seconds:
                            self._flush(batch, totals)
                            batch, cur_day = [], None
                        time.sleep(0.5)
                        continue
                    doc = event.get("fullDocument")
                    parsed = self._parse(doc, totals) if doc else None
                    if parsed is None:
                        continue
                    day = _day_key(parsed)
                    if cur_day is not None and day != cur_day:
                        self._flush(batch, totals)
                        batch = []
                    cur_day = day
                    batch.append(parsed)
                    last_doc_t = time.time()
        except pymongo.errors.PyMongoError as exc:
            logger.error("Change stream error: %s (a standalone mongod has no change streams - use --mode poll)", exc)
            raise

    # -- Poll mode ---------------------------------------------------------------

    def run_poll(self, interval: float = 5.0, max_idle_cycles: int = 0) -> None:
        """Poll for documents newer than the last `created_at` seen (standalone-mongod friendly)."""
        totals = {"processed": 0, "recommendations": 0, "errors": 0}
        watermark, idle = None, 0
        logger.info("Poll mode: checking every %.0fs for new documents...", interval)
        while True:
            filt = {"category": {"$in": list(SUPPORTED_CATEGORIES)}}
            if watermark is not None:
                filt["created_at"] = {"$gt": watermark}
            docs = list(self.col.find(filt).sort([("from_date", 1), ("project", 1), ("resourceId", 1), ("metric", 1)]))
            if docs:
                idle = 0
                watermark = max(d.get("created_at") for d in docs if d.get("created_at")) or watermark
                batch, cur_day = [], None
                for raw in docs:
                    parsed = self._parse(raw, totals)
                    if parsed is None:
                        continue
                    day = _day_key(parsed)
                    if cur_day is not None and day != cur_day:
                        self._flush(batch, totals)
                        batch = []
                    cur_day = day
                    batch.append(parsed)
                self._flush(batch, totals)
            else:
                idle += 1
                if max_idle_cycles and idle >= max_idle_cycles:
                    return
            time.sleep(interval)
