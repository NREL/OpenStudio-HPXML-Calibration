import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import pytest
from loguru import logger
from lxml import etree

from openstudio_hpxml_calibration import app
from openstudio_hpxml_calibration.calibrate import Calibrate

TEST_DIR = Path(__file__).parent
TEST_DATA_DIR = TEST_DIR / "data"
FIXTURE_DATA = TEST_DATA_DIR / "test_fixture_data.json"
TEST_CONFIG = TEST_DATA_DIR / "test_config.yaml"

repo_root = TEST_DIR.parent
invalid_hpxmls = list((repo_root / "test_hpxmls" / "invalid_homes").glob("*.xml"))
results_path = TEST_DIR / "run" / "results_annual.json"


@pytest.fixture
def test_data():
    # Setup phase
    data: dict = json.loads(FIXTURE_DATA.read_text())
    return data  # Provide data dict to the test
    # To implement a teardown phase:
    # yield data
    # put any teardown code here if needed
    # See test_cli.py for a teardown example


def test_calibrate_normalizes_bills_to_weather(test_data) -> None:
    cal = Calibrate(
        original_hpxml_filepath=test_data["sample_xml_file"], config_filepath=TEST_CONFIG
    )
    normalized_usage = cal.get_normalized_consumption_per_bill()
    for fuel_type, normalized_consumption in normalized_usage.items():
        assert normalized_consumption.shape == (12, 5)
        # Assert that baseload has 12 non-zero values
        assert not pd.isna(normalized_consumption["baseload"]).any()
        if fuel_type == "electricity":
            assert normalized_consumption["baseload"].sum().round(3) == pytest.approx(21.364, 0.005)
        elif fuel_type == "natural gas":
            assert normalized_consumption["baseload"].sum().round(3) == pytest.approx(21.711, 0.005)


@pytest.mark.order(2)
def test_get_model_results(test_data) -> None:
    cal = Calibrate(
        original_hpxml_filepath=test_data["sample_xml_file"], config_filepath=TEST_CONFIG
    )
    if results_path.exists():
        simulation_results = cal.get_model_results(json_results_path=results_path)
    else:
        raise SystemExit(
            f"Results file {results_path} does not exist. Please run the simulation first by calling: "
            "`uv run pytest tests/test_cli.py::test_cli_calls_run_sim`."
        )
    for fuel_type, disagg_results in simulation_results.items():
        if fuel_type == "electricity":
            assert disagg_results["cooling"] == pytest.approx(9.3, 0.5)
            assert disagg_results["baseload"] == pytest.approx(26.7, 0.5)
        elif fuel_type == "natural gas":
            assert disagg_results["heating"] == pytest.approx(151.7, 0.5)
            assert disagg_results["baseload"] == pytest.approx(26.3, 0.5)
        elif disagg_results["baseload"] != 0.0:
            logger.warning(
                f"Unexpected fuel type {fuel_type} with non-zero baseload: {disagg_results['baseload']}"
            )


@pytest.mark.order(3)
def test_compare_results(test_data):
    cal = Calibrate(
        original_hpxml_filepath=test_data["sample_xml_file"], config_filepath=TEST_CONFIG
    )
    normalized_usage = cal.get_normalized_consumption_per_bill()
    if results_path.exists():
        simulation_results = cal.get_model_results(json_results_path=results_path)
    else:
        raise SystemExit(
            f"Results file {results_path} does not exist. Please run the simulation first by calling: "
            "`uv run pytest tests/test_cli.py::test_cli_calls_run_sim`."
        )
    comparison = cal.compare_results(
        normalized_consumption=normalized_usage, annual_model_results=simulation_results
    )
    assert len(comparison) == 2  # Should have two fuel types in the comparison for this building
    assert comparison["electricity"]["Absolute Error"]["baseload"] == 1544.5
    assert comparison["natural gas"]["Bias Error"]["heating"] == -79.3


