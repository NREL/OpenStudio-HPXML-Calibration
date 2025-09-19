# Getting Started

Generate an HPXML model of home energy use, calibrated to utility data

- `openstudio-hpxml-calibration --help`
- Or the short version `oshc -h`

## Required inputs

- An OSW (JSON) for the `BuildResidentialHPXML` measure
- A CSV file of utility data
- A config file specific to the home being calibrated

## Example steps

1. Write an [OSW file](inputs.md#osw-json-file-defining-the-home) that defines the existing home
1. Create an HPXML model from that osw file: `openstudio run --workflow <existing_home.osw> --measures_only`
1. Write a [utility consumption file](inputs.md#utility-consumption-csv-file) in csv format
1. Define a [custom configuration file](inputs.md#config-file) accounting for what is known about this home
1. Calibrate that model to the utility consumption data: `oshc calibrate --hpxml-filepath asdf.xml --csv-bills-filepath bcde.csv --config-filepath qwer.yml --output-dir test_output --num-proc 8`
1. Write an [OSW file](inputs.md#osw-json-file-defining-the-home) with an upgrade to the home
1. Create an HPXML model from the upgrade osw file: `openstudio run --workflow <upgraded_home.osw> --measures_only`
1. Calculate energy use from the uncalibrated upgraded home: `oshc run-sim --hpxml-filepath asdf_upgraded.xml`
1. Initialize the Calibrate object from this repo
    1. Use it to create an OSW to modify the xml with the changes from calibration: `calibration.osw`
1. Modify the upgraded xml to match the calibration work: `oshc modify-xml --workflow-file calibration.osw`
    1. Use the `calibration_results` from the `best_individual` of the final generation of calibration
    1. Remove whatever item(s) is/are being upgraded, since the upgrade overrides the calibration
1. Calculate energy use from the calibrated upgraded home: `oshc run-sim --hpxml-filepath asdf_upgraded.xml`
1. Read the energy simulation results from both the upgraded calibrated home and the existing calibrated home
