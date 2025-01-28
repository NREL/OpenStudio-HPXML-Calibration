import pathlib
import subprocess

from cyclopts import App

app = App()

oshpxml_path = pathlib.Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


@app.command
def openstudio_version() -> None:
    """Return the OpenStudio-HPXML, HPXML, OpenStudio, and EnergyPlus Versions"""
    resp = subprocess.run(
        [
            "openstudio",
            str(oshpxml_path / "workflow" / "run_simulation.rb"),
            "--version",
        ],
        capture_output=True,
        check=True,
    )
    print(resp.stdout.decode())


if __name__ == "__main__":
    app()