def test_add_bills(test_data):
    # Confirm that an error is raised if no consumption data is in the hpxml object
    with pytest.raises(ValueError, match="No Consumption section matches the Building ID"):
        cal = Calibrate(
            original_hpxml_filepath=test_data["model_without_bills"],
            config_filepath=TEST_CONFIG,
        )
    # Confirm that the Consumption section is added when bills are provided
    cal = Calibrate(
        original_hpxml_filepath=test_data["model_without_bills"],
        csv_bills_filepath=test_data["sample_bill_csv_path"],
        config_filepath=TEST_CONFIG,
    )
    assert cal.hpxml.get_consumptions() is not None
    assert cal.hpxml.get_consumptions()[0] is not None
    # Confirm that we wrote the building_id correctly
    assert (
        cal.hpxml.get_consumptions()[0].BuildingID.attrib["idref"]
        == cal.hpxml.get_first_building_id()
    )
    # Confirm that we got the right fuel types from the incoming csv file
    raw_bills = pd.read_csv(test_data["sample_bill_csv_path"])
    assert (
        cal.hpxml.get_consumptions()[0]
        .ConsumptionDetails.ConsumptionInfo[0]
        .ConsumptionType.Energy.FuelType
        == raw_bills["FuelType"].unique()[0]
    )
    assert (
        cal.hpxml.get_consumptions()[0]
        .ConsumptionDetails.ConsumptionInfo[1]
        .ConsumptionType.Energy.FuelType
        == raw_bills["FuelType"].unique()[1]
    )
    # Spot-check that the Consumption xml element matches the csv utility data
    assert (
        cal.hpxml.get_consumptions()[0]
        .ConsumptionDetails.ConsumptionInfo[0]
        .ConsumptionDetail[2]
        .Consumption
        == 1200
    )
    assert (
        cal.hpxml.get_consumptions()[0]
        .ConsumptionDetails.ConsumptionInfo[1]
        .ConsumptionDetail[2]
        .Consumption
        == 14
    )


@pytest.mark.parametrize("filename", invalid_hpxmls, ids=lambda x: x.stem)
def test_hpxml_invalid(filename):
    if filename.stem in ("invalid_hpxml_xsd", "invalid_oshpxml_sch"):
        with pytest.raises(etree.DocumentInvalid):
            Calibrate(filename, config_filepath=TEST_CONFIG)
    else:
        with pytest.raises(ValueError):  # noqa: PT011
            Calibrate(filename, config_filepath=TEST_CONFIG)


def test_calibrate_runs_successfully():
    app(
        [
            "calibrate",
            "test_hpxmls/ihmh_homes/ihmh4.xml",
            "--config-filepath",
            str(TEST_CONFIG),
            "--output-dir",
            "tests/calibration_results/ihmh4_test",
        ]
    )
    output_file = TEST_DIR / "calibration_results/ihmh4_test/logbook.json"
    assert output_file.exists()


def test_calibrate_switches_to_simplified_correctly():
    app(
        [
            "calibrate",
            "test_hpxmls/ihmh_homes/ihmh5.xml",
            "--config-filepath",
            str(TEST_DATA_DIR / "test_config_no_cvrmse.yaml"),
            "--output-dir",
            "tests/calibration_results/ihmh5_test",
        ]
    )
    output_file = TEST_DIR / "calibration_results/ihmh5_test/logbook.json"
    assert output_file.exists()


