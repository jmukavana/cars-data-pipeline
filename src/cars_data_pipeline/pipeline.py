"""Run every pipeline stage; publish a manifest only after all checks pass."""
import csv
import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

import psycopg

from .config import (
    DATA_DIR, INPUT_FILE, PROJECT_DIR, connect_database, database_environment,
)
from .setup_database import main as setup_database


# A session-level lock serializes cooperating runners in the same database.
PIPELINE_LOCK = 724031019
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout,
)


def inspect_source(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.reader(file)
        next(reader, None)
        rows = sum(1 for row in reader if row)
    return digest.hexdigest(), rows


def run_batch(audit):
    started = perf_counter()
    batch_id = uuid4()
    run_dir = DATA_DIR / "runs" / str(batch_id)
    snapshot = run_dir / "raw/cars_dataset.csv"
    env = database_environment()
    env.update({
        "CARS_INPUT_FILE": str(snapshot), "CARS_DATA_DIR": str(run_dir),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    })
    audit.execute(
        """INSERT INTO pipeline_batches
        (batch_id, source_file, source_sha256, source_rows, status)
        VALUES (%s, %s, '', 0, 'RUNNING')""",
        (batch_id, str(INPUT_FILE)),
    )
    logging.info("Batch ID: %s", batch_id)
    label = "Snapshot source"
    try:
        snapshot.parent.mkdir(parents=True)
        shutil.copyfile(INPUT_FILE, snapshot)
        fingerprint, source_rows = inspect_source(snapshot)
        audit.execute(
            "UPDATE pipeline_batches SET source_sha256=%s, source_rows=%s WHERE batch_id=%s",
            (fingerprint, source_rows, batch_id),
        )
        steps = [
            ("Transform cars data", [sys.executable, "-m", "cars_data_pipeline.transform"]),
            ("Load source table", [sys.executable, "-m", "cars_data_pipeline.load_source"]),
            ("Load warehouse tables", [sys.executable, "-m", "cars_data_pipeline.load_warehouse"]),
            ("Validate warehouse", [sys.executable, "-m", "cars_data_pipeline.validate_warehouse"]),
            ("Build and test dbt models", [
                str(Path(sys.executable).with_name("dbt")), "build",
                "--project-dir", str(PROJECT_DIR / "dbt"),
                "--profiles-dir", str(PROJECT_DIR / "dbt"),
                "--target-path", str(run_dir / "dbt_target"),
                "--log-path", str(run_dir / "logs"),
            ]),
            ("Export partitioned sales", [sys.executable, "-m", "cars_data_pipeline.partition_sales"]),
        ]
        for label, command in steps:
            logging.info("Starting: %s", label)
            subprocess.run(command, cwd=PROJECT_DIR, env=env, check=True)
            logging.info("Finished: %s", label)

        label = "Publish successful batch"
        manifest = {
            "batch_id": str(batch_id), "source_sha256": fingerprint,
            "source_rows": source_rows, "source_snapshot": str(snapshot),
            "clean_csv": str(run_dir / "processed/cars_listings_clean.csv"),
            "clean_parquet": str(run_dir / "processed/cars_listings_clean.parquet"),
            "sales_export": str(run_dir / "analytics/sales"),
            "dbt_results": str(run_dir / "dbt_target/run_results.json"),
        }
        serialized = json.dumps(manifest, indent=2) + "\n"
        (run_dir / "manifest.json").write_text(serialized)
        latest_tmp = DATA_DIR / f".latest-{batch_id}.tmp"
        latest_tmp.write_text(serialized)
        audit.execute(
            """UPDATE pipeline_batches SET status='SUCCESS', finished_at=CURRENT_TIMESTAMP
            WHERE batch_id=%s""", (batch_id,),
        )
        latest_tmp.replace(DATA_DIR / "latest.json")
    except (Exception, KeyboardInterrupt):
        logging.exception("Batch %s failed: %s", batch_id, label)
        try:
            audit.execute(
                """UPDATE pipeline_batches SET status='FAILED',
                finished_at=CURRENT_TIMESTAMP, failed_step=%s WHERE batch_id=%s""",
                (label, batch_id),
            )
        except psycopg.Error:
            logging.exception("Could not record failure for batch %s", batch_id)
        return 1
    logging.info("Batch %s completed in %.2f seconds", batch_id, perf_counter() - started)
    logging.info("Successful outputs: %s", DATA_DIR / "latest.json")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the complete cars analytics batch pipeline.")
    parser.add_argument("--setup-only", action="store_true", help="Create missing tables and exit")
    args = parser.parse_args(argv)
    try:
        with connect_database(autocommit=True) as audit:
            if not audit.execute("SELECT pg_try_advisory_lock(%s)", (PIPELINE_LOCK,)).fetchone()[0]:
                logging.error("Another pipeline run is active in this database")
                return 1
            setup_database()
            if args.setup_only:
                return 0
            return run_batch(audit)
    except (psycopg.Error, OSError):
        logging.exception("Could not initialize pipeline; check PostgreSQL settings and schema")
        return 1


if __name__ == "__main__":
    sys.exit(main())
