from pathlib import Path

import openstudio_hpxml_calibration.weather_normalization.degree_days as dd
from openstudio_hpxml_calibration.hpxml import HpxmlDoc


def test_calc_daily_dbs():
    hpxml = HpxmlDoc(Path("test_hpxmls/ihmh_homes/ihmh4.xml").resolve())
    daily_dbs = dd.calc_daily_dbs(hpxml)
    assert daily_dbs.f.iloc[0] == 36.695
    assert daily_dbs.f.iloc[364] == 28.85
    assert daily_dbs.f.iloc[200] == 69.035
    assert daily_dbs.c.iloc[200] == 20.575


def test_calc_degree_days():
    hpxml = HpxmlDoc(Path("test_hpxmls/ihmh_homes/ihmh4.xml").resolve())
    daily_dbs = dd.calc_daily_dbs(hpxml)
    hdd = dd.calc_degree_days(daily_dbs.f, base_temp_f=65.0, is_heating=True)
    cdd = dd.calc_degree_days(daily_dbs.f, base_temp_f=65.0, is_heating=False)
    assert hdd == 5444.54
    assert cdd == 658.34


def test_calc_heat_cool_degree_days():
    hpxml = HpxmlDoc(Path("test_hpxmls/ihmh_homes/ihmh4.xml").resolve())
    daily_dbs = dd.calc_daily_dbs(hpxml)
    degree_days = dd.calc_heat_cool_degree_days(daily_dbs.f)
    assert degree_days["HDD65F"] == 5444.54
    assert degree_days["CDD65F"] == 658.34
