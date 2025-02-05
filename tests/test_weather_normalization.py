import pytest
import pathlib

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud

test_hpxml_files = (pathlib.Path(__file__).resolve().parent.parent / "test_hpxmls").glob("*.xml")


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    tree = ud.parse_hpxml(filename)
    root = tree.getroot()
    bills, bill_units, tz = ud.get_bills_from_hpxml(root)
    assert "electricity" in bills

    for fuel_type, df in bills.items():
        pass
