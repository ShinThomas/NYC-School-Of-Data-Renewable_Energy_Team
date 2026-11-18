"""Load and clean each raw dataset into a tidy table keyed by BBL, BIN or property ID."""
from pathlib import Path

import numpy as np
import pandas as pd

from hpf import config
from hpf.utils import clean_bbl, clean_bin, norm, pick, to_num


def _read(key: str, path: Path | None = None) -> pd.DataFrame:
    """Read only the columns config needs, then normalize their names."""
    path = Path(path or config.RAW / config.DATASETS[key]["file"])
    wanted = {c for cands in config.COLS[key].values() for c in cands}
    if path.suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
        df.columns = [norm(c) for c in df.columns]
        return df[[c for c in df.columns if c in wanted]]
    header = pd.read_csv(path, nrows=0).columns
    keep = [c for c in header if norm(c) in wanted]
    df = pd.read_csv(path, usecols=keep, low_memory=False)
    df.columns = [norm(c) for c in df.columns]
    return df


# LL84 annual
def building_group(use: str, use2: str, gfa: float, gfa2: float) -> str:
    use_l = str(use).lower()
    if pd.notna(gfa2) and pd.notna(gfa) and gfa > 0 and gfa2 / gfa >= config.MIXED_USE_MIN_SHARE \
            and pd.notna(use2) and str(use2).strip():
        return "mixed_use"
    for group, words in config.TYPE_GROUPS.items():
        if any(w in use_l for w in words):
            return group
    return "other"


def load_ll84_annual(path=None) -> pd.DataFrame:
    raw = _read("ll84_annual", path)
    df = pick(raw, config.COLS["ll84_annual"], "ll84_annual",
              required=("property_id", "bbl", "use_type", "gas_kbtu", "elec_kwh", "gfa"))
    for c in ["gfa", "use_type_2_gfa", "gas_kbtu", "oil2_kbtu", "oil4_kbtu", "steam_kbtu", "elec_kwh", "units"]:
        df[c] = to_num(df[c])
    df["year"] = to_num(df["year"])
    df["bbl"] = clean_bbl(df["bbl"])
    df["bin"] = clean_bin(df["bin"])

    # one row per property: most recent year
    df = df.sort_values("year").drop_duplicates("property_id", keep="last")

    df["building_type"] = [
        building_group(u, u2, g, g2)
        for u, u2, g, g2 in zip(df.use_type, df.use_type_2, df.gfa, df.use_type_2_gfa)
    ]
    fossil = df[["gas_kbtu", "oil2_kbtu", "oil4_kbtu"]].fillna(0).sum(axis=1)
    df["fossil_kbtu"] = fossil
    df["mostly_steam"] = df["steam_kbtu"].fillna(0) > fossil
    return df


# LL84 monthly
def load_ll84_monthly(path=None) -> pd.DataFrame:
    """Per property, for its most recent complete year:
    summer average monthly gas, and the largest summer and winter monthly electricity.
    """
    raw = _read("ll84_monthly", path)
    m = pick(raw, config.COLS["ll84_monthly"], "ll84_monthly",
             required=("property_id", "month", "gas_kbtu"))
    m["gas_kbtu"] = to_num(m["gas_kbtu"])
    m["elec_kwh"] = to_num(m["elec_kbtu"]) / config.KBTU_PER_KWH

    # Month may be "Jan", "January", "1", or a full date; year is in calendar_year.
    month_txt = m["month"].astype(str).str.strip()
    as_date = pd.to_datetime(month_txt, format="mixed", errors="coerce")
    mo = pd.to_datetime(month_txt.str[:3], format="%b", errors="coerce").dt.month
    mo = mo.fillna(pd.to_numeric(month_txt, errors="coerce")).fillna(as_date.dt.month)
    yr = to_num(m["year"]).fillna(as_date.dt.year)
    ok = mo.notna() & yr.notna()
    m = m[ok].copy()
    m["yr"], m["mo"] = yr[ok].astype(int), mo[ok].astype(int)

    # most recent year with 12 months of gas data
    counts = m.dropna(subset=["gas_kbtu"]).groupby(["property_id", "yr"]).mo.nunique()
    full = counts[counts == 12].reset_index()
    best = full.sort_values("yr").drop_duplicates("property_id", keep="last")[["property_id", "yr"]]
    m = m.merge(best, on=["property_id", "yr"])

    summer = m[m.mo.isin(config.SUMMER_MONTHS)].groupby("property_id")
    winter = m[m.mo.isin(config.WINTER_MONTHS)].groupby("property_id")
    out = pd.DataFrame({
        "gas_summer_avg_kbtu": summer.gas_kbtu.mean(),
        "elec_summer_max_kwh": summer.elec_kwh.max(),
        "elec_winter_max_kwh": winter.elec_kwh.max(),
        "gas_annual_monthly_kbtu": m.groupby("property_id").gas_kbtu.sum(),
        "monthly_year": m.groupby("property_id").yr.first(),
    }).reset_index()
    return out