def test_workflow_with_upgrade():
    temp_output_dir = Path(tempfile.mkdtemp(prefix=f"calib_test_{uuid.uuid4().hex[:6]}_"))

    # Create HPXML file for existing home
    subprocess.run(
        [
            "openstudio",
            "run",
            "--workflow",
            str(TEST_DIR / "data/ihmh3_existing_hpxml.osw"),
            "--measures_only",
        ],
        capture_output=True,
        check=True,
    )
    existing_hpxml_filepath = TEST_DIR / "data/uncalibrated_existing/ihmh3.xml"
    assert existing_hpxml_filepath.exists()

    # Run calibration
    csv_bills_filepath = TEST_DIR / "data/ihmh3_existing_bills.csv"
    config_filepath = TEST_DIR / "data/test_config.yaml"
    cal_output_dir = TEST_DIR / "data/uncalibrated_existing/calibration_results"
    app(
        [
            "calibrate",
            str(existing_hpxml_filepath),
            str(csv_bills_filepath),
            "--output-dir",
            str(cal_output_dir),
            "--config-filepath",
            str(config_filepath),
            "--num-proc",
            "8",
        ]
    )
    cal_output_filepath = cal_output_dir / "logbook.json"
    assert cal_output_filepath.exists()
    cal_results = json.loads(cal_output_filepath.read_text())
    assert cal_results["calibration_success"]
    cal_adjustments = cal_results["calibration_results"][-1]["best_individual"]

    # Create HPXML file for upgrade scenario (R-60 attic insulation)
    subprocess.run(
        [
            "openstudio",
            "run",
            "--workflow",
            str(TEST_DIR / "data/ihmh3_upgrade_hpxml.osw"),
            "--measures_only",
        ],
        capture_output=True,
        check=True,
    )
    upgrade_hpxml_filepath = TEST_DIR / "data/uncalibrated_upgrade/ihmh3.xml"
    assert upgrade_hpxml_filepath.exists()

    # Run upgrade scenario simulation
    upgrade_run_dir = TEST_DIR / "data/uncalibrated_upgrade"
    app(
        [
            "run-sim",
            str(upgrade_hpxml_filepath),
            "--output-dir",
            str(upgrade_run_dir),
            "--output-format",
            "json",
        ]
    )
    upgrade_json_filepath = upgrade_run_dir / "run/results_annual.json"
    assert upgrade_json_filepath.exists()

    # FUTURE: Move some methods outside of the Calibrate class so we
    # can call them directly without having to create a cal object.
    cal = Calibrate(
        original_hpxml_filepath=existing_hpxml_filepath,
        config_filepath=config_filepath,
        csv_bills_filepath=csv_bills_filepath,
    )
    measure_dir = str(Path(__file__).resolve().parent.parent / "src/measures")

    # Run upgrade model w/ calibration adjustments
    # **NOTE**: We exclude the ceiling R-value adjustment so as not to override the
    #           upgrade scenario R-value.
    cal_upgrade_hpxml_filepath = TEST_DIR / "data/calibrated_upgrade/ihmh3.xml"
    cal_adjustments["xml_file_path"] = str(upgrade_hpxml_filepath)
    cal_adjustments["save_file_path"] = str(cal_upgrade_hpxml_filepath)
    cal_adjustments.pop("ceiling_r_value_multiplier")
    adjustments_osw = Path(temp_output_dir / "modify_hpxml.osw")
    cal.create_measure_input_file(cal_adjustments, adjustments_osw, measure_dir)
    app(["modify-xml", str(adjustments_osw)])
    cal_upgrade_run_dir = TEST_DIR / "data/calibrated_upgrade"
    app(
        [
            "run-sim",
            str(cal_upgrade_hpxml_filepath),
            "--output-dir",
            str(cal_upgrade_run_dir),
            "--output-format",
            "json",
        ]
    )
    cal_upgrade_json_filepath = cal_upgrade_run_dir / "run/results_annual.json"
    assert cal_upgrade_json_filepath.exists()

    # Gather simulation results
    uncal_existing_results = cal_results["existing_home_results"]["existing_home_sim_results"]
    uncal_upgrade_results = cal.get_model_results(json_results_path=upgrade_json_filepath)
    cal_existing_results = cal_results["calibration_results"][-1]["best_individual_sim_results"]
    cal_upgrade_results = cal.get_model_results(json_results_path=cal_upgrade_json_filepath)

    # Check calibrated savings is similar to, but not identical to, uncalibrated savings
    uncal_mbtu_savings = sum(uncal_existing_results["electricity"].values()) - sum(
        uncal_upgrade_results["electricity"].values()
    )
    cal_mbtu_savings = sum(cal_existing_results["electricity"].values()) - sum(
        cal_upgrade_results["electricity"].values()
    )
    diff_mbtu_savings = abs(cal_mbtu_savings - uncal_mbtu_savings)
    assert diff_mbtu_savings > 0
    assert diff_mbtu_savings < 5

    # Clean up
    for subdir in (
        "uncalibrated_existing",
        "uncalibrated_upgrade",
        "calibrated_upgrade",
        "generated_files",
    ):
        shutil.rmtree(str(TEST_DIR / "data" / subdir))
