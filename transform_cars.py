import csv
import logging
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from pipeline_config import INPUT_FILE, OUTPUT_FILE


COLUMNS = [
    "listing_id", "vehicle_id", "make", "model", "model_year",
    "listing_price", "odometer_km", "hybrid_flag", "hybrid_type",
    "seller_type", "dealer_id", "sale_status", "sale_date",
    "final_sale_price",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def validate_header(path):
    with path.open(newline="", encoding="utf-8-sig") as file:
        header = next(csv.reader(file), [])

    missing = sorted(set(COLUMNS) - set(header))
    duplicates = sorted({
        column for column in header
        if header.count(column) > 1
    })

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if duplicates:
        raise ValueError(f"Duplicate column names: {duplicates}")


def validate_values(df):
    if df.empty:
        raise ValueError("Data contract failed: empty batch")
    errors = []

    for column in ["listing_id", "vehicle_id", "make", "model"]:
        values = df[column].astype("string").str.strip()
        invalid = values.isna() | values.eq("").fillna(False)

        if invalid.any():
            errors.append(
                f"{column}: {invalid.sum():,} missing or blank values"
            )

    numeric_rules = {
        "model_year": {"whole": True, "minimum": None},
        "odometer_km": {"whole": True, "minimum": 0},
        "listing_price": {"whole": False, "minimum": None},
        "hybrid_flag": {"whole": True, "minimum": None},
    }

    for column, rule in numeric_rules.items():
        values = pd.to_numeric(df[column], errors="coerce")
        finite = pd.Series(
            np.isfinite(
                values.to_numpy(dtype=float, na_value=np.nan)
            ),
            index=df.index,
        )
        invalid = ~finite

        if rule["whole"]:
            invalid |= values.mod(1).ne(0).fillna(True)

        if rule["minimum"] is not None:
            invalid |= values.lt(rule["minimum"]).fillna(True)

        if column == "listing_price":
            invalid |= values.le(0).fillna(True)

        if column == "hybrid_flag":
            invalid |= ~values.isin([0, 1])

        if invalid.any():
            errors.append(
                f"{column}: {invalid.sum():,} invalid values"
            )
        else:
            # Store the validated numeric representation.
            df[column] = (
                values.astype("int64")
                if rule["whole"]
                else values
            )

    allowed_statuses = {
        "Available", "Pending", "Reserved", "Sold", "Withdrawn"
    }

    invalid_status = ~df["sale_status"].isin(allowed_statuses)

    if invalid_status.any():
        errors.append(
            f"sale_status: {invalid_status.sum():,} "
            "missing or unrecognized values"
        )

    if errors:
        raise ValueError(
            "Data contract failed:\n- " + "\n- ".join(errors)
        )




def transform(df):
    clean = df.copy()

    # Stop if the identifier cannot support reliable upserts.
    listing_ids = clean["listing_id"].astype("string").str.strip()

    if listing_ids.isna().any() or listing_ids.eq("").any():
        raise ValueError("Missing or blank listing IDs")

    if listing_ids.duplicated().any():
        raise ValueError("Duplicate listing IDs")

    clean["listing_id"] = listing_ids

    non_hybrid = clean["hybrid_flag"].eq(0)
    unknown_hybrid = (
        clean["hybrid_flag"].eq(1)
        & clean["hybrid_type"].isna()
    )

    clean.loc[non_hybrid, "hybrid_type"] = "Not applicable"
    clean.loc[unknown_hybrid, "hybrid_type"] = "Unknown"
    clean["hybrid_type_unknown"] = unknown_hybrid

    original_dates = clean["sale_date"].copy()
    clean["sale_date"] = pd.to_datetime(
        original_dates,
        errors="coerce",
    )

    invalid_dates = (
        original_dates.notna()
        & clean["sale_date"].isna()
    )

    if invalid_dates.any():
        raise ValueError(
            f"Unparseable sale dates: {invalid_dates.sum():,}"
        )

    sold = clean["sale_status"].eq("Sold")
    if (sold & clean["sale_date"].isna()).any():
        raise ValueError("Sold listings must have a sale date")

    prices = pd.to_numeric(clean["final_sale_price"], errors="coerce")
    recorded = sold & clean["final_sale_price"].notna()
    finite = pd.Series(
        np.isfinite(prices.to_numpy(dtype=float, na_value=np.nan)),
        index=clean.index,
    )
    if (recorded & (~finite | prices.le(0))).any():
        raise ValueError("Recorded sale prices must be finite positive numbers")
    clean["completed_sale_price"] = prices.where(sold)
    clean["sold_price_missing"] = (
        sold & clean["final_sale_price"].isna()
    )

    dealer = clean["seller_type"].isin([
        "Authorized Dealer",
        "Independent Dealer",
    ])
    clean["dealer_id_needs_review"] = (
        dealer & clean["dealer_id"].isna()
    )

    return clean


def main():
    logging.info("Reading %s", INPUT_FILE.name)
    validate_header(INPUT_FILE)
    df = pd.read_csv(
        INPUT_FILE,
        usecols=COLUMNS,
        encoding="utf-8-sig",
        dtype={
            "listing_id": "string",
            "vehicle_id": "string",
            "make": "string",
            "model": "string",
            "sale_status": "string",
        },
        low_memory=False,
    )

    validate_values(df)
    logging.info("Data contract passed")

    clean = transform(df)

    for flag in [
        "hybrid_type_unknown",
        "sold_price_missing",
        "dealer_id_needs_review",
    ]:
        logging.info("%s: %s", flag, f"{clean[flag].sum():,}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Finish writing before replacing the previous processed file.
    temporary_file = OUTPUT_FILE.with_suffix(".tmp")
    try:
        clean.to_csv(
            temporary_file,
            index=False,
            date_format="%Y-%m-%d",
        )
        temporary_file.replace(OUTPUT_FILE)
    finally:
        temporary_file.unlink(missing_ok=True)

    parquet_file = OUTPUT_FILE.with_suffix(".parquet")
    temporary_parquet = parquet_file.with_suffix(".parquet.tmp")

    try:
        clean.to_parquet(
            temporary_parquet,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        temporary_parquet.replace(parquet_file)
    finally:
        temporary_parquet.unlink(missing_ok=True)

    logging.info("Saved Parquet file: %s", parquet_file.name)


    logging.info("Saved %s rows to %s", f"{len(clean):,}", OUTPUT_FILE.name)


if __name__ == "__main__":
    main()
