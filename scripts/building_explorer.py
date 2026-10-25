
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "data" / "local_law_buildings.csv", low_memory=False)

columns = {
    "Calendar Year": "year",
    "NYC Building Identification Number (BIN)": "bin",
    "NYC Borough, Block and Lot (BBL)": "bbl",
    "Borough": "borough",
    "Year Built": "year_built",
    "Primary Property Type - Self Selected": "property_type",
    "Property GFA - Calculated (Buildings) (ft²)": "floor_area",
    "Electricity Use - Grid Purchase (kWh)": "grid_kwh"
}

grid = df[list(columns)].rename(columns=columns).copy()

for col in ["year", "year_built", "floor_area", "grid_kwh"]:
    grid[col] = pd.to_numeric(
        grid[col].astype("string").str.replace(",", "", regex=False),
        errors="coerce"
    )

grid = grid[(grid["year"] == 2024) & (grid["grid_kwh"] > 0)].copy()

grid["electricity_intensity"] = grid["grid_kwh"] / grid["floor_area"]
grid.loc[grid["floor_area"] <= 0, "electricity_intensity"] = pd.NA

grid["suspicious_intensity"] = (
    (grid["floor_area"] < 1000) |
    (grid["electricity_intensity"] > 200)
).fillna(True)

grid["grid_emissions_tons"] = grid["grid_kwh"] * 0.0003927

grid["single_bin"] = grid["bin"].astype("string").str.fullmatch(
    r"\d{7}", na=False
)

valid = grid[~grid["suspicious_intensity"]].copy()

type_summary = (
    grid.groupby("property_type")["grid_kwh"]
    .sum()
    .sort_values(ascending=False)
)

intensity_summary = (
    valid.groupby("property_type")["electricity_intensity"]
    .agg(["count", "median"])
    .query("count >= 10")
    .sort_values("median", ascending=False)
)

print("2024 records:", len(grid))
print("Records with usable intensity:", len(valid))
print("Records with one BIN:", grid["single_bin"].sum())

print("\nTop property types by electricity consumption:")
print((type_summary.head(10) / 1_000_000).round(1))

print("\nHighest median electricity intensity by property type:")
print(intensity_summary.head(10).round(2))

print("\nTop 10 records by estimated grid emissions:")
print(
    grid.nlargest(10, "grid_emissions_tons")[
        ["bin", "borough", "property_type", "grid_emissions_tons"]
    ].to_string(index=False)
)

output = ROOT / "results"
output.mkdir(exist_ok=True)

grid.to_csv(output / "building_characteristics_2024.csv", index=False)

print("\nSaved building_characteristics_2024.csv")