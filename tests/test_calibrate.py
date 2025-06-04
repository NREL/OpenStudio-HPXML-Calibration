import json
from pathlib import Path

import pandas as pd
import pytest
from loguru import logger

from openstudio_hpxml_calibration.calibrate import Calibrate

TEST_DIR = Path(__file__).parent
TEST_DATA_DIR = TEST_DIR / "data"
TEST_CONFIG = TEST_DATA_DIR / "test_config.json"


@pytest.fixture
def test_data():
    # Setup phase
    data: dict = json.loads(TEST_CONFIG.read_text())
    return data  # Provide data dict to the test
    # To implement a teardown phase:
    # yield data
    # put any teardown code here if needed
    # See test_cli.py for a teardown example


def test_calibrate_normalizes_bills_to_weather(test_data) -> None:
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    normalized_usage = cal.get_normalized_consumption_per_bill()
    for fuel_type, normalized_consumption in normalized_usage.items():
        assert normalized_consumption.shape == (12, 5)
        # Assert that baseload has 12 non-zero values
        assert not pd.isna(normalized_consumption["baseload"]).any()
        if fuel_type == "electricity":
            assert normalized_consumption["baseload"].sum().round(3) == 20.222
        elif fuel_type == "natural gas":
            assert normalized_consumption["baseload"].sum().round(3) == 17.854


def test_get_model_results(test_data) -> None:
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    simulation_results = cal.get_model_results(
        json_results_path=Path(test_data["annual_json_results_path"])
    )
    for fuel_type, disagg_results in simulation_results.items():
        if fuel_type == "electricity":
            assert disagg_results["heating"] == 3.372
            assert disagg_results["cooling"] == 8.907
            assert disagg_results["baseload"] == 26.745
        elif fuel_type == "natural gas":
            assert disagg_results["heating"] == 151.884
            assert disagg_results["baseload"] == 26.682
        elif disagg_results["baseload"] != 0.0:
            logger.warning(
                f"Unexpected fuel type {fuel_type} with non-zero baseload: {disagg_results['baseload']}"
            )


def test_compare_results(test_data):
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    normalized_usage = cal.get_normalized_consumption_per_bill()
    simulation_results = cal.get_model_results(
        json_results_path=Path(test_data["annual_json_results_path"])
    )
    comparison = cal.compare_results(
        normalized_consumption=normalized_usage, annual_model_results=simulation_results
    )
    assert len(comparison) == 2  # Should have two fuel types in the comparison for this building
    assert comparison["electricity"]["Absolute Error"]["baseload"] == 1918.2
    assert comparison["natural gas"]["Bias Error"]["heating"] == -125.3
