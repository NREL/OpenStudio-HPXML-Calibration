import pytest

# @pytest.fixture
# def setup_data():
#     # Setup phase
#     data = {"key": "value"}
#     print("\nSetting up resources...")
#     yield data  # Provide data to the test
#     # Teardown phase
#     print("\nTearing down resources...")
# def test_example(setup_data):
#     assert setup_data["key"] == "value"
from openstudio_hpxml_calibration import app


def test_cli_has_help(capsys):
    app(["--help"])
    captured = capsys.readouterr()
    assert "Return the OpenStudio-HPXML" in captured.out


@pytest.mark.skip(reason="Requires OpenStudio installation")
def test_cli_calls_openstudio(capsys):
    app(["openstudio-version"])
    captured = capsys.readouterr()
    assert "HPXML v4.0" in captured.out


@pytest.mark.skip(reason="Requires OpenStudio installation")
def test_cli_calls_run_sim(capsys):
    app(["run-sim", "tests/data/sample-xml/sample.xml"])
    captured = capsys.readouterr()
    assert "Completed in" in captured.out