# LL87
def distribution_type(plant: str, hvac: str) -> str:
    p, h = str(plant).lower(), str(hvac).lower()
    if "district" in p or "utility" in p:
        return "district"
    if "steam" in p:
        return "steam"
    if "hot water" in p:
        return "hot_water"
    if any(w in h for w in ["furnace", "dx", "heat pump"]):
        return "ducted_or_dx"
    if "electric" in h:
        return "electric_resistance"
    return "unknown"


def load_ll87(path=None) -> pd.DataFrame:
    raw = _read("ll87", path)
    df = pick(raw, config.COLS["ll87"], "ll87", required=("bbl", "plant_type"))
    df["bbl"] = clean_bbl(df["bbl"])
    df["audit_date"] = pd.to_datetime(df["audit_date"], errors="coerce")
    df = df.dropna(subset=["bbl"]).sort_values("audit_date").drop_duplicates("bbl", keep="last")

    eff = to_num(df["eff"])
    eff = eff.where(eff <= 1, eff / 100)                 # 80 -> 0.80
    df["boiler_eff"] = eff.where(eff.between(0.5, 1.0))  # drop impossible values
    df["distribution"] = [distribution_type(p, h) for p, h in zip(df.plant_type, df.hvac_heat_type)]
    df["install_year"] = to_num(df["install_year"])
    return df[["bbl", "audit_date", "plant_type", "plant_fuel", "distribution",
               "boiler_eff", "install_year"]]


# PLUTO
def load_pluto(path=None) -> pd.DataFrame:
    raw = _read("pluto", path)
    df = pick(raw, config.COLS["pluto"], "pluto", required=("bbl",))
    df["bbl"] = clean_bbl(df["bbl"])
    for c in ["lotarea", "bldgarea", "numfloors", "yearbuilt", "unitsres", "resarea"]:
        df[c] = to_num(df[c])
    floors = df["numfloors"].where(df["numfloors"] > 0)
    footprint = df["bldgarea"] / floors
    df["open_lot_sqft"] = (df["lotarea"] - footprint).clip(lower=0)
    df["landmark_or_hist"] = df["landmark"].notna() | df["histdist"].notna()
    return df.dropna(subset=["bbl"]).drop_duplicates("bbl")[
        ["bbl", "yearbuilt", "open_lot_sqft", "landmark_or_hist", "unitsres", "resarea", "bldgarea"]]


# boiler permits
def load_boiler_permits(path=None) -> pd.DataFrame:
    """One row per BIN with a boiler-related DOB permit.

    Adds the permit's heating system label when a permit names it
    (steam vs hot water), and the latest permit year if that column exists.
    """
    raw = _read("boiler_permits", path)
    df = pick(raw, config.COLS["boiler_permits"], "boiler_permits", required=("bin",))
    df["bin"] = clean_bin(df["bin"])
    labels = (df["dob_now_systems"].fillna("").astype(str) + " "
              + df["bis_systems"].fillna("").astype(str)).str.lower()
    df["permit_system"] = np.select(
        [labels.str.contains("steam"), labels.str.contains("hot water")],
        ["steam", "hot_water"], default="boiler_unspecified")
    df["boiler_permit"] = True
    df["last_permit_year"] = to_num(df["last_permit_year"])
    return (df.dropna(subset=["bin"])
              .sort_values("last_permit_year")
              .drop_duplicates("bin", keep="last")
              [["bin", "boiler_permit", "permit_system", "last_permit_year"]])
