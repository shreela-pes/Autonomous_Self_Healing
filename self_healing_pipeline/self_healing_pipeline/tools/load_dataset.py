"""
Load the synthetic dataset (Mongo extended-JSON, one document per line) into the source collection.

    python tools/load_dataset.py                       # data/synthetic_logs.ndjson.gz -> MONGO_DB_NAME/MONGO_COLLECTION
    python tools/load_dataset.py --drop                # empty the collection first
    python tools/load_dataset.py --path other.ndjson.gz

Equivalent with mongoimport:
    gunzip -c data/synthetic_logs.ndjson.gz | mongoimport --uri "$MONGO_URI" --db symthetic_data --collection "distinct logs"
"""
import argparse
import gzip
import os

from _common import DEFAULT_DATA  # noqa: F401  (sets sys.path)
import pymongo
from bson import json_util

from pipeline.config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(DEFAULT_DATA, "synthetic_logs.ndjson.gz"))
    ap.add_argument("--drop", action="store_true", help="drop the source collection first")
    ap.add_argument("--batch", type=int, default=500)
    a = ap.parse_args()

    client = pymongo.MongoClient(MONGO_URI, tz_aware=True)
    col = client[MONGO_DB_NAME][MONGO_COLLECTION]
    if a.drop:
        col.drop()
    opener = gzip.open if a.path.endswith(".gz") else open
    buf, n = [], 0
    with opener(a.path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            buf.append(json_util.loads(line))
            if len(buf) >= a.batch:
                col.insert_many(buf)
                n += len(buf)
                buf = []
        if buf:
            col.insert_many(buf)
            n += len(buf)
    col.create_index("from_date")
    col.create_index([("project", 1), ("resourceId", 1), ("metric", 1)])
    print(f"loaded {n} documents into {MONGO_DB_NAME}.{MONGO_COLLECTION} ({col.estimated_document_count()} total)")


if __name__ == "__main__":
    main()
