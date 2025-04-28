# import json
from pathlib import Path

# from shutil import rmtree
# import pytest
from openstudio_hpxml_calibration.calibrate import Calibrate

TEST_DIR = Path(__file__).parent
TEST_DATA_DIR = TEST_DIR / "data"
# USER_CONFIG = TEST_DATA_DIR / "user_config.json"

# @pytest.fixture
# def test_data():
# Setup phase
# data: dict = json.loads(USER_CONFIG.read_text())
# return data  # Provide data dict to the test
# Teardown phase


def test_calibrate_reads_hpxml():
    foo = Calibrate("sample_files/house21.xml")
    normalized_usage = foo.normalize_bills()
    for fuel_type, (normalized_heating_usage, normalized_cooling_usage) in normalized_usage.items():
        assert normalized_heating_usage is not None
        assert normalized_cooling_usage is not None
        # print(f"Fuel Type: {fuel_type}")
        # print(f"Normalized Heating Usage: {normalized_heating_usage}")
        # print(f"Normalized Cooling Usage: {normalized_cooling_usage}")
    # assert False is True
