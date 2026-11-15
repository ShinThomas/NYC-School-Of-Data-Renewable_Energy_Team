"""Run the full heat pump feasibility pipeline.

Usage:
    python -m hpf.run
    python -m hpf.run --ll87 path/to/LL87_2019-2024.xlsx   # use a local LL87 file

Outputs (data/processed/):
    hp_feasibility_buildings.csv   one row per building
    hp_feasibility_by_type.csv     summary by building type and tier
    hp_grid_by_nta.csv             added winter peak by neighborhood
    hp_grid_citywide.csv           citywide added peak, air-source vs ground-source
"""
import argparse

import pandas as pd

from hpf import config
from hpf.calcs import current_peaks, heat_pump_load, split_space_heating
from hpf.load import load_ll84_annual, load_ll84_monthly, load_ll87, load_pluto
from hpf.tiers import assign_tiers

OUT_COLS = [
    "property_id", "bbl", "nta", "use_type", "building_type", "gfa",
    "fossil_kbtu", "space_heat_share", "space_split_method",
    "fuel_space_kbtu", "fuel_base_kbtu",
    "plant_type", "distribution_used", "boiler_eff_used", "install_year",
    "heat_delivered_kbtu",
    "hp_kwh_ashp", "hp_kwh_gshp", "hp_peak_kw_ashp", "hp_peak_kw_gshp",
    "peak_now_summer_kw", "peak_now_winter_kw", "peak_method",
    "headroom_R_ashp", "headroom_R_gshp",
    "landmark_or_hist", "open_lot_sqft", "gshp_space_ok",
    "feasibility_tier", "tier_reason", "data_confidence",
]


MONTHLY_COLS = ["gas_summer_avg_kbtu", "elec_summer_max_kwh", "elec_winter_max_kwh",
                "gas_annual_monthly_kbtu", "monthly_year"]
LL87_COLS = ["audit_date", "plant_type", "plant_fuel", "distribution", "boiler_eff", "install_year"]
PLUTO_COLS = ["yearbuilt", "open_lot_sqft", "landmark_or_hist"]
TEXT_COLS = {"plant_type", "plant_fuel", "distribution", "landmark_or_hist", "audit_date"}


def build(ll84=None, monthly=None, ll87=None, pluto=None) -> pd.DataFrame:
    df = load_ll84_annual(ll84)
    print(f"LL84 annual: {len(df):,} properties")

    optional = [
        ("LL84 monthly", load_ll84_monthly, monthly, "property_id", MONTHLY_COLS),
        ("LL87", load_ll87, ll87, "bbl", LL87_COLS),
        ("PLUTO", load_pluto, pluto, "bbl", PLUTO_COLS),
    ]
    for name, loader, path, key, cols in optional:
        try:
            extra = loader(path)
            print(f"{name}: {len(extra):,} rows")
            df = df.merge(extra, on=key, how="left")
        except FileNotFoundError:
            print(f"{name}: file not found, skipping (defaults will be used)")
            for c in cols:
                df[c] = pd.NA if c in TEXT_COLS else float("nan")
    print(f"Join rates: monthly {df.gas_summer_avg_kbtu.notna().mean():.0%}, "
          f"LL87 {df.plant_type.notna().mean():.0%}, PLUTO {df.yearbuilt.notna().mean():.0%}")

    df = split_space_heating(df)
    df = heat_pump_load(df)
    df = current_peaks(df)
    df = assign_tiers(df)
    return df


def summarize(df: pd.DataFrame) -> dict:
    inc = df[df.feasibility_tier.notna()]
    by_type = (inc.groupby(["building_type", "feasibility_tier"])
                  .agg(buildings=("bbl", "size"),
                       floor_area_sqft=("gfa", "sum"),
                       hp_kwh_ashp=("hp_kwh_ashp", "sum"),
                       hp_peak_mw_ashp=("hp_peak_kw_ashp", lambda s: s.sum() / 1000),
                       hp_peak_mw_gshp=("hp_peak_kw_gshp", lambda s: s.sum() / 1000),
                       median_headroom_R=("headroom_R_ashp", "median"))
                  .reset_index())
    by_nta = (inc.groupby("nta")
                 .agg(buildings=("bbl", "size"),
                      added_peak_mw_ashp=("hp_peak_kw_ashp", lambda s: s.sum() / 1000),
                      added_peak_mw_gshp=("hp_peak_kw_gshp", lambda s: s.sum() / 1000),
                      current_winter_peak_mw=("peak_now_winter_kw", lambda s: s.sum() / 1000))
                 .reset_index()
                 .sort_values("added_peak_mw_ashp", ascending=False))
    rows = []
    for label, sub in [("all included", inc), ("tiers 1-2", inc[inc.feasibility_tier <= 2])]:
        rows.append({"scope": label, "buildings": len(sub),
                     "added_peak_mw_ashp": sub.hp_peak_kw_ashp.sum() / 1000,
                     "added_peak_mw_gshp": sub.hp_peak_kw_gshp.sum() / 1000,
                     "added_gwh_ashp": sub.hp_kwh_ashp.sum() / 1e6,
                     "added_gwh_gshp": sub.hp_kwh_gshp.sum() / 1e6})
    return {"by_type": by_type, "by_nta": by_nta, "citywide": pd.DataFrame(rows)}


def main():
    ap = argparse.ArgumentParser()
    for k in ["ll84", "monthly", "ll87", "pluto"]:
        ap.add_argument(f"--{k}", default=None, help=f"path to {k} file (default: data/raw)")
    args = ap.parse_args()

    df = build(args.ll84, args.monthly, args.ll87, args.pluto)
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    df[[c for c in OUT_COLS if c in df.columns]].to_csv(
        config.PROCESSED / "hp_feasibility_buildings.csv", index=False)
    s = summarize(df)
    s["by_type"].to_csv(config.PROCESSED / "hp_feasibility_by_type.csv", index=False)
    s["by_nta"].to_csv(config.PROCESSED / "hp_grid_by_nta.csv", index=False)
    s["citywide"].to_csv(config.PROCESSED / "hp_grid_citywide.csv", index=False)

    print("\nTier counts:\n", df.feasibility_tier.value_counts(dropna=False).sort_index())
    print("\nCitywide added peak:\n", s["citywide"].round(1).to_string(index=False))
    print(f"\nSaved to {config.PROCESSED}")


if __name__ == "__main__":
    main()
