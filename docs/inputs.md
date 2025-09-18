# Inputs

## OSW (json) file defining the home

An example file can be found in `tests/data/ihmh3_existing_hpxml.osw`

## Utility consumption csv file

| Consumption | StartDateTime | EndDateTime | UnitofMeasure | FuelType  |
|:-----------:|:-------------:|:-----------:|:-------------:|:---------:|
|1000         | 2/1/23        | 2/28/23     |kWh            |electricity|
|1000         | 3/1/23        | 3/31/23     |kWh            |electricity|
|120          | 1/1/23        | 1/31/23     |therms         |natural gas|

## Config file

- The default config can be found at `src/openstudio_hpxml_calibration/default_calibration_config.yaml`
- That should probably be left as is, and for each home you create an override config specific for that home
- An example override config can be found at `tests/data/test_config.yaml`
