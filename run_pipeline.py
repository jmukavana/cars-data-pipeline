import csv
import hashlib
import logging
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from uuid import uuid4

import psycopg


PROJECT_DIR = Path(__file__).resolve().parent
INPUT_FILE = PROJECT_DIR / "data/raw/cars_dataset.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def inspect_source():
    digest = hashlib.sha256()

    with INPUT_FILE.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    with INPUT_FILE.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header.
        rows = sum(1 for _ in reader)

    return digest.hexdigest(), rows


def main():
    started = perf_counter()
    batch_id = uuid4()
    fingerprint, source_rows = inspect_source()

    steps = [
        ("Transform cars data", "transform_cars.py"),
        ("Load source table", "load_cars.py"),
        ("Load warehouse tables", "load_warehouse.py"),
        ("Validate warehouse", "validate_warehouse.py"),
    ]

    # Commit audit updates immediately, independently of data loads.
    with psycopg.connect("", autocommit=True, connect_timeout=10) as audit:
        audit.execute(
            """
            INSERT INTO pipeline_batches (
                batch_id, source_file, source_sha256,
                source_rows, status
            )
            VALUES (%s, %s, %s, %s, 'RUNNING')
            """,
            (batch_id, INPUT_FILE.name, fingerprint, source_rows),
        )

        logging.info("Batch ID: %s", batch_id)

        for label, script in steps:
            logging.info("Starting: %s", label)

            try:
                subprocess.run(
                    [sys.executable, str(PROJECT_DIR / script)],
                    cwd=PROJECT_DIR,
                    check=True,
                )
            except (subprocess.CalledProcessError, OSError):
                logging.exception("Failed: %s", label)

                try:
                    audit.execute(
                        """
                        UPDATE pipeline_batches
                        SET status = 'FAILED',
                            finished_at = CURRENT_TIMESTAMP,
                            failed_step = %s
                        WHERE batch_id = %s
                        """,
                        (label, batch_id),
                    )
                except psycopg.Error:
                    logging.exception(
                        "Could not record failure for batch %s",
                        batch_id,
                    )

                return 1

            logging.info("Finished: %s", label)

        audit.execute(
            """
            UPDATE pipeline_batches
            SET status = 'SUCCESS',
                finished_at = CURRENT_TIMESTAMP
            WHERE batch_id = %s
            """,
            (batch_id,),
        )

    logging.info(
        "Batch %s completed in %.2f seconds",
        batch_id,
        perf_counter() - started,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())