import logging
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
INPUT_FILE = PROJECT_DIR / "data/raw/cars_dataset.csv"
OUTPUT_FILE = PROJECT_DIR / "data/processed/cars_listings_clean.csv"

COLUMNS = [
    "listing_id", "vehicle_id", "make", "model", "model_year",
    "listing_price", "odometer_km", "hybrid_flag", "hybrid_type",
    "seller_type", "dealer_id", "sale_status", "sale_date",
    "final_sale_price",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
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
    clean["completed_sale_price"] = clean["final_sale_price"].where(sold)
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
    df = pd.read_csv(INPUT_FILE, usecols=COLUMNS, low_memory=False)

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

    logging.info("Saved %s rows to %s", f"{len(clean):,}", OUTPUT_FILE.name)


if __name__ == "__main__":
    main()