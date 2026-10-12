import logging
import sys

import psycopg

from pipeline_config import connect_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def main():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )

            cursor.execute("SELECT COUNT(*) FROM car_listings")
            source_count = cursor.fetchone()[0]

            if source_count == 0:
                raise ValueError("Source table is empty")

            cursor.execute("""
                SELECT COUNT(*)
                FROM car_listings AS c
                LEFT JOIN fact_car_listing AS f
                    ON f.listing_id = c.listing_id
                WHERE f.listing_id IS NULL
            """)
            missing = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*)
                FROM car_listings AS c
                JOIN fact_car_listing AS f
                    ON f.listing_id = c.listing_id
                LEFT JOIN dim_vehicle_model AS v
                    ON v.vehicle_model_key = f.vehicle_model_key
                LEFT JOIN dim_listing_status AS s
                    ON s.status_key = f.status_key
                WHERE ROW(
                    c.vehicle_id,
                    c.make,
                    c.model,
                    c.model_year,
                    c.sale_status,
                    c.listing_price,
                    c.completed_sale_price,
                    c.odometer_km,
                    c.sale_date
                ) IS DISTINCT FROM ROW(
                    f.vehicle_id,
                    v.make,
                    v.model,
                    v.model_year,
                    s.sale_status,
                    f.listing_price,
                    f.completed_sale_price,
                    f.odometer_km,
                    f.sale_date
                )
            """)
            mismatched = cursor.fetchone()[0]

            logging.info("Source listings checked: %s", f"{source_count:,}")
            logging.info("Missing facts: %s", missing)
            logging.info("Mismatched facts: %s", mismatched)

            if missing or mismatched:
                raise ValueError(
                    f"Warehouse validation failed: "
                    f"{missing} missing, {mismatched} mismatched"
                )

    logging.info("Warehouse validation passed")


if __name__ == "__main__":
    main()
