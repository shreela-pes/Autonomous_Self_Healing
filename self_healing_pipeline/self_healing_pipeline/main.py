"""
Self-Healing Recommendation Pipeline — Entry Point

Real-time, alert-gated self-healing RECOMMENDATIONS (nothing is remediated automatically).

Modes:
  batch   Replay all existing documents oldest-first in day batches (default)
  stream  Listen to MongoDB change streams (replica set required)
  poll    Poll for new documents (works on a standalone mongod)

Usage:
  python main.py                        # batch, all docs, LLM explanation if Ollama is up
  python main.py --no-llm               # deterministic template explanations only
  python main.py --reset                # drop derived collections first (clean replay)
  python main.py --mode stream          # real-time change stream
  python main.py --mode batch --limit 1000  --skip 0
  python main.py --mode batch --project <project_id>  # one project only
  python main.py --mode batch --resource-type EC2     # one type only
  python main.py --health               # check Ollama + MongoDB then exit
  python main.py --db my_output_db      # write/read a different output database (else MONGO_DB_NAME from .env)
  python main.py --ui --db my_output_db # UI-only run, pointed at that database
"""

import argparse
import logging
import os
import sys
import time

import pymongo

# --db is applied to the environment BEFORE importing pipeline.config, since config.py reads
# MONGO_DB_NAME at import time. This must run before any pipeline import below.
def _apply_db_override():
    if "--db" in sys.argv:
        i = sys.argv.index("--db")
        if i + 1 < len(sys.argv):
            os.environ["MONGO_DB_NAME"] = sys.argv[i + 1]


_apply_db_override()

from pipeline.config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION, DERIVED_COLLECTIONS
from pipeline.recommendation.engine import RecommendationEngine
from pipeline.ingestion.change_stream import ChangeStreamListener
from pipeline.llm.ollama_client import OllamaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def build_client() -> pymongo.MongoClient:
    return pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, tz_aware=True)


def health_check(client: pymongo.MongoClient) -> bool:
    ok = True
    # MongoDB
    try:
        db  = client[MONGO_DB_NAME]
        col = db[MONGO_COLLECTION]
        cnt = col.estimated_document_count()
        logger.info("MongoDB OK — collection '%s' has ~%d documents", MONGO_COLLECTION, cnt)
    except Exception as exc:
        logger.error("MongoDB FAILED: %s", exc)
        ok = False

    # Ollama
    ollama = OllamaClient()
    if ollama.health_check():
        logger.info("Ollama OK — model '%s' is available", ollama.model)
    else:
        logger.warning("Ollama WARNING — model '%s' not found; fallback recommendations will be used", ollama.model)

    return ok


def parse_args():
    p = argparse.ArgumentParser(description="Self-Healing Cloud Recommendation Pipeline")
    p.add_argument("--mode",          choices=["batch", "stream", "poll"], default="batch",
                   help="Processing mode (default: batch)")
    p.add_argument("--limit",         type=int, default=0,
                   help="Max documents to process in batch mode (0 = all)")
    p.add_argument("--skip",          type=int, default=0,
                   help="Number of documents to skip in batch mode")
    p.add_argument("--project",       type=str, default=None,
                   help="Filter batch by project ID")
    p.add_argument("--resource-type", type=str, default=None,
                   help="Filter batch by resource_type (e.g. EC2, EBS)")
    p.add_argument("--category",      type=str, default=None,
                   help="Filter batch by category (Compute or Storage)")
    p.add_argument("--no-llm",        action="store_true",
                   help="Do not call Ollama; use deterministic template explanations")
    p.add_argument("--reset",         action="store_true",
                   help="Drop the pipeline's derived collections (profiles, incidents, recommendations, ...) before running. "
                        "The source log collection is never touched.")
    p.add_argument("--db",            type=str, default=None,
                   help="Output database name to write to (pipeline run) or read from (--ui). "
                        "Overrides MONGO_DB_NAME from .env for this process. Same DB holds the source log "
                        "collection and every derived collection (recommendations, incidents, ...).")
    p.add_argument("--ui",            action="store_true",
                   help="Launch the Streamlit UI (reads the recommendations from MongoDB) and exit")
    p.add_argument("--ui-port",       type=int, default=8501, help="Port for --ui (default 8501)")
    p.add_argument("--run-ui",        action="store_true",
                   help="After the batch run finishes, launch the Streamlit UI")
    p.add_argument("--health",        action="store_true",
                   help="Run health check and exit")
    p.add_argument("--log-level",     default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def _launch_ui(port: int) -> None:
    import os
    import subprocess
    import sys
    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "app.py")
    logger.info("Starting UI on http://localhost:%d against database '%s'  (Ctrl-C to stop)", port, MONGO_DB_NAME)
    subprocess.run([sys.executable, "-m", "streamlit", "run", app, "--server.port", str(port)])


def main():
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    if args.ui:
        _launch_ui(args.ui_port)
        return

    client = build_client()

    if args.health:
        ok = health_check(client)
        sys.exit(0 if ok else 1)

    # Validate connectivity before starting
    try:
        client.server_info()
        logger.info("Connected to MongoDB at %s", MONGO_URI)
    except Exception as exc:
        logger.error("Cannot connect to MongoDB: %s", exc)
        sys.exit(1)

    db = client[MONGO_DB_NAME]
    if args.reset:
        for name in DERIVED_COLLECTIONS:
            db[name].drop()
        logger.info("Dropped derived collections: %s", ", ".join(DERIVED_COLLECTIONS))

    use_llm = not args.no_llm
    ollama = None
    if use_llm:
        ollama = OllamaClient()
        if not ollama.health_check():
            logger.warning("Ollama/model not available - explanations will use the deterministic template")
            ollama = None
    engine = RecommendationEngine(db, ollama_client=ollama, use_llm=use_llm and ollama is not None)
    listener = ChangeStreamListener(client=client, process_batch_fn=engine.process_batch)

    if args.mode == "stream":
        logger.info("Starting in STREAM mode...")
        try:
            listener.run_stream()
        except KeyboardInterrupt:
            logger.info("Stream stopped by user.")

    elif args.mode == "poll":
        logger.info("Starting in POLL mode...")
        try:
            listener.run_poll()
        except KeyboardInterrupt:
            logger.info("Polling stopped by user.")

    else:  # batch
        logger.info("Starting in BATCH mode...")
        query_filter: dict = {}
        if args.project:
            query_filter["project"] = args.project
        if args.resource_type:
            query_filter["resource_type"] = args.resource_type
        if args.category:
            query_filter["category"] = args.category

        t0 = time.time()
        stats = listener.run_batch(
            query_filter = query_filter or None,
            limit        = args.limit,
            skip         = args.skip,
        )
        elapsed = time.time() - t0
        logger.info(
            "Done in %.1fs — processed=%d  recommendations=%d  errors=%d",
            elapsed, stats["processed"], stats["recommendations"], stats["errors"],
        )

    client.close()


if __name__ == "__main__":
    main()
