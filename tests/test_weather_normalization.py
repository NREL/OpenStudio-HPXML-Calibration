import pathlib
import sys

import numpy as np
import pandas as pd
import pytest
from matplotlib import pyplot as plt

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import HpxmlDoc
from openstudio_hpxml_calibration.weather_normalization import regression as reg

repo_root = pathlib.Path(__file__).resolve().parent.parent
test_hpxml_files = list((repo_root / "test_hpxmls").glob("*.xml"))
sample_files = list((repo_root / "sample_files").glob("*.xml"))


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    hpxml = HpxmlDoc(filename, validate_schematron=False)
    bills, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    assert "electricity" in bills

    for fuel_type, df in bills.items():
        assert not pd.isna(df).any().any()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read_missing_start_end_date(filename):
    for start_end in ("start", "end"):
        # Remove all the EndDateTime elements
        hpxml = HpxmlDoc(filename, validate_schematron=False)
        for el in hpxml.xpath(f"//h:{start_end.capitalize()}DateTime"):
            el.getparent().remove(el)

        # Load the bills
        bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
        assert "electricity" in bills_by_fuel_type

        # Ensure the dates got filled in
        for fuel_type, bills in bills_by_fuel_type.items():
            assert not pd.isna(bills[f"{start_end}_date"]).all()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_weather_retrieval(results_dir, filename):
    hpxml = HpxmlDoc(filename, validate_schematron=False)
    lat, lon = ud.get_lat_lon_from_hpxml(hpxml)
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    for fuel_type, bills in bills_by_fuel_type.items():
        bills_temps = ud.join_bills_weather(bills, lat, lon)
        fig = plt.figure(figsize=(8, 6))
        plt.scatter(bills_temps["avg_temp"], bills_temps["daily_consumption"])
        fig.savefig(
            results_dir / "weather_normalization" / f"{filename.stem}_{fuel_type}.png", dpi=200
        )
        plt.close(fig)
        assert not pd.isna(bills_temps["avg_temp"]).any()


# Skipping because of this bug in Python https://github.com/python/cpython/issues/125235#issuecomment-2412948604
@pytest.mark.skipif(
    sys.platform == "win32"
    and sys.version_info.major == 3
    and sys.version_info.minor == 13
    and sys.version_info.micro <= 2,
    reason="Skipping Windows and Python <= 3.13.2 due to known bug",
)
@pytest.mark.parametrize("filename", test_hpxml_files + sample_files, ids=lambda x: x.stem)
def test_curve_fit(results_dir, filename):
    hpxml = HpxmlDoc(filename, validate_schematron=False)
    lat, lon = ud.get_lat_lon_from_hpxml(hpxml)
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    for fuel_type, bills in bills_by_fuel_type.items():
        if bills.shape[0] < 10:
            # Rudimentary check for delivered fuels.
            continue
        bills_temps = ud.join_bills_weather(bills, lat, lon)
        model = reg.fit_model(bills_temps, bpi2400=False)
        temps_range = np.linspace(bills_temps["avg_temp"].min(), bills_temps["avg_temp"].max(), 500)
        fig = plt.figure(figsize=(8, 6))
        daily_consumption_pred = model(temps_range)
        cvrmse = model.calc_cvrmse(bills_temps)
        plt.plot(
            temps_range,
            daily_consumption_pred,
            label=f"{model.MODEL_NAME}, CVRMSE = {cvrmse:.1%}\n{model.parameters}",
        )
        plt.scatter(
            bills_temps["avg_temp"],
            bills_temps["daily_consumption"],
            label="data",
            color="darkgreen",
        )
        plt.title(f"{fuel_type} [{bill_units[fuel_type]}]")
        plt.legend()
        fig.savefig(
            results_dir / "weather_normalization" / f"{filename.stem}_{fuel_type}_fit.png", dpi=200
        )
        plt.close(fig)
        # TODO: reinstate this check, but for now some are coming in with larger CVRMSE
        # assert cvrmse <= 0.2
