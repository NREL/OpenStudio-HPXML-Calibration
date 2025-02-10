import json
from pathlib import Path
from shutil import rmtree

import pytest

from openstudio_hpxml_calibration import app

REPO_DIR = Path(__file__).parent.parent
TEST_SIM_DIR = REPO_DIR / "tests" / "run"
TEST_CONFIG = REPO_DIR / "tests" / "data" / "test_config.json"


@pytest.fixture
def test_data():
    # Setup phase
    data: dict = json.loads(TEST_CONFIG.read_text())
    yield data  # Provide data dict to the test

    # Teardown phase
    rmtree(TEST_SIM_DIR, ignore_errors=True)


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
