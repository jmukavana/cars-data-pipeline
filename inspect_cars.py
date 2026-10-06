from pathlib import Path

import pandas as pd
from pandas.core import missing

csv_files= sorted(
    Path("data/raw").glob("*.csv")
)


if len(csv_files) !=1:
    raise ValueError(
        f"Expected exactly 1 csv file. Got {len(csv_files)}"
        "Keep only the intended input csv in this folder"
    )


file_path = csv_files[0]


df = pd.read_csv(file_path,low_memory=False)


print(f"\n File: {file_path.name}")
print(f"\n Rows: {df.shape[0]}")
print(f"\n Columns: {df.columns}")

# inspect column name and inferred types

print("\n Columns an data types ...")
print(df.dtypes.to_string())


print("\n  First 5 records: first ten columns ...")
print(df.iloc[:5,:10].to_string(index=False))


# count missing values by columns
missing = df.isna().sum()

missing_report =pd.DataFrame({
    "missing_count":missing,
    "missing_percent": df.isna().mean().mul(100).round(2),
})

print(" \n  Columns with missing values .. ")
print(
    missing_report.loc[missing_report["missing_count"]>0]
    .sort_values("missing_count", ascending=False)
    .to_string()
)

print(f"\n Count exact duplicate rows: {df.duplicated().sum():,}")

print("\n  Numeric summary...")
print(df.describe().T.to_string())


memory_mb = df.memory_usage(deep=True).sum() / 1024**2
print(f"\n  Dataframe memory usage: {memory_mb:.2f} MB")