# OpenStudio-HPXML calibration

A package to automatically calibrate an OS-HPXML model to provided utilities bills

## Developer installation & usage

- Clone the repository: `git clone https://github.com/NREL/OpenStudio-HPXML-Calibration.git`
- Move into the repository: `cd OpenStudio-HPXML-Calibration`

- [Uv](https://docs.astral.sh/uv/) is used to manage the project & dependencies (and may also be used to [manage Python](https://docs.astral.sh/uv/guides/install-python/) if you want). After cloning, ensure you have
[uv installed](https://docs.astral.sh/uv/getting-started/installation/), then run `uv sync` to install the package and all development dependencies.
  - Some Windows developers have reported version conflicts using the default strategy. If this occurs, consider changing the [resolution strategy](https://docs.astral.sh/uv/concepts/resolution/#resolution-strategy) using `uv sync --resolution=lowest-direct`
- Developers can then call `uv run pytest` to confirm all dev dependencies have been
installed and everything is working as expected.
- Activate [pre-commit](https://pre-commit.com/) (only required once, after cloning the repo) with: `uv run pre-commit install`. On your first commit it will install the pre-commit environments, then run pre-commit hooks at every commit.
- Before pushing to Github, run pre-commit on all files with `uv run pre-commit run -a` to highlight any linting/formatting errors that will cause CI to fail.
- Pycharm users may need to add Ruff as a [3rd-party plugin](https://docs.astral.sh/ruff/editors/setup/#via-third-party-plugin) or install it as an [external tool](https://docs.astral.sh/ruff/editors/setup/#pycharm) to their IDE to ensure linting & formatting is consistent.
- Developers can test in-process functionality by prepending `uv run` to a terminal command. For instance, to see the CLI help menu with local changes not yet committed, run: `uv run openstudio-hpxml-calibration --help`

## Testing

Can be run by calling: `uv run pytest`
