import json
from pathlib import Path

# from shutil import rmtree
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


def test_calibrate_reads_hpxml(test_data):
    foo = Calibrate(test_data["sample_xml_file"])
    normalized_usage = foo.normalize_bills()
    for fuel_type, (
        normalized_heating_usage,
        normalized_cooling_usage,
        normalized_baseload_usage,
    ) in normalized_usage.items():
        assert normalized_heating_usage is not None
        assert normalized_cooling_usage is not None
        assert normalized_baseload_usage is not None
    #     print(f"Fuel Type: {fuel_type}")
    #     print(f"Normalized Heating Usage: {normalized_heating_usage}")
    #     print(f"Normalized Cooling Usage: {normalized_cooling_usage}")
    #     print(f"Normalized Baseload Usage: {normalized_baseload_usage}")
    # assert False is True
