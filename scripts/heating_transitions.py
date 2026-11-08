import pandas as pd

dob_now = pd.read_csv("data/dob_now.csv", low_memory=False)
descriptions = dob_now["Job Description"].fillna("")

heat_pumps = dob_now[
    descriptions.str.contains("heat pump", case=False, na=False)
].copy()

natural_gas = dob_now[
    descriptions.str.contains(
        "natural gas|gas boiler|gas-fired|gas fired|gas furnace",
        case=False,
        na=False
    )
].copy()

#possible gas -> heat pump conversions
gas_to_heat_pump = heat_pumps[
    heat_pumps["Job Description"].str.contains(
        "replace.*gas.*with.*heat pump|"
        "replacing.*gas.*with.*heat pump|"
        "gas.*replaced.*with.*heat pump|"
        "remove.*gas.*heat pump|"
        "removal.*gas.*heat pump|"
        "gas.*removed.*heat pump|"
        "existing gas boiler.*heat pump|"
        "existing gas furnace.*heat pump|"
        "existing boiler.*gas piping",
        case=False,
        na=False,
        regex=True
    )
].copy()

#possible gas -> gas replacements
gas_to_gas = natural_gas[
    natural_gas["Job Description"].str.contains(
        "replacement gas-fired boiler|"
        "replace gas boiler|"
        "gas boiler replacement|"
        "replacement of gas-fired|"
        "replace existing gas fired|"
        "replace existing gas-fired|"
        "gas fired domestic hot water heaters with new domestic gas fired",
        case=False,
        na=False
    )
].copy()

#exclude gas-fired oven replacements
gas_to_gas = gas_to_gas[
    ~gas_to_gas["Job Description"].str.contains(
        "gas-fired oven|gas fired oven",
        case=False,
        na=False
    )
].copy()

gas_to_heat_pump = gas_to_heat_pump.drop_duplicates(
    subset=["Bin", "Job Description"]
).copy()

gas_to_gas = gas_to_gas.drop_duplicates(
    subset=["Bin", "Job Description"]
).copy()

#extract permit year
date_format = "%Y %b %d %I:%M:%S %p"

gas_to_heat_pump["Year"] = pd.to_datetime(
    gas_to_heat_pump["Issued Date"],
    format=date_format,
    errors="coerce"
).dt.year

gas_to_gas["Year"] = pd.to_datetime(
    gas_to_gas["Issued Date"],
    format=date_format,
    errors="coerce"
).dt.year

columns = [
    "Bin",
    "BBL",
    "Job Filing Number",
    "Issued Date",
    "Year",
    "Job Description"
]

gas_to_heat_pump[columns].to_csv(
    "results/gas_to_heat_pump_candidates.csv",
    index=False
)

gas_to_gas[columns].to_csv(
    "results/gas_to_gas_candidates.csv",
    index=False
)

#candidates by year
heat_pump_years = gas_to_heat_pump.groupby("Year").size()
gas_years = gas_to_gas.groupby("Year").size()

comparison = pd.DataFrame({
    "Gas to Heat Pump": heat_pump_years,
    "Gas to Gas": gas_years
}).fillna(0).astype(int)

#share of heat pump candidates
comparison["Total Candidates"] = (
    comparison["Gas to Heat Pump"] + comparison["Gas to Gas"]
)

comparison["Heat Pump Share (%)"] = (
    comparison["Gas to Heat Pump"]
    / comparison["Total Candidates"].replace(0, float("nan"))
    * 100
).round(1)

comparison.to_csv("results/heating_transition_by_year.csv")


print("\nHEATING TRANSITION ANALYSIS")
print("---------------------------")

print("Total DOB NOW permits:", len(dob_now))
print("Heat pump permits:", len(heat_pumps))
print("Natural gas permits:", len(natural_gas))
w
print("Possible gas-to-heat-pump candidates:", len(gas_to_heat_pump))
print("Possible gas-to-gas candidates:", len(gas_to_gas))

print("\nHeating transition candidates by year:")
print(comparison.to_string())

print("\nSaved files:")
print("results/gas_to_heat_pump_candidates.csv")
print("results/gas_to_gas_candidates.csv")
print("results/heating_transition_by_year.csv")
