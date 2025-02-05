import subprocess
from pathlib import Path

from cyclopts import App

app = App()

oshpxml_path = Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


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


@app.command
def run_sim(hpxml_filepath, output_format="json", output_dir=Path.cwd()) -> None:
    """Simulate an HPXML file using the OpenStudio-HPXML workflow"""
    subprocess.run(
        [
            "openstudio",
            oshpxml_path / "workflow" / "run_simulation.rb",
            "--xml",
            hpxml_filepath,
            f"--output-format={output_format}",
            f"--output-dir={output_dir}",
        ],
        capture_output=True,
        check=True,
    )


if __name__ == "__main__":
    app()
