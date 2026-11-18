"""Rule-based feasibility tiers. Edit thresholds in config.py.

Tier 1 (easy):      no hard factors and no moderate factors
Tier 2 (moderate):  one hard factor, or only moderate factors
Tier 3 (hard):      two or more hard factors
Excluded:           no fossil heating to replace (district steam, all-electric)

Unknowns (heating system not in LL87, unreliable headroom) do not lower the tier.
They lower data_confidence instead, so "we don't know" stays separate from "this is hard".
"""
import numpy as np
import pandas as pd

from hpf import config


def assign_tiers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # distribution: LL87 if known, otherwise assume steam for old buildings
    dist = df["distribution"].fillna("unknown")
    assumed_steam = (dist == "unknown") & (df["yearbuilt"] < config.PRE_STEAM_YEAR)
    df["distribution_used"] = np.where(assumed_steam, "steam_assumed", dist)

    # headroom: ignore values that come from bad or tiny electricity data
    R = df["headroom_R_ashp"]
    valid = R.between(0, config.HEADROOM_MAX_VALID) & (df["peak_now_summer_kw"] >= config.MIN_SUMMER_KW)
    df["headroom_valid"] = valid
    R = R.where(valid)

    special_type = df["building_type"].isin(["industrial", "food_service"])
    hard = {
        "steam distribution": df["distribution_used"].isin(["steam", "steam_assumed"]),
        "major electrical upgrade likely": R > config.HEADROOM_MAJOR,
        "landmark or historic district": df["landmark_or_hist"].fillna(False).astype(bool),
        "process or kitchen gas use": special_type,
    }
    moderate = {
        "electrical upgrade possible": (R > config.HEADROOM_OK) & (R <= config.HEADROOM_MAJOR),
        "large hot water or cooking gas use": ~special_type & (df["space_heat_share"] < 0.5),
        "mixed use": df["building_type"] == "mixed_use",
    }
    hard = {k: v.fillna(False).astype(bool) for k, v in hard.items()}
    moderate = {k: v.fillna(False).astype(bool) for k, v in moderate.items()}
    n_hard = sum(v.astype(int) for v in hard.values())
    n_mod = sum(v.astype(int) for v in moderate.values())

    tier = np.select([n_hard >= 2, n_hard == 1, n_mod > 0], [3, 2, 2], default=1)

    excluded = df["mostly_steam"] | (df["fossil_kbtu"] <= 0) | (df["distribution"] == "district")
    df["feasibility_tier"] = pd.Series(tier, index=df.index).where(~excluded)

    def reasons(i):
        r = [k for k, v in hard.items() if v.loc[i]]
        r += [f"({k})" for k, v in moderate.items() if v.loc[i]]
        return "; ".join(r) or "none"
    df["tier_reason"] = [("excluded: no on-site fossil heating" if excluded.loc[i] else reasons(i))
                         for i in df.index]

    # ground-source needs open ground for wells
    df["gshp_space_ok"] = df["open_lot_sqft"] >= config.MIN_OPEN_LOT_SQFT

    # confidence: LL87 heating system + monthly gas split + valid headroom
    n_src = (df["distribution"].notna().astype(int)
             + (df["space_split_method"] == "monthly").astype(int)
             + valid.astype(int))
    df["data_confidence"] = np.select([n_src == 3, n_src == 2], ["high", "medium"], default="low")
    return df
