
import pandas as pd
import numpy as np
from pathlib import Path


INPUT_FILE = "data/LL84_Monthly.csv"
OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GAS_EFFICIENCY = 0.85
HEAT_PUMP_COP = 2.5

# kg CO2e per kBtu
GAS_EF = 0.0664
ELECTRIC_EF = 0.0282

KBTU_PER_KWH = 3.412
df = pd.read_csv(INPUT_FILE, low_memory=False)

print("Original shape:", df.shape)
print("\nAvailable years:")
print(df["Calendar Year"].value_counts().sort_index())

# Keep relevant columns
df = df[[
    "Calendar Year",
    "Month",
    "Property Id",
    "Property Name",
    "Parent Property ID",
    "Parent Property Name",
    "Natural Gas Use - Monthly (kBtu)"
]].copy()

df.columns = [
    "year",
    "month",
    "property_id",
    "property_name",
    "parent_property_id",
    "parent_property_name",
    "gas_kbtu"
]


df["year"] = pd.to_numeric(df["year"], errors="coerce")

df["gas_kbtu"] = pd.to_numeric(
    df["gas_kbtu"].astype(str)
      .str.replace(",", "", regex=False),
    errors="coerce"
)

# Parse months
month_names = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12
}

month_text = df["month"].astype(str).str.strip()

df["month_num"] = pd.to_numeric(
    month_text, errors="coerce"
)

missing = df["month_num"].isna()

df.loc[missing, "month_num"] = (
    month_text[missing]
    .str.lower()
    .str[:3]
    .map(month_names)
)

missing = df["month_num"].isna()

df.loc[missing, "month_num"] = (
    pd.to_datetime(
        month_text[missing],
        errors="coerce"
    ).dt.month
)

print("\nUnparsed months:", df["month_num"].isna().sum())

# Select latest year with all 12 months represented
year_counts = df.groupby("year")["month_num"].nunique()
complete_years = year_counts[year_counts == 12].index

if len(complete_years) == 0:
    raise ValueError("No year contains all 12 months.")

latest_year = int(max(complete_years))
df = df[df["year"] == latest_year].copy()

print("Selected year:", latest_year)

# Examine missing natural gas records
print("Rows before gas filtering:", len(df))
print("Missing gas values:", df["gas_kbtu"].isna().sum())

df = df.dropna(subset=[
    "property_id", "month_num", "gas_kbtu"
])

df = df[df["gas_kbtu"] >= 0].copy()
duplicates = df.duplicated(
    ["property_id", "month_num"],
    keep=False
)

print("\nDuplicate property-month rows:", duplicates.sum())

# Exclude ambiguous duplicates
df = df[~duplicates].copy()

# Keep only properties with all 12 months
month_counts = df.groupby("property_id")["month_num"].nunique()
valid_ids = month_counts[month_counts == 12].index

df = df[df["property_id"].isin(valid_ids)].copy()

print("Properties with complete 12-month records:",
      df["property_id"].nunique())

relationships = df[[
    "property_id",
    "property_name",
    "parent_property_id",
    "parent_property_name"
]].drop_duplicates()

print("\nProperties with parent IDs:",
      relationships[
          "parent_property_id"
      ].notna().sum())

print("\nSample parent-child relationships:")
print(
    relationships[
        relationships["parent_property_id"].notna()
    ].head(10).to_string(index=False)
)

relationships.to_csv(
    OUTPUT_DIR / "property_relationships.csv",
    index=False
)

# Summer months approximate non-heating gas demand
summer = df[df["month_num"].isin([6, 7, 8])]

baseline = (
    summer.groupby("property_id")["gas_kbtu"]
    .mean()
    .rename("monthly_baseline_kbtu")
)

df = df.join(baseline, on="property_id")

# Gas consumption above summer baseline
df["heating_gas_kbtu"] = (
    df["gas_kbtu"] - df["monthly_baseline_kbtu"]
).clip(lower=0)

