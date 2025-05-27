import json
from pathlib import Path

import pandas as pd
import pytest

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


def test_calibrate_normalizes_bills_to_weather(test_data) -> None:
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    normalized_usage = cal.get_normalized_consumption_per_bill()
    for fuel_type, normalized_consumption in normalized_usage.items():
        # print(fuel_type)
        # print(normalized_consumption)
        assert normalized_consumption.shape == (12, 5)
        # Assert that baseload has 12 non-zero values
        assert not pd.isna(normalized_consumption["baseload"]).any()
        # assert False is True
        # this bogus assert creates a test failure so the print statements can be seen for debugging


def test_get_model_results(test_data) -> None:
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    simulation_results = cal.get_model_results(
        json_results_path=Path(test_data["annual_json_results_path"])
    )
    for fuel_type, disagg_results in simulation_results.items():
        # assert that this string is one of the keys in the disaggregated results
        # print(fuel_type)
        # print(len(disagg_results))
        # print(disagg_results)
        assert [s for s in disagg_results if "heating" in s]
        # assert False is True
        # this bogus assert creates a test failure so the print statements can be seen for debugging


def test_compare_results(test_data):
    cal = Calibrate(original_hpxml_filepath=test_data["sample_xml_file"])
    normalized_usage = cal.get_normalized_consumption_per_bill()
    simulation_results = cal.get_model_results(
        json_results_path=Path(test_data["annual_json_results_path"])
    )
    comparison = cal.compare_results(
        normalized_consumption=normalized_usage, annual_model_results=simulation_results
    )
    assert len(comparison) == 2  # Should have two fuel types in the comparison
    assert comparison["electricity"]["Absolute Error"]["baseload"] == 1918.2
    assert comparison["natural gas"]["Bias Error"]["heating"] == -125.3
    # for fuel_type, comparison in results_comparison.items():
    #     print(fuel_type)
    #     print(comparison["model_results"].keys())
    #     print(
    #         comparison["model_results"].get(
    #             "(136, 165)", "The dates you entered do not correspond with bill dates"
    #         )
    #     )
    #     print(comparison["model_results"]["(136, 165)"].keys())
    # print(comparison["model_results"]["(158, 187)"])
    # assert False is True
    # this bogus assert creates a test failure so the print statements can be seen for debugging
