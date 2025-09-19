import json
import pathlib
import sys

import pandas as pd
import pytest
from matplotlib import pyplot as plt

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.utils import _load_config, plot_fuel_type_curve_fits
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel
from openstudio_hpxml_calibration.weather_normalization.regression import (
    Bpi2400ModelFitError,
    fit_model,
)

test_config = _load_config("tests/data/test_config.yaml")

repo_root = pathlib.Path(__file__).resolve().parent.parent
ira_rebate_hpxmls = list((repo_root / "test_hpxmls" / "ira_rebates").glob("*.xml"))
real_home_hpxmls = list((repo_root / "test_hpxmls" / "real_homes").glob("*.xml"))
ihmh_home_hpxmls = list((repo_root / "test_hpxmls" / "ihmh_homes").glob("*.xml"))


@pytest.mark.parametrize("filename", ira_rebate_hpxmls, ids=lambda x: x.stem)
def test_hpxml_utility_bill_read(filename):
    hpxml = HpxmlDoc(filename)
    bills, _bill_units, _tz = ud.get_bills_from_hpxml(hpxml)
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
        bills_by_fuel_type, _bill_units, _tz = ud.get_bills_from_hpxml(hpxml)
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
    bills_by_fuel_type, _bill_units, _tz = ud.get_bills_from_hpxml(hpxml)
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
# Suppress warning ("invalid value encountered in sqrt") that is only emitted during testing, not during normal use
# See discussion in https://github.com/NREL/OpenStudio-HPXML-Calibration/issues/75
@pytest.mark.filterwarnings("ignore:invalid value encountered in sqrt:RuntimeWarning")
# Skipping because of this bug in Python https://github.com/python/cpython/issues/125235#issuecomment-2412948604
@pytest.mark.skipif(
    sys.platform == "win32"
    and sys.version_info.major == 3
    and sys.version_info.minor == 13
    and sys.version_info.micro <= 2,
    reason="Skipping Windows and Python <= 3.13.2 due to known bug",
)
@pytest.mark.parametrize(
    "filename", ira_rebate_hpxmls + real_home_hpxmls + ihmh_home_hpxmls, ids=lambda x: x.stem
)
def test_curve_fit_and_fit_model(results_dir, filename):
    try:
        hpxml = HpxmlDoc(filename)
        inv_model = InverseModel(hpxml, user_config=test_config)
        successful_fits = 0  # Track number of successful fits
        output_filepath = results_dir / "weather_normalization"

        fuel_types = hpxml.get_fuel_types()
        conditioning_fuels = fuel_types["heating"] | fuel_types["cooling"]
        delivered_fuels = (
            FuelType.FUEL_OIL.value,
            FuelType.PROPANE.value,
            FuelType.WOOD.value,
            FuelType.WOOD_PELLETS.value,
        )

        for fuel_type, bills in inv_model.bills_by_fuel_type.items():
            if fuel_type.value in delivered_fuels:
                continue  # Skip delivered fuels

            model = inv_model.get_model(fuel_type)
            bills_temps = inv_model.bills_weather_by_fuel_type_in_btu[fuel_type]
            cvrmse = model.calc_cvrmse(bills_temps)
            plot_fuel_type_curve_fits(inv_model, output_filepath, filename.stem)

            # Save CVRMSE result per test
            individual_result = {f"{filename.stem}_{fuel_type}": cvrmse}
            json_path = output_filepath / f"{filename.stem}_{fuel_type.value}.json"
            with open(json_path, "w") as f:
                json.dump(individual_result, f, indent=2)

            best_fitting_model = fit_model(
                bills_temps,
                test_config["acceptance_criteria"]["bill_regression_max_cvrmse"],
                conditioning_fuels,
                fuel_type,
            )
            assert best_fitting_model is not None

            successful_fits += 1

        assert successful_fits > 0, (
            f"No successful regression fits for {filename.stem}_{fuel_type.value}"
        )
    except Bpi2400ModelFitError:
        # Only these files should raise this error
        assert filename.name in {"ihmh7.xml", "house11.xml", "house83.xml"}


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
