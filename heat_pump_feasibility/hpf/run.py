"""Run the full heat pump feasibility + price-of-switch pipeline.

Usage:
    python -m hpf.run
    python -m hpf.run --ll87 path/to/LL87_2019-2024.xlsx   # use a local LL87 file

Outputs (data/processed/):
    hp_feasibility_buildings.csv   one row per building (feasibility + price)
    hp_feasibility_by_type.csv     summary by building type and tier
    hp_price_by_type.csv           price summary by building type and tier
    hp_grid_by_nta.csv             added winter peak by neighborhood
    hp_grid_citywide.csv           citywide added peak, air-source vs ground-source
"""
import argparse

import numpy as np
import pandas as pd

from hpf import config
from hpf.calcs import current_peaks, heat_pump_load, split_space_heating
from hpf.load import load_boiler_permits, load_ll84_annual, load_ll84_monthly, load_ll87, load_pluto
from hpf.price import estimate_price
from hpf.tiers import assign_tiers

OUT_COLS = [
    "property_id", "bbl", "bin", "nta", "use_type", "building_type", "gfa", "unitsres",
    "fossil_kbtu", "space_heat_share", "space_split_method",
    "fuel_space_kbtu", "fuel_base_kbtu",
    "plant_type", "distribution_source", "distribution_used", "boiler_eff_used",
    "install_year", "boiler_permit", "last_permit_year",
    "heat_delivered_kbtu",
    "hp_kwh_ashp", "hp_kwh_gshp", "hp_peak_kw_ashp", "hp_peak_kw_gshp",
    "peak_now_summer_kw", "peak_now_winter_kw", "peak_method",
    "headroom_R_ashp", "headroom_R_gshp", "headroom_valid",
    "landmark_or_hist", "open_lot_sqft", "gshp_space_ok",
    "feasibility_tier", "tier_reason", "data_confidence",
    # price of switch
    "cost_basis", "units_priced", "units_estimated", "nonres_sqft_priced", "range_position", "price_drivers",
    "price_ashp_low", "price_ashp_mid", "price_ashp_high", "incentive_ashp",
    "boiler_due_soon", "avoided_boiler_credit", "price_ashp_net", "price_ashp_net_per_sqft", "price_ashp_net_is_zero",
    "price_gshp_low", "price_gshp_mid", "price_gshp_high", "incentive_gshp",
    "price_gshp_net", "price_gshp_net_per_sqft", "price_gshp_net_is_zero",
    "price_confidence",
]

MONTHLY_COLS = ["gas_summer_avg_kbtu", "elec_summer_max_kwh", "elec_winter_max_kwh",
                "gas_annual_monthly_kbtu", "monthly_year"]
LL87_COLS = ["audit_date", "plant_type", "plant_fuel", "distribution", "boiler_eff", "install_year"]
PLUTO_COLS = ["yearbuilt", "open_lot_sqft", "landmark_or_hist", "unitsres", "resarea", "bldgarea"]
PERMIT_COLS = ["boiler_permit", "permit_system", "last_permit_year"]
TEXT_COLS = {"plant_type", "plant_fuel", "distribution", "landmark_or_hist", "audit_date",
             "boiler_permit", "permit_system"}


def build(ll84=None, monthly=None, ll87=None, pluto=None, permits=None) -> pd.DataFrame:
    df = load_ll84_annual(ll84)
    print(f"LL84 annual: {len(df):,} properties")

    # Optional datasets: if a file is missing, skip it and fall back to defaults.
    optional = [
        ("LL84 monthly", load_ll84_monthly, monthly, "property_id", MONTHLY_COLS),
        ("LL87", load_ll87, ll87, "bbl", LL87_COLS),
        ("PLUTO", load_pluto, pluto, "bbl", PLUTO_COLS),
        ("Boiler permits", load_boiler_permits, permits, "bin", PERMIT_COLS),
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

    # heating system: LL87 first, then a permit that names steam or hot water
    from_permit = df["distribution"].isna() & df["permit_system"].isin(["steam", "hot_water"])
    df["distribution_source"] = np.select(
        [df["distribution"].notna(), from_permit], ["ll87", "permit"], default="none")
    df["distribution"] = df["distribution"].where(~from_permit, df["permit_system"])

    print(f"Join rates: monthly {df.gas_summer_avg_kbtu.notna().mean():.0%}, "
          f"LL87 {df.plant_type.notna().mean():.0%}, PLUTO {df.yearbuilt.notna().mean():.0%}, "
          f"boiler permit {df.boiler_permit.notna().mean():.0%}")

    df = split_space_heating(df)
    df = heat_pump_load(df)
    df = current_peaks(df)
    df = assign_tiers(df)
    df = estimate_price(df)
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
    price = (inc.groupby(["building_type", "feasibility_tier"])
                .agg(buildings=("bbl", "size"),
                     median_price_ashp_net=("price_ashp_net", "median"),
                     median_price_ashp_per_sqft=("price_ashp_net_per_sqft", "median"),
                     total_price_ashp_net_musd=("price_ashp_net", lambda s: s.sum() / 1e6),
                     median_price_gshp_net=("price_gshp_net", "median"),
                     total_price_gshp_net_musd=("price_gshp_net", lambda s: s.sum() / 1e6),
                     share_boiler_due_soon=("boiler_due_soon", "mean"))
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
                     "added_gwh_gshp": sub.hp_kwh_gshp.sum() / 1e6,
                     "total_price_ashp_net_busd": sub.price_ashp_net.sum() / 1e9})
    return {"by_type": by_type, "price": price, "by_nta": by_nta, "citywide": pd.DataFrame(rows)}


def main():
    ap = argparse.ArgumentParser()
    for k in ["ll84", "monthly", "ll87", "pluto", "permits"]:
        ap.add_argument(f"--{k}", default=None, help=f"path to {k} file (default: data/raw)")
    args = ap.parse_args()

    df = build(args.ll84, args.monthly, args.ll87, args.pluto, args.permits)
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    df[[c for c in OUT_COLS if c in df.columns]].to_csv(
        config.PROCESSED / "hp_feasibility_buildings.csv", index=False)
    s = summarize(df)
    s["by_type"].to_csv(config.PROCESSED / "hp_feasibility_by_type.csv", index=False)
    s["price"].to_csv(config.PROCESSED / "hp_price_by_type.csv", index=False)
    s["by_nta"].to_csv(config.PROCESSED / "hp_grid_by_nta.csv", index=False)
    s["citywide"].to_csv(config.PROCESSED / "hp_grid_citywide.csv", index=False)

    print("\nTier counts:\n", df.feasibility_tier.value_counts(dropna=False).sort_index())
    print("\nCitywide:\n", s["citywide"].round(1).to_string(index=False))
    p = df.price_ashp_net_per_sqft.dropna()
    print(f"\nPrice of switch (air-source, net): median ${p.median():,.2f}/sq ft, "
          f"middle 50% ${p.quantile(.25):,.2f} to ${p.quantile(.75):,.2f}/sq ft")
    print("Price confidence:", df.price_confidence.value_counts().to_dict())
    print(f"\nSaved to {config.PROCESSED}")


if __name__ == "__main__":
    main()
