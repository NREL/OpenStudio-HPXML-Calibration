import subprocess
from importlib.metadata import version
from pathlib import Path

from cyclopts import App

from .enums import Format, Granularity

OSHPXML_PATH = Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


app = App(
    version=version("openstudio-hpxml-calibration"),
    version_flags=["--version", "-v"],
    help="Calibrate an HPXML model to provided utility data using OpenStudio-HPXML",
)


@app.command
def openstudio_version() -> None:
    """Return the OpenStudio-HPXML, HPXML, OpenStudio, and EnergyPlus Versions"""
    resp = subprocess.run(
        [
            "openstudio",
            str(OSHPXML_PATH / "workflow" / "run_simulation.rb"),
            "--version",
        ],
        capture_output=True,
        check=True,
    )
    print(resp.stdout.decode())


@app.command
def run_sim(
    hpxml_filepath: str,
    output_format: Format | None = None,
    output_dir: str | None = None,
    granularity: Granularity | None = None,
) -> None:
    """Simulate an HPXML file using the OpenStudio-HPXML workflow

    Parameters
    ----------
    hpxml_filepath: str
        Path to the HPXML file to simulate
    output_format: str
        Output file format type. Default is csv.
    output_dir: str
        Output directory to save simulation results dir. Default is HPXML file dir.
    granularity: str
        Granularity of simulation results. Default is annual.
    """
    run_simulation_command = [
        "openstudio",
        str(OSHPXML_PATH / "workflow" / "run_simulation.rb"),
        "--xml",
        hpxml_filepath,
    ]
    if granularity is not None:
        granularity = [f"--{granularity.value}", "ALL"]
        run_simulation_command.extend(granularity)
    if output_format is not None:
        output_format = ["--output-format", output_format.value]
        run_simulation_command.extend(output_format)
    if output_dir is not None:
        output_dir = ["--output-dir", output_dir]
        run_simulation_command.extend(output_dir)
    subprocess.run(
        run_simulation_command,
        capture_output=True,
        check=True,
    )


@app.command
def modify_xml(workflow_file: Path) -> None:
    modify_xml_command = [
        "openstudio",
        "run",
        "--workflow",
        str(workflow_file),
        "--measures_only",
    ]

    subprocess.run(
        modify_xml_command,
        capture_output=True,
        check=True,
    )


if __name__ == "__main__":
    app()
