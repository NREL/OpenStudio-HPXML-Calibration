import pathlib

import numpy as np
import pandas as pd
import pytest
from matplotlib import pyplot as plt

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import HpxmlDoc
from openstudio_hpxml_calibration.weather_normalization import regression as reg

test_hpxml_files = list(
    (pathlib.Path(__file__).resolve().parent.parent / "test_hpxmls").glob("*.xml")
)
results_dir = pathlib.Path(__file__).resolve().parent / "results"
results_dir.mkdir(exist_ok=True)


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    hpxml = HpxmlDoc(filename)
    bills, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    assert "electricity" in bills

    for fuel_type, df in bills.items():
        assert not pd.isna(df).any().any()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read_missing_start_end_date(filename):
    for start_end in ("start", "end"):
        # Remove all the EndDateTime elements
        hpxml = HpxmlDoc(filename)
        for el in hpxml.xpath(f"//h:{start_end.capitalize()}DateTime"):
            el.getparent().remove(el)

        # Load the bills
        bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
        assert "electricity" in bills_by_fuel_type

        # Ensure the dates got filled in
        for fuel_type, bills in bills_by_fuel_type.items():
            assert not pd.isna(bills[f"{start_end}_date"]).all()


@pytest.mark.parametrize("filename", test_hpxml_files, ids=lambda x: x.stem)
def test_weather_retrieval(filename):
    hpxml = HpxmlDoc(filename)
    lat, lon = ud.get_lat_lon_from_hpxml(hpxml)
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    for fuel_type, bills in bills_by_fuel_type.items():
        bills_temps = ud.join_bills_weather(bills, lat, lon)
        fig = plt.figure(figsize=(8, 6))
        plt.scatter(bills_temps["avg_temp"], bills_temps["daily_consumption"])
        fig.savefig(results_dir / f"{filename.stem}_{fuel_type}.png", dpi=200)
        assert not pd.isna(bills_temps["avg_temp"]).any()


def test_curve_fit():
    filename = (
        pathlib.Path(__file__).resolve().parent.parent
        / "test_hpxmls"
        / "3_natural_gas_fuel_furnace.xml"
    )
    hpxml = HpxmlDoc(filename)
    lat, lon = ud.get_lat_lon_from_hpxml(hpxml)
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    fuel_type = "natural gas"
    bills = bills_by_fuel_type["natural gas"]
    bills_temps = ud.join_bills_weather(bills, lat, lon)
    popt, pcov = reg.fit_model(reg.three_parameter_heating, bills_temps)
    temps_range = np.linspace(bills_temps["avg_temp"].min(), bills_temps["avg_temp"].max(), 100)
    daily_consumption_pred = reg.three_parameter_heating(temps_range, *popt)
    fig = plt.figure(figsize=(8, 6))
    plt.plot(temps_range, daily_consumption_pred, label="model", color="darkred")
    plt.scatter(bills_temps["avg_temp"], bills_temps["daily_consumption"], label="data")
    plt.legend()
    fig.savefig(results_dir / f"{filename.stem}_{fuel_type}_fit.png", dpi=200)
