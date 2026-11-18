"""Price of switch: estimated cost to convert a building's heating to heat pumps.

For each building and heat pump type (air-source "ashp", ground-source "gshp"):

    gross cost  = residential units x $/unit  +  non-residential area x $/sq ft
    position    = where the building sits in the (low, high) cost range, 0 to 1,
                  shifted by steam, electrical upgrade, landmark status, mixed use
    cost_mid    = low + position x (high - low)
    incentive   = $/unit (multifamily) + $/MMBtu of heating fuel (commercial),
                  capped at a share of cost
    boiler credit = cost of a new boiler, if the boiler is due within a few years
    net price   = cost_mid - incentive - boiler credit

All numbers come from hpf/config.py. Excluded buildings (no on-site fossil heating) get no price.
"""
import numpy as np
import pandas as pd

from hpf import config

HP_TYPES = ("ashp", "gshp")


def _range_position(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Position in the cost range (0 = low end, 1 = high end) and the reasons for it."""
    shift = config.RANGE_POSITION_SHIFT
    R = df["headroom_R_ashp"].where(df.get("headroom_valid", True))
    flags = {
        "steam distribution": df["distribution_used"].isin(["steam", "steam_assumed"]),
        "hot water or ducted": df["distribution_used"].isin(["hot_water", "ducted_or_dx"]),
        "major electrical upgrade likely": R > config.HEADROOM_MAJOR,
        "electrical upgrade possible": (R > config.HEADROOM_OK) & (R <= config.HEADROOM_MAJOR),
        "landmark or historic district": df["landmark_or_hist"].fillna(False).astype(bool),
        "mixed use": df["building_type"] == "mixed_use",
    }
    flags = {k: v.fillna(False).astype(bool) for k, v in flags.items()}
    pos = pd.Series(config.RANGE_POSITION_START, index=df.index, dtype=float)
    for k, v in flags.items():
        pos += v.astype(float) * shift[k]
    drivers = [
        "; ".join(k for k, v in flags.items() if v.loc[i]) or "typical"
        for i in df.index
    ]
    return pos.clip(0, 1), pd.Series(drivers, index=df.index)


def _split_areas(df: pd.DataFrame) -> pd.DataFrame:
    """Residential units priced per unit; everything else priced per sq ft.

    Unit counts are checked against floor area. A count that implies apartments
    smaller than MIN_SQFT_PER_UNIT (often a PLUTO count for a whole multi-building lot)
    or larger than MAX_SQFT_PER_UNIT (too few units for the floor area)
    is replaced by an estimate: residential area / AVG_SQFT_PER_UNIT.
    """
    out = pd.DataFrame(index=df.index)
    gfa = df["gfa"]
    res_type = df["building_type"].isin(["multifamily", "mixed_use"])
    res_share = (df["resarea"] / df["bldgarea"]).clip(0, 1)
    res_area = pd.Series(np.where(df["building_type"] == "mixed_use",
                                  gfa * res_share.fillna(0.5), gfa), index=df.index).where(res_type)

    # unit count: LL84 (matches the property's floor area) first, PLUTO as fallback
    reported = df.get("units", pd.Series(np.nan, index=df.index)).combine_first(df["unitsres"])
    reported = reported.where(reported >= 2)
    plausible = (res_area / reported).between(config.MIN_SQFT_PER_UNIT, config.MAX_SQFT_PER_UNIT)
    estimated = (res_area / config.AVG_SQFT_PER_UNIT).round()
    units = reported.where(plausible, estimated).where(res_type)
    units = units.where(units >= 2)
    out["units_priced"] = units.fillna(0)
    out["units_estimated"] = res_type & ~(reported.notna() & plausible) & (out["units_priced"] > 0)

    nonres_area = np.where(out["units_priced"] > 0, gfa - res_area.fillna(0), gfa)
    out["nonres_sqft_priced"] = pd.Series(nonres_area, index=df.index).clip(lower=0)
    out["mf_size"] = np.where(out["units_priced"] >= config.MF_LARGE_MIN_UNITS, "large", "small")

    # how the cost was estimated
    unit_label = np.where(out["units_estimated"], "per_unit_estimated", "per_unit")
    basis = np.select(
        [(out["units_priced"] > 0) & (out["nonres_sqft_priced"] > 0),
         out["units_priced"] > 0,
         df["building_type"] == "office"],
        [pd.Series(unit_label, index=df.index) + " + per_sqft", unit_label, "per_sqft"],
        default="per_sqft_office_proxy",
    )
    out["cost_basis"] = basis
    return out


def _boiler_credit(df: pd.DataFrame) -> pd.Series:
    """Cost of a new boiler, credited when the boiler is due within the window."""
    last_install = df["install_year"].combine_first(df.get("last_permit_year", pd.Series(np.nan, index=df.index)))
    due = (last_install + config.BOILER_LIFESPAN_YEARS
           <= config.CURRENT_YEAR + config.BOILER_DUE_WITHIN_YEARS)
    return pd.Series(np.where(due, config.BOILER_COST_PER_SQFT * df["gfa"], 0.0), index=df.index), due


def estimate_price(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    areas = _split_areas(df)
    df = df.join(areas)
    df["range_position"], df["price_drivers"] = _range_position(df)
    credit, due = _boiler_credit(df)
    df["boiler_due_soon"] = due
    df["avoided_boiler_credit"] = credit

    mmbtu_space = df["fuel_space_kbtu"] / 1000
    nonres_share = (df["nonres_sqft_priced"] / df["gfa"]).clip(0, 1).fillna(1)

    for hp in HP_TYPES:
        u_lo = df["mf_size"].map(lambda s: config.COST_PER_UNIT[s][hp][0])
        u_hi = df["mf_size"].map(lambda s: config.COST_PER_UNIT[s][hp][1])
        f_lo, f_hi = config.COST_PER_SQFT[hp]
        low = df["units_priced"] * u_lo + df["nonres_sqft_priced"] * f_lo
        high = df["units_priced"] * u_hi + df["nonres_sqft_priced"] * f_hi
        mid = low + df["range_position"] * (high - low)

        incentive = (df["units_priced"] * config.INCENTIVE_MF_PER_UNIT
                     + mmbtu_space * nonres_share * config.INCENTIVE_COMMERCIAL_PER_MMBTU)
        incentive = np.minimum(incentive, config.INCENTIVE_CAP_SHARE * mid)

        net = (mid - incentive - df["avoided_boiler_credit"]).clip(lower=0)

        df[f"price_{hp}_low"] = low
        df[f"price_{hp}_high"] = high
        df[f"price_{hp}_mid"] = mid
        df[f"incentive_{hp}"] = incentive
        df[f"price_{hp}_net"] = net
        df[f"price_{hp}_net_per_sqft"] = net / df["gfa"].where(df["gfa"] > 0)
        # incentives + boiler credit covered the whole cost: net price was floored at $0
        df[f"price_{hp}_net_is_zero"] = (net <= 0).astype("boolean")

    # no price for buildings with nothing to replace
    excluded = df["feasibility_tier"].isna()
    flag_cols = [c for c in df.columns if c.endswith("_net_is_zero")]
    price_cols = [c for c in df.columns if c.startswith(("price_", "incentive_"))
                  and c != "price_drivers" and c not in flag_cols] + ["avoided_boiler_credit"]
    df.loc[excluded, price_cols] = np.nan
    df.loc[excluded, flag_cols] = pd.NA
    df.loc[excluded, "price_drivers"] = "excluded: no on-site fossil heating"

    # confidence in the price (separate from feasibility confidence)
    good_basis = df["cost_basis"].isin(["per_unit", "per_unit + per_sqft", "per_sqft"])  # estimated units = weaker
    known_system = df["distribution_used"].isin(["steam", "hot_water", "ducted_or_dx"])
    n = good_basis.astype(int) + known_system.astype(int)
    df["price_confidence"] = np.select([n == 2, n == 1], ["high", "medium"], default="low")
    df.loc[excluded, "price_confidence"] = np.nan
    return df
