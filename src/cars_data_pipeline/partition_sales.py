"""Export this input batch's sold listings, partitioned by sale year."""
import json

import pandas as pd

from .config import DATA_DIR, OUTPUT_FILE


def main():
    source = OUTPUT_FILE.with_suffix(".parquet")
    export_dir = DATA_DIR / "analytics/sales"
    df = pd.read_parquet(source)
    sold = df.loc[df["sale_status"].eq("Sold")].copy()
    missing_dates = sold["sale_date"].isna().sum()
    if missing_dates:
        raise ValueError(f"Cannot partition sales: {missing_dates:,} sold listings lack dates")
    sold["sale_year"] = sold["sale_date"].dt.year.astype("int64")
    # A fresh destination prevents stale partitions being mixed into this export.
    export_dir.mkdir(parents=True, exist_ok=False)
    if sold.empty:
        # Preserve a readable schema even when the batch contains no sales.
        sold.to_parquet(export_dir / "empty.parquet", index=False, compression="snappy")
    else:
        sold.to_parquet(
            export_dir, engine="pyarrow", partition_cols=["sale_year"],
            compression="snappy", index=False,
        )

    exported = pd.read_parquet(export_dir)

    for label, frame in (
        ("Source sold listings", sold),
        ("Exported listings", exported),
    ):
        ids = frame["listing_id"]

        if ids.isna().any():
            raise ValueError(f"{label} contain null listing IDs")

        if ids.duplicated().any():
            raise ValueError(f"{label} contain duplicate listing IDs")

    expected_ids = set(sold["listing_id"])
    actual_ids = set(exported["listing_id"])

    missing_ids = expected_ids - actual_ids
    unexpected_ids = actual_ids - expected_ids

    if missing_ids or unexpected_ids:
        raise ValueError(
            "Export listing IDs do not match: "
            f"{len(missing_ids):,} missing, "
            f"{len(unexpected_ids):,} unexpected"
        )

    if len(exported) != len(sold):
        raise ValueError("Export read-back count does not match")

    for year, expected in sold.groupby("sale_year").size().items():
        actual = pd.read_parquet(export_dir, filters=[("sale_year", "==", int(year))])
        if len(actual) != expected:
            raise ValueError(f"Partition read-back count does not match for {year}")
    # Leading underscore keeps this metadata file out of Parquet dataset scans.
    (export_dir / "_manifest.json").write_text(json.dumps({
        "sold_rows": len(sold),
        "rows_by_year": {str(year): int(count) for year, count in sold.groupby("sale_year").size().items()},
    }, indent=2) + "\n")
    print(f"Exported {len(sold):,} sold listings to {export_dir}; read-back checks passed")


if __name__ == "__main__":
    main()
