# OpenStudio™ HPXML Calibration

[![ci](https://github.com/NREL/OpenStudio-HPXML-Calibration/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NREL/OpenStudio-HPXML-Calibration/actions/workflows/ci.yml)

A package to automatically calibrate an [OpenStudio-HPXML](https://github.com/NREL/OpenStudio-HPXML) residential building model against utility bills.

The implementation relies heavily on [BPI-2400-S-2015 v.2 Standard Practice for Standardized Qualification of Whole-House Energy Savings Predictions by Calibration to Energy Use](https://www.bpi.org/__cms/docs/20240523_BPI-2400-S-2015_Delta_Standard_v2.pdf).
However, it is not currently a complete implementation of BPI-2400.

## Documentation & usage

Full documentation is available at <https://NREL.github.io/OpenStudio-HPXML-Calibration>

Create a custom config file (based on [`default_calibration_config.yaml`](https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/src/openstudio_hpxml_calibration/default_calibration_config.yaml)) that is specific to the home being calibrated.

Then run:
`uv run openstudio-hpxml-calibration calibrate --hpxml-filepath hpxml.xml --config-filepath my_config.yaml`

See `uv run openstudio-hpxml-calibration calibrate --help` or `uv run openstudio-hpxml-calibration --help` for more options.

## Developer installation

- Clone the repository: `git clone https://github.com/NREL/OpenStudio-HPXML-Calibration.git`
- Move into the repository: `cd OpenStudio-HPXML-Calibration`
- Install [OpenStudio 3.10.0](https://github.com/NREL/OpenStudio/releases/tag/v3.10.0)

- [Uv](https://docs.astral.sh/uv/) is used to manage the project & dependencies (and may also be used to [manage Python](https://docs.astral.sh/uv/guides/install-python/) if you want). After cloning, ensure you have
[uv installed](https://docs.astral.sh/uv/getting-started/installation/), then run `uv sync` to install the package and all development dependencies.
    - Some Windows developers have reported version conflicts using the default strategy. If this occurs, consider changing the [resolution strategy](https://docs.astral.sh/uv/concepts/resolution/#resolution-strategy) using `uv sync --resolution=lowest-direct`
- Download all weather files using `uv run openstudio-hpxml-calibration download-weather`
- Developers can then call `uv run pytest` to confirm all dev dependencies have been installed and everything is working as expected. (If you need to restrict the number of concurrent workers, you can use e.g. `uv run pytest -n <NUM>`.)
- Activate [pre-commit](https://pre-commit.com/) (only required once, after cloning the repo) with: `uv run pre-commit install`. On your first commit it will install the pre-commit environments, then run pre-commit hooks at every commit.
- Before pushing to Github, run pre-commit on all files with `uv run pre-commit run -a` to highlight any linting/formatting errors that will cause CI to fail.
- Pycharm users may need to add Ruff as a [3rd-party plugin](https://docs.astral.sh/ruff/editors/setup/#via-third-party-plugin) or install it as an [external tool](https://docs.astral.sh/ruff/editors/setup/#pycharm) to their IDE to ensure linting & formatting is consistent.
- Developers can test in-process functionality by prepending `uv run` to a terminal command. For instance, to see the CLI help menu with local changes not yet committed, run: `uv run openstudio-hpxml-calibration --help`

### Alternative Dev Container Environment

There's a Dev Container configuration in this repo which installs all the necessary dependencies in a docker container and attaches to VSCode to it. To use it:

- Install [VSCode](https://code.visualstudio.com/)
- Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.
- Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) or something compatible.
- Click the little blue "><" icon in the lower left of VSCode, and select "Reopen in Container". The window will reload. It may take a few minutes the first time.

## Testing

Project tests can be run with `uv run pytest` from the repo root. (If you need to restrict the number of concurrent workers, you can use e.g. `uv run pytest -n <NUM>`.)

Ruby Measure tests can be run with `openstudio src/measures/ModifyXML/tests/modify_xml_test.rb`

## Developing documentation

During development we can serve docs locally and view updates as they are made.

1. Start a documentation update branch: `git switch -c <branch_name>`
1. `uv run mkdocs serve`
1. Point browser to <http://127.0.0.1:8000/>

- To deploy, push a commit in the `docs` folder to the `main` branch
- Wait a few minutes, then verify the new documentation on the [docs website](https://NREL.github.io/OpenStudio-HPXML-Calibration)

## License

This project is available under a BSD-3-like license, which is a free, open-source, and permissive license. For more information, check out the [license file](https://github.com/NREL/OpenStudio-HPXML-Calibration/blob/main/LICENSE.md).

This project is NREL Software Record `SWR-25-94`
