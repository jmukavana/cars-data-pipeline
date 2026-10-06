from pathlib import Path

import pandas as pd

columns = [
    "listing_id",
    "vehicle_id",
    "make",
    "model",
    "model_year",
    "listing_price",
    "odometer_km",
    "hybrid_flag",
    "hybrid_type",
    "seller_type",
    "dealer_id",
    "sale_status",
    "sale_date",
    "final_sale_price",
]

df = pd.read_csv(
    "data/raw/cars_dataset.csv",
    usecols=columns,
    low_memory=False
)



print("\n Identifier check ..")
for column in ["listing_id","vehicle_id"]:
    print(
        f"{column}: "
        f"{df[column].isna().sum():,} missing, "
        f"{df[column].dropna().duplicated().sum():,} repeated after first"
    )
print("\n listing by make ..")

toyota = df.loc[
    (df["make"] == "Toyota") & (df["model_year"] == 2020),
    ["make","model","model_year","listing_price"],
]

print("\n Toyota listing from 2020 onwards:first 10 ..")
print(toyota.head(10).to_string(index=False))


print("\n Hybrid flag vs missing hybrid flag ..")
print(
    pd.crosstab(
        df["hybrid_flag"],
        df["hybrid_type"].isna(),
        colnames=["hybrid_type_missing"],
    )
)

print("\n seller type vs dealer id ..")
print(
    pd.crosstab(
        df["seller_type"],
        df["dealer_id"].isna(),
        colnames=["dealer_id_missing"],
    )
)
df["sale_date_missing"] = df["sale_date"].isna()
df["sale_price_missing"] = df["final_sale_price"].isna()
df["sale_price_zero"] = df["final_sale_price"].eq(0)


sale_summary=df.groupby("sale_status",dropna=False).agg(
    rows=("listing_id","size"),
    missing_sale_dates=("sale_date_missing", "sum"),
    missing_sale_prices=("sale_price_missing", "sum"),
    zero_sale_prices=("sale_price_zero", "sum"),
)

print("\n Sale summary ..")
print(sale_summary.to_string())



# Work on a separate copy.
clean = df.copy()

# 1. Distinguish non-applicable hybrid types from unknown ones.
non_hybrid = clean["hybrid_flag"].eq(0)
hybrid_type_unknown = (
    clean["hybrid_flag"].eq(1)
    & clean["hybrid_type"].isna()
)

clean.loc[non_hybrid, "hybrid_type"] = "Not applicable"
clean.loc[hybrid_type_unknown, "hybrid_type"] = "Unknown"

# Preserve a flag so we can count the missing source information.
clean["hybrid_type_unknown"] = hybrid_type_unknown

# 2. Parse sale dates and flag values that fail conversion.
original_dates = clean["sale_date"].copy()

clean["sale_date"] = pd.to_datetime(
    original_dates,
    errors="coerce",
)

clean["sale_date_parse_failed"] = (
    original_dates.notna()
    & clean["sale_date"].isna()
)

# 3. Create an analytical sale-price column.
# Preserve final_sale_price exactly as it was received.
sold = clean["sale_status"].eq("Sold")

clean["completed_sale_price"] = clean["final_sale_price"].where(sold)

clean["sold_price_missing"] = (
    sold & clean["final_sale_price"].isna()
)

# 4. Flag missing dealer IDs without inventing replacements.
dealer = clean["seller_type"].isin([
    "Authorized Dealer",
    "Independent Dealer",
])

clean["dealer_id_needs_review"] = (
    dealer & clean["dealer_id"].isna()
)

# 5. Report the results.
print("\n--- Transformation checks ---")

checks = [
    "hybrid_type_unknown",
    "sale_date_parse_failed",
    "sold_price_missing",
    "dealer_id_needs_review",
]

for column in checks:
    print(f"{column}: {clean[column].sum():,}")

print("\n--- Completed sales with known prices ---")

known_sales = clean.loc[
    sold & clean["completed_sale_price"].notna()
]

print(f"Sold listings: {sold.sum():,}")
print(f"Sold listings with known prices: {len(known_sales):,}")
print(
    "Average recorded sale price: "
    f"{known_sales['completed_sale_price'].mean():,.2f}"
)

output_dir = Path("data/processed")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "cars_listings_clean.csv"

clean.to_csv(
    output_file,
    index=False,
    date_format="%Y-%m-%d",
)

print(f"\nSaved {len(clean):,} rows to {output_file}")


saved = pd.read_csv(
    "data/processed/cars_listings_clean.csv",
    parse_dates=["sale_date"],
)

print(f"Reloaded rows: {len(saved):,}")
print(f"Sale date type: {saved['sale_date'].dtype}")