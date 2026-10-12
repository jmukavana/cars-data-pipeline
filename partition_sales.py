from pathlib import Path
from uuid import uuid4

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
SOURCE = PROJECT_DIR / "data/processed/cars_listings_clean.parquet"

# Each export gets its own directory to avoid mixing old and new files.
EXPORT_DIR = (
    PROJECT_DIR
    / "data/analytics/sales"
    / f"export_{uuid4().hex}"
)

df = pd.read_parquet(SOURCE)

sold = df.loc[df["sale_status"].eq("Sold")].copy()

missing_dates = sold["sale_date"].isna().sum()
if missing_dates:
    raise ValueError(
        f"Cannot partition sales: {missing_dates:,} sold listings lack dates"
    )

if sold.empty:
    raise ValueError("No sold listings to export")

sold["sale_year"] = sold["sale_date"].dt.year.astype("int64")

EXPORT_DIR.mkdir(parents=True)

sold.to_parquet(
    EXPORT_DIR,
    engine="pyarrow",
    partition_cols=["sale_year"],
    compression="snappy",
    index=False,
)

print(f"Export directory: {EXPORT_DIR}")
print(f"Sold listings exported: {len(sold):,}")

print("\nRows by sale year:")
print(sold.groupby("sale_year").size().to_string())

# Read only one year's partition.
selected_year = int(sold["sale_year"].max())

one_year = pd.read_parquet(
    EXPORT_DIR,
    engine="pyarrow",
    filters=[("sale_year", "==", selected_year)],
)

print(f"\nRows read for {selected_year}: {len(one_year):,}")

expected = sold["sale_year"].eq(selected_year).sum()
if len(one_year) != expected:
    raise ValueError("Partition read-back count does not match")

print("Partition read-back check passed")