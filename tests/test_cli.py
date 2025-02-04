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


def test_cli_gets_os_version():
    from openstudio_hpxml_calibration import openstudio_version

    openstudio_version()
