import json
from pathlib import Path
from shutil import rmtree

import pytest

from openstudio_hpxml_calibration import app

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
    rmtree(TEST_SIM_DIR, ignore_errors=True)
    rmtree(TEST_MODIFY_DIR, ignore_errors=True)
    rmtree(TEST_DATA_DIR / "generated_files", ignore_errors=True)
    rmtree(TEST_DATA_DIR / "reports", ignore_errors=True)
    (TEST_DATA_DIR / "out.osw").unlink(missing_ok=True)


def test_cli_has_help(capsys):
    app(["--help"])
    captured = capsys.readouterr()
    assert "Return the OpenStudio-HPXML" in captured.out


def test_cli_calls_openstudio(capsys):
    app(["openstudio-version"])
    captured = capsys.readouterr()
    assert "HPXML v4.0" in captured.out


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
    assert (TEST_SIM_DIR / "results_annual.json").exists()


def test_calls_modify_hpxml(test_data):
    app(
        [
            "modify-xml",
            test_data["test_workflow"],
        ]
    )
    assert (TEST_MODIFY_DIR / "new_output.xml").exists()
