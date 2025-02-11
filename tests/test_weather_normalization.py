import pathlib
import re

import pandas as pd
import pytest

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud

test_hpxml_files = list(
    (pathlib.Path(__file__).resolve().parent.parent / "test_hpxmls").glob("*.xml")
)


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    tree = ud.parse_hpxml(filename)
    root = tree.getroot()
    bills, bill_units, tz = ud.get_bills_from_hpxml(root)
    assert "electricity" in bills

    for fuel_type, df in bills.items():
        assert not pd.isna(df).any().any()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read_missing_start_end_date(filename):
    for start_end in ("start", "end"):
        # Remove all the EndDateTime elements
        tree = ud.parse_hpxml(filename)
        root = tree.getroot()
        ns = re.match(r"\{(.+)\}", root.tag).group(1)
        xpkw = {"namespaces": {"h": ns}}
        for el in root.xpath(f"//h:{start_end.capitalize()}DateTime", **xpkw):
            el.getparent().remove(el)

        # Load the bills
        bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(root)
        assert "electricity" in bills_by_fuel_type

        # Ensure the dates got filled in
        for fuel_type, bills in bills_by_fuel_type.items():
            assert not pd.isna(bills[f"{start_end}_date"]).all()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_weather_retrieval(filename):
    tree = ud.parse_hpxml(filename)
    root = tree.getroot()
    lat, lon = ud.get_lat_lon_from_hpxml(root)
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(root)
    for fuel_type, bills in bills_by_fuel_type.items():
        ud.join_bills_weather(bills, lat, lon)
