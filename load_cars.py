import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg


INPUT_FILE = Path("data/processed/cars_listings_clean.csv")


def optional_decimal(value):
    """Convert a CSV value into a decimal, preserving missing values."""
    return Decimal(value) if value else None


def optional_date(value):
    """Convert an ISO date into a Python date."""
    return date.fromisoformat(value) if value else None


def payment_rows(reader):
    """Yield one database-ready listing at a time."""
    for row in reader:
        yield (
            row["listing_id"],
            row["vehicle_id"],
            row["make"],
            row["model"],
            int(row["model_year"]),
            optional_decimal(row["listing_price"]),
            int(row["odometer_km"]),
            row["sale_status"],
            optional_date(row["sale_date"]),
            optional_decimal(row["completed_sale_price"]),
        )


def main():
    # Reads connection settings from the PG* environment variables.
    with psycopg.connect("") as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS car_listings (
                    listing_id TEXT PRIMARY KEY,
                    vehicle_id TEXT NOT NULL,
                    make TEXT NOT NULL,
                    model TEXT NOT NULL,
                    model_year INTEGER NOT NULL,
                    listing_price NUMERIC(14, 2),
                    odometer_km BIGINT NOT NULL
                        CHECK (odometer_km >= 0),
                    sale_status TEXT NOT NULL,
                    sale_date DATE,
                    completed_sale_price NUMERIC(14, 2)
                )
            """)

            # Temporary staging table exists only during this transaction.
            cursor.execute("""
                CREATE TEMP TABLE staging_car_listings
                (LIKE car_listings INCLUDING DEFAULTS)
                ON COMMIT DROP
            """)

            loaded = 0

            # COPY loads data efficiently into PostgreSQL.
            with INPUT_FILE.open(newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)

                with cursor.copy("""
                    COPY staging_car_listings (
                        listing_id, vehicle_id, make, model,
                        model_year, listing_price, odometer_km,
                        sale_status, sale_date, completed_sale_price
                    )
                    FROM STDIN
                """) as copy:
                    for record in payment_rows(reader):
                        copy.write_row(record)
                        loaded += 1

            # Upsert: insert new listings and update existing ones.
            cursor.execute("""
                INSERT INTO car_listings
                SELECT * FROM staging_car_listings
                ON CONFLICT (listing_id) DO UPDATE SET
                    vehicle_id = EXCLUDED.vehicle_id,
                    make = EXCLUDED.make,
                    model = EXCLUDED.model,
                    model_year = EXCLUDED.model_year,
                    listing_price = EXCLUDED.listing_price,
                    odometer_km = EXCLUDED.odometer_km,
                    sale_status = EXCLUDED.sale_status,
                    sale_date = EXCLUDED.sale_date,
                    completed_sale_price = EXCLUDED.completed_sale_price
            """)

            cursor.execute("SELECT COUNT(*) FROM car_listings")
            total = cursor.fetchone()[0]

    # Reaching here means the transaction committed successfully.
    print(f"Processed input rows: {loaded:,}")
    print(f"Database rows: {total:,}")


if __name__ == "__main__":
    main()