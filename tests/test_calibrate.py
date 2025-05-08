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
    # Teardown phase


def test_calibrate_normalizes_bills_to_weather(test_data):
    foo = Calibrate(test_data["sample_xml_file"])
    normalized_usage = foo.get_normalized_consumption_per_bill()
    for fuel_type, normalized_consumption in normalized_usage.items():
        assert normalized_consumption.shape == (12, 5)
        # Assert that baseload has 12 non-zero values
        assert not pd.isna(normalized_consumption["baseload"]).any()


def test_get_model_results(test_data):
    foo = Calibrate(test_data["sample_xml_file"])
    simulation_results = foo.get_model_results(Path(test_data["timeseries_json_results_path"]))
    for fuel_type, disagg_results in simulation_results.items():
        # assert that this string is one of the keys in the disaggregated results
        assert [s for s in disagg_results if "_heating_energy" in s]
