import json
from pathlib import Path
from shutil import rmtree

import pytest

from openstudio_hpxml_calibration import app
from openstudio_hpxml_calibration.hpxml import HpxmlDoc

TEST_DIR = Path(__file__).parent
TEST_DATA_DIR = TEST_DIR / "data"
TEST_SIM_DIR = TEST_DIR / "run"
TEST_MODIFY_DIR = TEST_DIR / "modifications"
TEST_CONFIG = TEST_DATA_DIR / "test_config.json"


@pytest.fixture
def test_data():
    # Setup phase
    data: dict = json.loads(TEST_CONFIG.read_text())
    yield data  # Provide data dict to the test

    # Teardown phase
    # To debug, comment the appropriate line here and review the test output
    rmtree(TEST_DATA_DIR / "generated_files", ignore_errors=True)
    rmtree(TEST_DATA_DIR / "reports", ignore_errors=True)
    (TEST_DATA_DIR / "out.osw").unlink(missing_ok=True)


def test_cli_has_help(capsys):
    # capsys is a builtin pytest fixture that captures stdout and stderr
    app(["--help"])
    captured = capsys.readouterr()
    assert "Return the OpenStudio-HPXML" in captured.out


def test_cli_calls_openstudio(capsys):
    # capsys is a builtin pytest fixture that captures stdout and stderr
    app(["openstudio-version"])
    captured = capsys.readouterr()
    assert "HPXML v" in captured.out


@pytest.mark.order(1)
def test_cli_calls_run_sim(test_data):
    app(
        [
            "run-sim",
            test_data["sample_xml_file"],
            "--output-dir",
            "tests",
            "--output-format",
            "json",
        ]
    )

    output_file = TEST_SIM_DIR / "results_annual.json"
    assert output_file.exists()
    output_data: dict = json.loads(output_file.read_text())
    assert output_data["Energy Use"]["Total (MBtu)"] == 218.83


def test_calls_modify_hpxml(test_data):
    app(
        [
            "modify-xml",
            test_data["test_workflow"],
        ]
    )

    output_file = TEST_MODIFY_DIR / "new_output.xml"
    assert output_file.exists()

    test_workflow_file = TEST_DATA_DIR / "test_modify_xml_workflow.osw"
    test_workflow: dict = json.loads(test_workflow_file.read_text())

    # Get the changed XML elements from the OSW file
    heating_offset = test_workflow["steps"][0]["arguments"]["heating_setpoint_offset"]
    # cooling_setpoint_offset = test_workflow["steps"][0]["arguments"]["cooling_setpoint_offset"]
    # infiltration_offset = test_workflow["steps"][0]["arguments"]["air_leakage_pct_change"]

    # Name of the original test xml file is the last part of the xml_file path
    test_file = Path(test_workflow["steps"][0]["arguments"]["xml_file_path"]).parts[-1]
    original_xml_file = TEST_DIR.parent / "test_hpxmls" / "real_homes" / test_file

    # Instantiate the original and modified HPXML files
    original_hpxml = HpxmlDoc(original_xml_file)
    modified_hpxml = HpxmlDoc(output_file)

    # Catching an AttributeError seems to be the best way to handle missing elements
    try:
        original_heating_setpoint = original_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetpointTempHeatingSeason
        modified_heating_setpoint = modified_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetpointTempHeatingSeason
        assert modified_heating_setpoint == original_heating_setpoint + heating_offset
    except AttributeError:
        pass


#     try:
#         original_heating_setback = original_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetbackTempHeatingSeason
#         modified_heating_setback = modified_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetbackTempHeatingSeason
#         assert modified_heating_setback == original_heating_setback + heating_offset
#     except AttributeError:
#         pass

#     try:
#         original_cooling_setback = original_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetupTempCoolingSeason
#         modified_cooling_setback = modified_hpxml.get_building().BuildingDetails.Systems.HVAC.HVACControl.SetupTempCoolingSeason
#         assert modified_cooling_setback == original_cooling_setback + cooling_setpoint_offset
#     except AttributeError:
#         pass

#     try:
#         original_infiltration = original_hpxml.get_building().BuildingDetails.Enclosure.AirInfiltration.BuildingAirLeakage.AirLeakage
#         modified_infiltration = modified_hpxml.get_building().BuildingDetails.Enclosure.AirInfiltration.BuildingAirLeakage.AirLeakage
#         assert modified_infiltration == original_infiltration * (1 + infiltration_offset)
#     except AttributeError:
#         pass
