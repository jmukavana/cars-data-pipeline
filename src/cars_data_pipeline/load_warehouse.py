import logging
import sys
from .config import connect_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def main():
    with connect_database() as connection:
        with connection.cursor() as cursor:
            # Keep all source reads consistent during this load.
            cursor.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            )

            cursor.execute("""
                INSERT INTO dim_vehicle_model (make, model, model_year)
                SELECT DISTINCT make, model, model_year
                FROM car_listings
                ON CONFLICT (make, model, model_year) DO NOTHING
            """)
            logging.info("New vehicle models: %s", cursor.rowcount)

            cursor.execute("""
                INSERT INTO dim_listing_status (sale_status)
                SELECT DISTINCT sale_status
                FROM car_listings
                ON CONFLICT (sale_status) DO NOTHING
            """)
            logging.info("New listing statuses: %s", cursor.rowcount)

            # Fail before loading facts if any dimension lookup fails.
            cursor.execute("""
                SELECT COUNT(*)
                FROM car_listings AS c
                LEFT JOIN dim_vehicle_model AS v
                    ON v.make = c.make
                    AND v.model = c.model
                    AND v.model_year = c.model_year
                LEFT JOIN dim_listing_status AS s
                    ON s.sale_status = c.sale_status
                WHERE v.vehicle_model_key IS NULL
                   OR s.status_key IS NULL
            """)

            unmatched = cursor.fetchone()[0]
            if unmatched:
                raise ValueError(
                    f"{unmatched:,} listings have unmatched dimensions"
                )

            cursor.execute("""
                INSERT INTO fact_car_listing (
                    listing_id,
                    vehicle_id,
                    vehicle_model_key,
                    status_key,
                    listing_price,
                    completed_sale_price,
                    odometer_km,
                    sale_date
                )
                SELECT
                    c.listing_id,
                    c.vehicle_id,
                    v.vehicle_model_key,
                    s.status_key,
                    c.listing_price,
                    c.completed_sale_price,
                    c.odometer_km,
                    c.sale_date
                FROM car_listings AS c
                JOIN dim_vehicle_model AS v
                    ON v.make = c.make
                    AND v.model = c.model
                    AND v.model_year = c.model_year
                JOIN dim_listing_status AS s
                    ON s.sale_status = c.sale_status
                ON CONFLICT (listing_id) DO UPDATE SET
                    vehicle_id = EXCLUDED.vehicle_id,
                    vehicle_model_key = EXCLUDED.vehicle_model_key,
                    status_key = EXCLUDED.status_key,
                    listing_price = EXCLUDED.listing_price,
                    completed_sale_price = EXCLUDED.completed_sale_price,
                    odometer_km = EXCLUDED.odometer_km,
                    sale_date = EXCLUDED.sale_date
                WHERE ROW(
                        fact_car_listing.vehicle_id,
                        fact_car_listing.vehicle_model_key,
                        fact_car_listing.status_key,
                        fact_car_listing.listing_price,
                        fact_car_listing.completed_sale_price,
                        fact_car_listing.odometer_km,
                        fact_car_listing.sale_date
                    ) IS DISTINCT FROM ROW(
                        EXCLUDED.vehicle_id,
                        EXCLUDED.vehicle_model_key,
                        EXCLUDED.status_key,
                        EXCLUDED.listing_price,
                        EXCLUDED.completed_sale_price,
                        EXCLUDED.odometer_km,
                        EXCLUDED.sale_date
                    )
                """)
            processed = cursor.rowcount

            cursor.execute("""
                SELECT COUNT(*)
                FROM car_listings AS c
                LEFT JOIN fact_car_listing AS f
                    ON f.listing_id = c.listing_id
                WHERE f.listing_id IS NULL
            """)

            missing = cursor.fetchone()[0]
            if missing:
                raise ValueError(
                    f"{missing:,} source listings are missing from facts"
                )

    logging.info(
        "Warehouse transaction committed: %s facts inserted or updated",
        f"{processed:,}",
    )


if __name__ == "__main__":
    main()
