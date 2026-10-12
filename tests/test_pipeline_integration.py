"""Real PostgreSQL/dbt acceptance tests; each test owns a disposable database."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


ROOT = Path(__file__).resolve().parents[1]
ADMIN_DSN = os.environ.get("CARS_TEST_ADMIN_DSN")
FIXTURE = ROOT / "tests/fixtures/listings.csv"


@unittest.skipUnless(ADMIN_DSN, "Set CARS_TEST_ADMIN_DSN to run PostgreSQL/dbt tests")
class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.database = "cars_test_" + uuid4().hex
        self.admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))
        self.addCleanup(self.drop_database)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        self.source = self.data / "input.csv"
        self.source.write_bytes(FIXTURE.read_bytes())
        settings = conninfo_to_dict(ADMIN_DSN)
        self.env = os.environ.copy()
        for name in list(self.env):
            if name.startswith(("PG", "DBT_", "CARS_")):
                self.env.pop(name)
        self.env.update({
            "PGHOST": settings.get("host", "127.0.0.1"),
            "PGPORT": settings.get("port", "5432"),
            "PGUSER": settings.get("user", "postgres"),
            "PGPASSWORD": settings.get("password", ""),
            "PGDATABASE": self.database,
            "CARS_DATA_DIR": str(self.data / "output"),
            "CARS_INPUT_FILE": str(self.source),
        })
        self.db = psycopg.connect(ADMIN_DSN, dbname=self.database, autocommit=True)
        self.addCleanup(self.db.close)

    def drop_database(self):
        self.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self.database)))

    def run_script(self, name, success=True):
        result = subprocess.run(
            [sys.executable, str(ROOT / name)], cwd=ROOT, env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def latest(self):
        return json.loads((self.data / "output/latest.json").read_text())

    def change_source(self, **changes):
        with self.source.open(newline="") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames
            rows = list(reader)
        rows[0].update(changes)
        with self.source.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_fresh_setup_rerun_and_changed_listing_reach_reports_and_export(self):
        self.run_script("run_pipeline.py")
        self.assertEqual(self.db.execute("SELECT count(*) FROM fact_car_listing").fetchone()[0], 3)
        self.assertEqual(self.db.execute(
            "SELECT sold_listings, known_sale_prices, recorded_sales_value FROM dbt_cars.monthly_sales"
        ).fetchone(), (2, 1, 12000))
        first = self.latest()
        self.assertEqual(first["source_rows"], 3)
        self.assertEqual(len(pd.read_parquet(first["sales_export"])), 2)
        original = self.db.execute("SELECT listing_id, xmin::text FROM fact_car_listing ORDER BY 1").fetchall()

        self.run_script("run_pipeline.py")
        self.assertEqual(self.db.execute("SELECT listing_id, xmin::text FROM fact_car_listing ORDER BY 1").fetchall(), original)
        self.assertEqual(self.db.execute("SELECT count(*) FROM car_listings").fetchone()[0], 3)
        fingerprints = self.db.execute("SELECT count(DISTINCT source_sha256) FROM pipeline_batches").fetchone()[0]
        self.assertEqual(fingerprints, 1)

        self.change_source(final_sale_price="14000")
        self.run_script("run_pipeline.py")
        self.assertEqual(self.db.execute(
            "SELECT completed_sale_price FROM fact_car_listing WHERE listing_id='L001'"
        ).fetchone()[0], 14000)
        self.assertEqual(self.db.execute("SELECT recorded_sales_value FROM dbt_cars.monthly_sales").fetchone()[0], 14000)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pipeline_batches WHERE status='SUCCESS'").fetchone()[0], 3)

    def test_failed_database_load_rolls_back_and_rerun_recovers(self):
        self.run_script("run_pipeline.py")
        previous = self.latest()
        self.db.execute("ALTER TABLE fact_car_listing ADD CONSTRAINT test_reject_price CHECK (completed_sale_price < 13000)")
        self.change_source(final_sale_price="14000")
        self.run_script("run_pipeline.py", success=False)
        self.assertEqual(self.db.execute("SELECT completed_sale_price FROM fact_car_listing WHERE listing_id='L001'").fetchone()[0], 12000)
        self.assertEqual(self.db.execute("SELECT status, failed_step FROM pipeline_batches ORDER BY started_at DESC LIMIT 1").fetchone(), ("FAILED", "Load warehouse tables"))
        self.assertEqual(self.latest(), previous)
        self.db.execute("ALTER TABLE fact_car_listing DROP CONSTRAINT test_reject_price")
        self.run_script("run_pipeline.py")
        self.assertEqual(self.db.execute("SELECT completed_sale_price FROM fact_car_listing WHERE listing_id='L001'").fetchone()[0], 14000)

    def test_invalid_batch_is_audited_without_loading(self):
        self.change_source(sale_date="")
        self.run_script("run_pipeline.py", success=False)
        self.assertEqual(self.db.execute("SELECT status, failed_step FROM pipeline_batches").fetchone(), ("FAILED", "Transform cars data"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM car_listings").fetchone()[0], 0)
        self.assertFalse((self.data / "output/latest.json").exists())

