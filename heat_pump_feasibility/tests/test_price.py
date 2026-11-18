"""Unit tests for the price-of-switch step. Run: pytest"""
import numpy as np
import pandas as pd
import pytest

from hpf import config
from hpf.price import estimate_price


def building(**kw):
    row = dict(
        building_type="office", gfa=100_000, unitsres=0, resarea=0, bldgarea=100_000,
        distribution_used="hot_water", headroom_R_ashp=0.9, headroom_valid=True,
        landmark_or_hist=False, fuel_space_kbtu=2_000_000, install_year=np.nan,
        last_permit_year=np.nan, feasibility_tier=1,
    )
    row.update(kw)
    return pd.DataFrame([row])


def test_office_priced_per_sqft_low_end_for_easy_building():
    d = estimate_price(building()).iloc[0]
    lo, hi = config.COST_PER_SQFT["ashp"]
    pos = config.RANGE_POSITION_START + config.RANGE_POSITION_SHIFT["hot water or ducted"]
    assert d.cost_basis == "per_sqft"
    assert d.price_ashp_low == pytest.approx(100_000 * lo)
    assert d.price_ashp_mid == pytest.approx(100_000 * (lo + pos * (hi - lo)))


def test_steam_moves_price_up():
    easy = estimate_price(building()).iloc[0]
    steam = estimate_price(building(distribution_used="steam")).iloc[0]
    assert steam.price_ashp_mid > easy.price_ashp_mid


def test_multifamily_priced_per_unit_with_incentive():
    d = estimate_price(building(building_type="multifamily", unitsres=100, resarea=95_000)).iloc[0]
    lo, hi = config.COST_PER_UNIT["large"]["ashp"]
    assert d.cost_basis == "per_unit"
    assert d.price_ashp_low == pytest.approx(100 * lo)
    assert d.incentive_ashp == pytest.approx(100 * config.INCENTIVE_MF_PER_UNIT)


def test_incentive_capped():
    d = estimate_price(building(fuel_space_kbtu=1e12)).iloc[0]
    assert d.incentive_ashp == pytest.approx(config.INCENTIVE_CAP_SHARE * d.price_ashp_mid)


def test_boiler_credit_only_when_due():
    old = estimate_price(building(install_year=1980)).iloc[0]
    new = estimate_price(building(install_year=2020)).iloc[0]
    assert old.avoided_boiler_credit == pytest.approx(config.BOILER_COST_PER_SQFT * 100_000)
    assert new.avoided_boiler_credit == 0
    assert old.price_ashp_net < new.price_ashp_net


def test_excluded_building_has_no_price():
    d = estimate_price(building(feasibility_tier=np.nan)).iloc[0]
    assert pd.isna(d.price_ashp_net)


def test_implausible_unit_count_is_replaced():
    # 1,000 units in 20,000 sq ft = 20 sq ft per unit: not possible
    d = estimate_price(building(building_type="multifamily", gfa=20_000, bldgarea=20_000,
                                unitsres=1_000, resarea=20_000)).iloc[0]
    assert d.units_priced == round(20_000 / config.AVG_SQFT_PER_UNIT)
    assert d.cost_basis == "per_unit_estimated"


def test_too_few_units_is_replaced():
    # 2 units in 200,000 sq ft = 100,000 sq ft per unit: not possible
    d = estimate_price(building(building_type="multifamily", gfa=200_000, bldgarea=200_000,
                                unitsres=2, resarea=200_000)).iloc[0]
    assert d.units_priced == round(200_000 / config.AVG_SQFT_PER_UNIT)


def test_zero_net_price_is_flagged(monkeypatch):
    # make the boiler credit larger than the cost so the net price floors at $0
    monkeypatch.setattr(config, "BOILER_COST_PER_SQFT", 1_000)
    d = estimate_price(building(install_year=1970)).iloc[0]
    assert d.price_ashp_net == 0
    assert bool(d.price_ashp_net_is_zero)
    normal = estimate_price(building(install_year=2020)).iloc[0]
    assert not bool(normal.price_ashp_net_is_zero)