# Aggregate to property level
buildings = df.groupby("property_id").agg(
    property_name=("property_name", "first"),
    parent_property_id=("parent_property_id", "first"),
    parent_property_name=("parent_property_name", "first"),
    annual_gas_kbtu=("gas_kbtu", "sum"),
    heating_gas_kbtu=("heating_gas_kbtu", "sum"),
    monthly_baseline_kbtu=("monthly_baseline_kbtu", "first")
).reset_index()

buildings = buildings[
    buildings["annual_gas_kbtu"] > 0
].copy()

buildings["heating_share_pct"] = (
    100 * buildings["heating_gas_kbtu"]
    / buildings["annual_gas_kbtu"]
)

# Useful heat delivered by existing gas system
buildings["heating_demand_kbtu"] = (
    buildings["heating_gas_kbtu"] * GAS_EFFICIENCY
)

# Heat pump electricity consumption
buildings["hp_electricity_kbtu"] = (
    buildings["heating_demand_kbtu"] / HEAT_PUMP_COP
)

buildings["hp_electricity_kwh"] = (
    buildings["hp_electricity_kbtu"] / KBTU_PER_KWH
)

# Natural gas emissions avoided
buildings["gas_emissions_kg"] = (
    buildings["heating_gas_kbtu"] * GAS_EF
)

# New heat pump electricity emissions
buildings["hp_emissions_kg"] = (
    buildings["hp_electricity_kbtu"] * ELECTRIC_EF
)

# Net emissions saved
buildings["net_saved_kg"] = (
    buildings["gas_emissions_kg"]
    - buildings["hp_emissions_kg"]
)

buildings["net_saved_tons"] = (
    buildings["net_saved_kg"] / 1000
)

buildings["reduction_pct"] = np.where(
    buildings["gas_emissions_kg"] > 0,
    100 * buildings["net_saved_kg"]
    / buildings["gas_emissions_kg"],
    np.nan
)

print("\n======================================")
print("HEAT PUMP EMISSIONS SAVINGS FINDINGS")
print("======================================")

print("Year:", latest_year)
print("Properties analyzed:", len(buildings))

print("Total annual emissions saved (tons):",
      round(buildings["net_saved_tons"].sum(), 2))

print("Median annual savings per property (tons):",
      round(buildings["net_saved_tons"].median(), 2))

print("Total additional electricity (MWh):",
      round(buildings["hp_electricity_kwh"].sum() / 1000, 2))

print("Median heating share (%):",
      round(buildings["heating_share_pct"].median(), 2))

print("\nSavings distribution:")
print(
    buildings["net_saved_tons"].describe(
        percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    )
)

print("\nHeating share distribution:")
print(
    buildings["heating_share_pct"].describe(
        percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
    )
)

top10 = buildings.nlargest(10, "net_saved_tons")

print("\nTop 10 properties by emissions savings:")

print(top10[[
    "property_id",
    "property_name",
    "annual_gas_kbtu",
    "heating_gas_kbtu",
    "hp_electricity_kwh",
    "net_saved_tons"
]].to_string(index=False))

top10_share = (
    100 * top10["net_saved_tons"].sum()
    / buildings["net_saved_tons"].sum()
)

print("\nTop 10 share of total savings (%):",
      round(top10_share, 2))

print("\nSensitivity analysis by heat pump COP:")

sensitivity = []

for cop in [2.0, 2.5, 3.0, 3.5]:
    hp_kbtu = buildings["heating_demand_kbtu"] / cop

    hp_emissions = hp_kbtu * ELECTRIC_EF

    savings = (
        buildings["gas_emissions_kg"] - hp_emissions
    )

    sensitivity.append({
        "COP": cop,
        "Total Savings (tons)": savings.sum() / 1000,
        "Additional Electricity (MWh)":
            (hp_kbtu / KBTU_PER_KWH).sum() / 1000
    })

sensitivity_df = pd.DataFrame(sensitivity)

print(sensitivity_df.to_string(index=False))


