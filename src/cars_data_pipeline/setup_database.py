"""Bootstrap pipeline tables in an already-created PostgreSQL database."""
from .config import PROJECT_DIR, connect_database


def main():
    with connect_database() as connection:
        connection.execute((PROJECT_DIR / "sql/001_schema.sql").read_text())
    print("Pipeline schema is ready")


if __name__ == "__main__":
    main()
