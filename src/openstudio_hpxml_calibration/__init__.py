import subprocess
from pathlib import Path

from cyclopts import App

app = App(help="Calibrate an HPXML model to provided utility data using OpenStudio-HPXML")

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
def run_sim(hpxml_filepath, output_format=None, output_dir=None, granularity=None) -> None:
    """Simulate an HPXML file using the OpenStudio-HPXML workflow

    Parameters
    ----------
    hpxml_filepath: str
        Path to the HPXML file to simulate
    output_format: str
        Output file format type (csv, json, msgpack, csv_dview). Default is csv
    output_dir: str
        Output directory to save simulation results. Default is HPXML file dir
    granularity: str
        Granularity of simulation results (hourly, daily, monthly). Default is annual
    """
    run_simulation_command = ["openstudio", str(oshpxml_path / "workflow" / "run_simulation.rb"), "--xml", hpxml_filepath]
    if granularity is not None:
        granularity = f"--{granularity} ALL"
        run_simulation_command.extend(granularity.split())
    if output_format is not None:
        output_format = ["--output-format", output_format]
        run_simulation_command.extend(output_format)
    if output_dir is not None:
        output_dir = ["--output-dir", output_dir]
        run_simulation_command.extend(output_dir)
    subprocess.run(
        run_simulation_command,
        capture_output=True,
        check=True,
    )


if __name__ == "__main__":
    app()
