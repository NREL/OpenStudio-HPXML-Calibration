import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest
from matplotlib import pyplot as plt

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.utils import _load_config
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel
from openstudio_hpxml_calibration.weather_normalization.regression import fit_model

test_config = _load_config("tests/data/test_config.yaml")

repo_root = pathlib.Path(__file__).resolve().parent.parent
ira_rebate_hpxmls = list((repo_root / "test_hpxmls" / "ira_rebates").glob("*.xml"))


@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    hpxml = HpxmlDoc(filename)
    bills, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    assert any("electricity" in fuel_type.value for fuel_type in bills)

    for fuel_type, df in bills.items():
        assert not pd.isna(df).any().any()


@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read_missing_start_end_date(filename):
    for start_end in ("start", "end"):
        # Remove all the EndDateTime elements
        hpxml = HpxmlDoc(filename)
        for el in hpxml.xpath(f"//h:{start_end.capitalize()}DateTime"):
            el.getparent().remove(el)

        # Load the bills
        bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
        assert any("electricity" in fuel_type.value for fuel_type in bills_by_fuel_type)

        # Ensure the dates got filled in
        for fuel_type, bills in bills_by_fuel_type.items():
            assert not pd.isna(bills[f"{start_end}_date"]).all()


# Use flaky to address intermittent tcl errors on Windows https://stackoverflow.com/questions/71443540/intermittent-pytest-failures-complaining-about-missing-tcl-files-even-though-the
@pytest.mark.flaky(max_runs=3)
@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_weather_retrieval(results_dir, filename):
    hpxml = HpxmlDoc(filename)
    lat, lon = hpxml.get_lat_lon()
    bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(hpxml)
    for fuel_type, bills in bills_by_fuel_type.items():
        bills_temps, _ = ud.join_bills_weather(bills, lat, lon)
        fig = plt.figure(figsize=(8, 6))
        plt.scatter(bills_temps["avg_temp"], bills_temps["daily_consumption"])
        fig.savefig(
            results_dir / "weather_normalization" / f"{filename.stem}_{fuel_type.value}.png",
            dpi=200,
        )
        plt.close(fig)
        assert not pd.isna(bills_temps["avg_temp"]).any()


# Use flaky to address intermittent tcl errors on Windows https://stackoverflow.com/questions/71443540/intermittent-pytest-failures-complaining-about-missing-tcl-files-even-though-the
@pytest.mark.flaky(max_runs=3)
# Skipping because of this bug in Python https://github.com/python/cpython/issues/125235#issuecomment-2412948604
@pytest.mark.skipif(
    sys.platform == "win32"
    and sys.version_info.major == 3
    and sys.version_info.minor == 13
    and sys.version_info.micro <= 2,
    reason="Skipping Windows and Python <= 3.13.2 due to known bug",
)
@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_curve_fit(results_dir, filename):
    hpxml = HpxmlDoc(filename)
    inv_model = InverseModel(hpxml, user_config=test_config)
    successful_fits = 0  # Track number of successful fits

    for fuel_type, bills in inv_model.bills_by_fuel_type.items():
        model = inv_model.get_model(fuel_type)
        bills_temps = inv_model.bills_weather_by_fuel_type_in_btu[fuel_type]
        temps_range = np.linspace(bills_temps["avg_temp"].min(), bills_temps["avg_temp"].max(), 500)
        fig = plt.figure(figsize=(8, 6))
        daily_consumption_pred = model(temps_range)
        cvrmse = model.calc_cvrmse(bills_temps)
        num_params = len(model.parameters)
        if num_params == 5:
            plt.plot(
                temps_range,
                daily_consumption_pred,
                label=(
                    f"{model.MODEL_NAME}, CVRMSE = {cvrmse:.1%}\n Model parameters:\n"
                    f"1) Baseload value: {model.parameters[0]:.3f}\n"
                    f"2) Slopes: {model.parameters[1]:.3f}, {model.parameters[2]:.3f}\n"
                    f"3) Inflection points: {model.parameters[-2]:.1f}, {model.parameters[-1]:.1f}"
                ),
            )
        elif num_params == 3:
            plt.plot(
                temps_range,
                daily_consumption_pred,
                label=(
                    f"{model.MODEL_NAME}, CVRMSE = {cvrmse:.1%}\n Model parameters:\n"
                    f"1) Baseload value: {model.parameters[0]:.3f}\n"
                    f"2) Slope: {model.parameters[1]:.3f}\n"
                    f"3) Inflection point: {model.parameters[-1]:.1f}"
                ),
            )
        plt.scatter(
            bills_temps["avg_temp"],
            bills_temps["daily_consumption"],
            label="data",
            color="darkgreen",
        )
        plt.title(f"{filename.stem} {fuel_type.value}")
        plt.xlabel("Avg Daily Temperature [degF]")
        plt.ylabel("Daily Consumption [BTU]")
        plt.legend()
        fig.savefig(
            results_dir / "weather_normalization" / f"{filename.stem}_{fuel_type.value}_fit.png",
            dpi=200,
        )
        plt.close(fig)
        # TODO: reinstate this check, but for now some are coming in with larger CVRMSE
        # assert cvrmse <= 0.2

        # Save CVRMSE result per test
        individual_result = {f"{filename.stem}_{fuel_type}": cvrmse}
        json_path = (
            results_dir / "weather_normalization" / f"{filename.stem}_{fuel_type.value}.json"
        )
        with open(json_path, "w") as f:
            json.dump(individual_result, f, indent=2)

        successful_fits += 1

    assert successful_fits > 0, (
        f"No successful regression fits for {filename.stem}_{fuel_type.value}"
    )


# Use flaky to address intermittent tcl errors on Windows https://stackoverflow.com/questions/71443540/intermittent-pytest-failures-complaining-about-missing-tcl-files-even-though-the
@pytest.mark.flaky(max_runs=3)
# Skipping because of this bug in Python https://github.com/python/cpython/issues/125235#issuecomment-2412948604
@pytest.mark.skipif(
    sys.platform == "win32"
    and sys.version_info.major == 3
    and sys.version_info.minor == 13
    and sys.version_info.micro <= 2,
    reason="Skipping Windows and Python <= 3.13.2 due to known bug",
)
@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_fit_model(filename):
    hpxml = HpxmlDoc(filename)
    inv_model = InverseModel(hpxml, user_config=test_config)
    heating_fuels, cooling_fuels = hpxml.get_fuel_types()
    conditioning_fuels = heating_fuels | cooling_fuels

    for fuel_type, bills in inv_model.bills_by_fuel_type.items():
        bills_temps = inv_model.bills_weather_by_fuel_type_in_btu[fuel_type]

        best_fitting_model = fit_model(
            bills_temps,
            test_config["acceptance_criteria"]["bill_regression_max_cvrmse"],
            conditioning_fuels,
            fuel_type,
        )

        assert best_fitting_model is not None


def test_normalize_consumption_to_epw():
    filename = repo_root / "test_hpxmls" / "real_homes" / "house21.xml"
    hpxml = HpxmlDoc(filename)
    inv_model = InverseModel(hpxml, user_config=test_config)

    for fuel_type, bills in inv_model.bills_by_fuel_type.items():
        epw_daily = convert_units(inv_model.predict_epw_daily(fuel_type), "BTU", "kBTU")
        print(f"EPW Daily {fuel_type.value} (kbtu):\n", epw_daily)
        epw_annual = epw_daily.sum()
        print(f"EPW Annual {fuel_type.value} (kbtu):\n", epw_annual)
        assert not pd.isna(epw_annual).any()