buildings.to_csv(
    OUTPUT_DIR / "heat_pump_emissions_savings.csv",
    index=False
)

top10.to_csv(
    OUTPUT_DIR / "top10_heat_pump_candidates.csv",
    index=False
)

sensitivity_df.to_csv(
    OUTPUT_DIR / "cop_sensitivity.csv",
    index=False
)

annual = pd.read_csv(
    "data/LL84_Annual.csv",
    low_memory=False
)

print("\nAnnual LL84 columns:")
print(annual.columns.tolist())

# Identify columns despite differences in naming
def find_column(df, candidates):
    normalized = {
        col.lower().strip().replace(" ", "").replace("_", ""): col
        for col in df.columns
    }

    for candidate in candidates:
        key = candidate.lower().strip().replace(" ", "").replace("_", "")
        if key in normalized:
            return normalized[key]

    return None

id_col = find_column(annual, [
    "Property Id", "Property ID", "PropertyID"
])

year_col = find_column(annual, [
    "Calendar Year", "Reporting Year", "Year"
])

type_col = find_column(annual, [
    "Primary Property Type - Self Selected",
    "Primary Property Type",
    "PrimaryPropertyType"
])

if id_col is None or type_col is None or year_col is None:
    raise ValueError(
        "Could not identify required annual LL84 columns. "
        "Check the printed column names."
    )

# Keep 2024 to match monthly analysis
annual[year_col] = pd.to_numeric(
    annual[year_col], errors="coerce"
)

annual = annual[
    annual[year_col] == latest_year
].copy()

annual = annual[[id_col, type_col]].copy()

annual.columns = ["property_id", "building_type"]

# Standardize IDs
annual["property_id"] = (
    annual["property_id"].astype(str).str.strip()
)

buildings["property_id"] = (
    buildings["property_id"].astype(str).str.strip()
)

# Check for duplicate property IDs
print("\nDuplicate annual property IDs:",
      annual["property_id"].duplicated().sum())

annual = annual.drop_duplicates(
    subset="property_id", keep="first"
)


combined = buildings.merge(
    annual,
    on="property_id",
    how="left",
    validate="one_to_one"
)

print("\nProperties with building type:",
      combined["building_type"].notna().sum())

print("Properties without building type:",
      combined["building_type"].isna().sum())

combined["building_type"] = (
    combined["building_type"].fillna("Unknown")
)


category_results = combined.groupby(
    "building_type"
).agg(
    property_count=("property_id", "nunique"),
    total_saved_tons=("net_saved_tons", "sum"),
    median_saved_tons=("net_saved_tons", "median"),
    mean_saved_tons=("net_saved_tons", "mean"),
    electricity_mwh=("hp_electricity_kwh",
                     lambda x: x.sum() / 1000),
    median_heating_share=("heating_share_pct", "median")
).reset_index()

category_results["share_of_total_pct"] = (
    100 * category_results["total_saved_tons"]
    / combined["net_saved_tons"].sum()
)

category_results = category_results.sort_values(
    "total_saved_tons", ascending=False
)


print("\n====================================")
print("EMISSIONS SAVINGS BY BUILDING TYPE")
print("====================================")

print(category_results.head(15).round(2).to_string(index=False))

print("\nTop 5 building types by total emissions savings:")
print(category_results[[
    "building_type",
    "property_count",
    "total_saved_tons",
    "share_of_total_pct"
]].head(5).round(2).to_string(index=False))

print("\nTop 5 building types by median savings:")

# Exclude tiny groups to avoid misleading comparisons
eligible = category_results[
    category_results["property_count"] >= 30
]

print(
    eligible.nlargest(5, "median_saved_tons")[[
        "building_type",
        "property_count",
        "median_saved_tons"
    ]].round(2).to_string(index=False)
)


combined.to_csv(
    OUTPUT_DIR / "combined_property_emissions.csv",
    index=False
)

category_results.to_csv(
    OUTPUT_DIR / "emissions_by_building_type.csv",
    index=False
)

print("\nCategory analysis complete.")
