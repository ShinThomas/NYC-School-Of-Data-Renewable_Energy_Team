"""All settings for the heat pump feasibility pipeline.

Edit this file, not the code, when:
  * a column name in a downloaded dataset differs from the guesses below
    (run `python -m hpf.inspect` to see the real names), or
  * you want to change an assumption (efficiencies, COPs, thresholds).

Column names are matched AFTER normalization: lowercase, every run of
non a-z/0-9 characters replaced by "_". Example:
  "Natural Gas Use (kBtu)"  ->  "natural_gas_use_kbtu"
Each key lists candidate names; the loader uses the first one it finds.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# downloads
SOCRATA = "https://data.cityofnewyork.us"
DATASETS = {
    "ll84_annual": {
        "url": f"{SOCRATA}/api/views/5zyy-y8am/rows.csv?accessType=DOWNLOAD",
        "file": "ll84_annual.csv",
        "about": "LL84 benchmarking, 2023 to present (one row per property per year)",
    },
    "ll84_monthly": {
        "url": f"{SOCRATA}/api/views/fvp3-gcb2/rows.csv?accessType=DOWNLOAD",
        "file": "ll84_monthly.csv",
        "about": "LL84 monthly electricity and gas use",
    },
    "ll87": {
        "url": f"{SOCRATA}/api/views/au6c-jqvf/rows.csv?accessType=DOWNLOAD",
        "file": "ll87.csv",
        "about": "LL87 energy audits (heating plant details)",
    },
    "pluto": {
        "url": (f"{SOCRATA}/resource/64uk-42ks.csv?$select=bbl,landmark,histdist,"
                "lotarea,bldgarea,numfloors,bldgclass,yearbuilt&$limit=2000000"),
        "file": "pluto.csv",
        "about": "PLUTO tax lots (selected columns only)",
    },
}

# column names
COLS = {
    "ll84_annual": {
        "property_id": ["property_id"],
        "bbl": ["nyc_borough_block_and_lot_bbl", "bbl", "borough_block_and_lot_bbl"],
        "year": ["calendar_year", "report_year", "year_ending"],
        "nta": ["neighborhood_tabulation_area_nta_2020", "nta", "nta_2020"],
        "use_type": ["largest_property_use_type"],
        "use_type_2": ["2nd_largest_property_use_type"],
        "use_type_2_gfa": ["2nd_largest_property_use_gross_floor_area_ft",
                           "2nd_largest_property_use_type_gross_floor_area_ft"],
        "gfa": ["property_gfa_self_reported_ft", "property_gfa_calculated_buildings_ft",
                "largest_property_use_type_gross_floor_area_ft"],
        "gas_kbtu": ["natural_gas_use_kbtu"],
        "oil2_kbtu": ["fuel_oil_2_use_kbtu"],
        "oil4_kbtu": ["fuel_oil_4_use_kbtu"],
        "steam_kbtu": ["district_steam_use_kbtu"],
        "elec_kwh": ["electricity_use_grid_purchase_kwh"],
    },
    "ll84_monthly": {
        "property_id": ["property_id"],
        "year": ["calendar_year"],
        "month": ["month"],
        "gas_kbtu": ["natural_gas_use_monthly_kbtu", "natural_gas_use_kbtu"],
        "elec_kbtu": ["electricity_use_grid_monthly_kbtu", "electricity_use_kbtu"],
    },
    "ll87": {
        "bbl": ["borough_block_lot_bbl", "bbl"],
        "audit_date": ["date_of_completion_for_level_2_audit", "submission_date"],
        "plant_type": ["heating_plant_type_1"],
        "plant_fuel": ["fuel_type_heating_plant_1"],
        "eff": ["rated_efficiency_heating_plant_1"],
        "eff_units": ["efficiency_units_heating_plant_1"],
        "install_year": ["approximate_year_installed_heating_plant_1"],
        "hvac_heat_type": ["heating_system_type_hvac_sys_1"],
    },
    "pluto": {
        "bbl": ["bbl"],
        "landmark": ["landmark"],
        "histdist": ["histdist"],
        "lotarea": ["lotarea"],
        "bldgarea": ["bldgarea"],
        "numfloors": ["numfloors"],
        "yearbuilt": ["yearbuilt"],
    },
}

# climate (VERIFY)
HDD_65F = 4_700          # NYC annual heating degree days, 65 degrees F base (check NOAA normals, Central Park)
T_DESIGN_F = 15          # winter design temperature degrees F (check ASHRAE 99% design condition)
T_BALANCE_F = 65         # indoor balance temperature degrees F
KBTU_PER_KWH = 3.412

# equipment
BOILER_EFF_DEFAULT = {"steam": 0.75, "hot_water": 0.80, "unknown": 0.78}
HEAT_PUMPS = {
    #           seasonal COP     COP on design day
    "ashp": {"scop": 2.7, "cop_cold": 1.9},   # air-source (cold-climate)
    "gshp": {"scop": 3.7, "cop_cold": 3.4},   # ground-source
}

# Share of gas that is space heating, used ONLY when monthly data is missing
SPACE_HEAT_SHARE_DEFAULT = {
    "multifamily": 0.65, "office": 0.80, "mixed_use": 0.60,
    "industrial": 0.40, "food_service": 0.20, "other": 0.70,
}
SUMMER_MONTHS = [6, 7, 8]
WINTER_MONTHS = [12, 1, 2]

# Monthly load factor (average kW / peak kW within a month) by building type
LOAD_FACTOR = {
    "multifamily": 0.55, "office": 0.50, "mixed_use": 0.50,
    "industrial": 0.60, "food_service": 0.55, "other": 0.50,
}
HOURS_PER_MONTH = 730

# building type groups
# Matched against LL84 "Largest Property Use Type" (case-insensitive substring)
TYPE_GROUPS = {
    "multifamily": ["multifamily", "residence hall", "senior living"],
    "office": ["office", "financial office", "bank branch"],
    "industrial": ["manufacturing", "industrial", "warehouse", "distribution center",
                   "self-storage", "data center"],
    "food_service": ["restaurant", "food service", "food sales", "supermarket",
                     "grocery", "bar/nightclub"],
}
MIXED_USE_MIN_SHARE = 0.20   # 2nd use >= 20% of floor area -> "mixed_use"

# feasibility rules
HEADROOM_OK = 1.1            # new winter peak / current summer peak
HEADROOM_MAJOR = 1.5
HEADROOM_MAX_VALID = 10      # above this, headroom comes from bad electricity data
MIN_SUMMER_KW = 10           # below this, summer electricity data is unreliable
MIN_OPEN_LOT_SQFT = 500
PRE_STEAM_YEAR = 1950