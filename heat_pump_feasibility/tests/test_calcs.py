"""Unit tests for the formulas. Run: pytest"""
import pandas as pd
import pytest

from hpf import config
from hpf.calcs import current_peaks, heat_pump_load, split_space_heating
from hpf.utils import clean_bbl, norm


def base_row(**kw):
    row = dict(building_type="multifamily", gas_kbtu=1_200_000, oil2_kbtu=0, oil4_kbtu=0,
               fossil_kbtu=1_200_000, gas_annual_monthly_kbtu=1_200_000,
               gas_summer_avg_kbtu=25_000, distribution="hot_water", boiler_eff=0.8,
               elec_kwh=500_000, elec_summer_max_kwh=60_000, elec_winter_max_kwh=40_000)
    row.update(kw)
    return pd.DataFrame([row])


def test_norm():
    assert norm("Natural Gas Use (kBtu)") == "natural_gas_use_kbtu"
    assert norm("Property GFA - Self-Reported (ft²)") == "property_gfa_self_reported_ft"


def test_clean_bbl():
    s = pd.Series(["4-07021-0100", "1012340056;1012340057", 1012340056.0, "missing"])
    assert clean_bbl(s).tolist()[:3] == ["4070210100", "1012340056", "1012340056"]
    assert pd.isna(clean_bbl(s).iloc[3])


def test_space_split_monthly():
    df = split_space_heating(base_row())
    # baseload = 12 * 25,000 = 300,000 -> space share = 0.75
    assert df.space_heat_share.iloc[0] == pytest.approx(0.75)
    assert df.fuel_space_kbtu.iloc[0] == pytest.approx(900_000)


def test_space_split_falls_back_without_monthly():
    df = split_space_heating(base_row(gas_summer_avg_kbtu=None))
    assert df.space_split_method.iloc[0] == "default_share"
    assert df.space_heat_share.iloc[0] == config.SPACE_HEAT_SHARE_DEFAULT["multifamily"]


def test_heat_pump_load_and_peak():
    df = heat_pump_load(split_space_heating(base_row()))
    q = 900_000 * 0.8
    assert df.hp_kwh_ashp.iloc[0] == pytest.approx(q / (config.HEAT_PUMPS["ashp"]["scop"] * 3.412))
    ua = q / (24 * config.HDD_65F)
    peak = ua * (config.T_BALANCE_F - config.T_DESIGN_F) / (config.HEAT_PUMPS["ashp"]["cop_cold"] * 3.412)
    assert df.hp_peak_kw_ashp.iloc[0] == pytest.approx(peak)
    # ground-source always adds less peak than air-source
    assert df.hp_peak_kw_gshp.iloc[0] < df.hp_peak_kw_ashp.iloc[0]


def test_headroom():
    df = current_peaks(heat_pump_load(split_space_heating(base_row())))
    lf = config.LOAD_FACTOR["multifamily"]
    summer = 60_000 / (730 * lf)
    winter = 40_000 / (730 * lf)
    expected = (winter + df.hp_peak_kw_ashp.iloc[0]) / summer
    assert df.headroom_R_ashp.iloc[0] == pytest.approx(expected)
