"""Shared paths and PostgreSQL settings for scripts and orchestration."""
import os
from pathlib import Path

import psycopg


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CARS_DATA_DIR", PROJECT_DIR / "data")).resolve()
INPUT_FILE = Path(os.environ.get("CARS_INPUT_FILE", DATA_DIR / "raw/cars_dataset.csv")).resolve()
OUTPUT_FILE = DATA_DIR / "processed/cars_listings_clean.csv"


def database_environment():
    env = os.environ.copy()
    env.setdefault("PGHOST", env.get("DBT_HOST", "127.0.0.1"))
    env.setdefault("PGPORT", "5432")
    env.setdefault("PGUSER", "postgres")
    env.setdefault("PGDATABASE", "cars_analytics")
    env.setdefault("PGPASSWORD", env.get("DBT_ENV_SECRET_CARS_PASSWORD", ""))
    # dbt masks values whose environment-variable names start with this prefix.
    env["DBT_ENV_SECRET_CARS_PASSWORD"] = env["PGPASSWORD"]
    return env


def connect_database(**kwargs):
    env = database_environment()
    return psycopg.connect(
        host=env["PGHOST"], port=env["PGPORT"], user=env["PGUSER"],
        dbname=env["PGDATABASE"], password=env["PGPASSWORD"],
        connect_timeout=10, **kwargs,
    )
