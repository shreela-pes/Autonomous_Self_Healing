"""
Simulate real time: pre-load the history, then insert the remaining days ONE DAY AT A TIME so that
`python main.py --mode poll` (or --mode stream on a replica set) reacts to them as they "arrive".

    python tools/replay_stream.py --preload-days 62 --seconds-per-day 10
    # in another terminal:  python main.py --mode poll --no-llm
"""
import argparse
import gzip
import os
import time
from collections import defaultdict

from _common import DEFAULT_DATA  # noqa: F401
import pymongo
from bson import json_util

from pipeline.config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.path.join(DEFAULT_DATA, "synthetic_logs.ndjson.gz"))
    ap.add_argument("--preload-days", type=int, default=62, help="days inserted immediately (history)")
    ap.add_argument("--seconds-per-day", type=float, default=10.0)
    ap.add_argument("--drop", action="store_true")
    a = ap.parse_args()

    client = pymongo.MongoClient(MONGO_URI, tz_aware=True)
    col = client[MONGO_DB_NAME][MONGO_COLLECTION]
    if a.drop:
        col.drop()
    by_day = defaultdict(list)
    with gzip.open(a.path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json_util.loads(line)
            by_day[d["from_date"].strftime("%Y-%m-%d")].append(d)
    days = sorted(by_day)
    pre, live = days[:a.preload_days], days[a.preload_days:]
    for day in pre:
        col.insert_many(by_day[day])
    print(f"pre-loaded {len(pre)} days ({days[0]} .. {pre[-1]}); streaming {len(live)} more day(s)")
    for day in live:
        col.insert_many(by_day[day])
        print(f"  inserted {day}: {len(by_day[day])} docs")
        time.sleep(a.seconds_per_day)


if __name__ == "__main__":
    main()
