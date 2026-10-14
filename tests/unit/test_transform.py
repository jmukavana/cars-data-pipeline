import csv
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from cars_data_pipeline.transform import (
    COLUMNS,
    validate_header,
    validate_values,
    transform,
)


class DataContractTests(unittest.TestCase):

    def sample(self):
        return pd.DataFrame([{
            "listing_id": "L001",
            "vehicle_id": "V001",
            "make": "Toyota",
            "model": "Corolla",
            "model_year": 2020,
            "odometer_km": 50000,
            "listing_price": 15000.00,
            "hybrid_flag": 0,
            "sale_status": "Available",
        }])

    def test_valid_record_passes(self):
        validate_values(self.sample())

    def test_negative_mileage_is_rejected(self):
        df = self.sample()
        df.loc[0, "odometer_km"] = -100

        with self.assertRaisesRegex(ValueError, "odometer_km"):
            validate_values(df)

    def test_unknown_status_is_rejected(self):
        df = self.sample()
        df.loc[0, "sale_status"] = "UnexpectedStatus"

        with self.assertRaisesRegex(ValueError, "sale_status"):
            validate_values(df)

    def test_blank_identifier_is_rejected(self):
        df = self.sample()
        df.loc[0, "listing_id"] = "   "

        with self.assertRaisesRegex(ValueError, "listing_id"):
            validate_values(df)

    def test_infinite_price_is_rejected(self):
        df = self.sample()
        df.loc[0, "listing_price"] = float("inf")

        with self.assertRaisesRegex(ValueError, "listing_price"):
            validate_values(df)

    def test_missing_required_column_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cars.csv"

            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    column for column in COLUMNS
                    if column != "listing_price"
                ])

            with self.assertRaisesRegex(ValueError, "listing_price"):
                validate_header(path)

    def full_sample(self):
        return self.sample().assign(
            hybrid_type=None, seller_type="Private", dealer_id=None,
            sale_date=None, final_sale_price=None,
        )

    def test_sold_without_date_is_rejected_before_loading(self):
        df = self.full_sample()
        df.loc[0, "sale_status"] = "Sold"
        with self.assertRaisesRegex(ValueError, "sale date"):
            transform(df)

    def test_invalid_completed_price_is_rejected(self):
        for price in [-1, 0, float("inf"), "not-a-price"]:
            with self.subTest(price=price):
                df = self.full_sample().assign(
                    sale_status="Sold", sale_date="2026-01-15",
                    final_sale_price=price,
                )
                with self.assertRaisesRegex(ValueError, "sale price"):
                    transform(df)

    def test_missing_sold_price_is_preserved(self):
        df = self.full_sample().assign(
            sale_status="Sold", sale_date="2026-01-15",
        )
        result = transform(df)
        self.assertTrue(pd.isna(result.loc[0, "completed_sale_price"]))
        self.assertTrue(result.loc[0, "sold_price_missing"])

    def test_unsold_price_is_not_counted_as_revenue(self):
        result = transform(self.full_sample().assign(final_sale_price=12000))
        self.assertTrue(pd.isna(result.loc[0, "completed_sale_price"]))

    def test_empty_batch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_values(self.full_sample().iloc[:0])


if __name__ == "__main__":
    unittest.main()
