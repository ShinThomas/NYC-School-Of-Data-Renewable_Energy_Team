"""Engineering estimates: space-heating fuel, heat pump electricity, peaks, headroom.

Every function takes and returns a DataFrame with one row per building.
Formulas (see docs/methods.md):
    Q        = fuel_space * boiler_eff                         delivered heat, kBtu/yr
    kWh_HP   = Q / (SCOP * 3.412)                              yearly heat pump electricity
    UA       = Q / (24 * HDD)                                  heat loss, kBtu/h per °F
    kW_HP    = UA * (T_balance - T_design) / (COP_cold * 3.412)  design-day peak
    kW_now   = max monthly kWh / (730 * LF)                    current peak (summer, winter)
    R        = (kW_now_winter + kW_HP) / kW_now_summer         electrical headroom ratio
"""
import numpy as np
import pandas as pd

from hpf import config


def split_space_heating(df: pd.DataFrame) -> pd.DataFrame:
    """Share of fossil fuel used for space heating.

    Monthly method: summer gas = hot water + cooking (baseload);
    space-heating share = 1 - 12 * summer average / annual gas.
    Fallback: default share by building type.
    """
    df = df.copy()
    has_monthly = (df["gas_annual_monthly_kbtu"] > 0) & df["gas_summer_avg_kbtu"].notna()
    share = 1 - 12 * df["gas_summer_avg_kbtu"] / df["gas_annual_monthly_kbtu"]
    default = df["building_type"].map(config.SPACE_HEAT_SHARE_DEFAULT)
    # oil-heated buildings have no monthly oil data, so use the default for them
    gas_main = df["gas_kbtu"].fillna(0) >= (df["oil2_kbtu"].fillna(0) + df["oil4_kbtu"].fillna(0))
    use_monthly = has_monthly & gas_main
    df["space_heat_share"] = np.where(use_monthly, share.clip(0, 1), default)
    df["space_split_method"] = np.where(use_monthly, "monthly", "default_share")
    df["fuel_space_kbtu"] = df["fossil_kbtu"] * df["space_heat_share"]
    df["fuel_base_kbtu"] = df["fossil_kbtu"] - df["fuel_space_kbtu"]
    return df


def heat_pump_load(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    default_eff = df["distribution"].map(config.BOILER_EFF_DEFAULT).fillna(
        config.BOILER_EFF_DEFAULT["unknown"])
    df["boiler_eff_used"] = df["boiler_eff"].fillna(default_eff)
    q = df["fuel_space_kbtu"] * df["boiler_eff_used"]              # delivered heat
    df["heat_delivered_kbtu"] = q
    ua = q / (24 * config.HDD_65F)                                   # kBtu/h per °F
    dT = config.T_BALANCE_F - config.T_DESIGN_F
    for hp, p in config.HEAT_PUMPS.items():
        df[f"hp_kwh_{hp}"] = q / (p["scop"] * config.KBTU_PER_KWH)
        df[f"hp_peak_kw_{hp}"] = ua * dT / (p["cop_cold"] * config.KBTU_PER_KWH)
    return df


def current_peaks(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lf = df["building_type"].map(config.LOAD_FACTOR).fillna(0.5)
    annual_kw = df["elec_kwh"] / (8760 * lf)
    summer = df["elec_summer_max_kwh"] / (config.HOURS_PER_MONTH * lf)
    winter = df["elec_winter_max_kwh"] / (config.HOURS_PER_MONTH * lf)
    df["peak_now_summer_kw"] = summer.fillna(annual_kw)
    df["peak_now_winter_kw"] = winter.fillna(annual_kw)
    df["peak_method"] = np.where(summer.notna() & winter.notna(), "monthly", "annual")
    for hp in config.HEAT_PUMPS:
        denom = df["peak_now_summer_kw"].where(df["peak_now_summer_kw"] > 0)
        df[f"headroom_R_{hp}"] = (df["peak_now_winter_kw"] + df[f"hp_peak_kw_{hp}"]) / denom
    return df
