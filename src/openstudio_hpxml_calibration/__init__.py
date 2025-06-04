import subprocess
import zipfile
from importlib.metadata import version
from pathlib import Path

import requests
from cyclopts import App
from loguru import logger
from tqdm import tqdm

from openstudio_hpxml_calibration.utils import OS_HPXML_PATH, calculate_sha256, get_cache_dir

from .enums import Format, Granularity

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
            str(OS_HPXML_PATH / "workflow" / "run_simulation.rb"),
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
        Granularity of simulation results. Annual results returned if not provided.
    """
    run_simulation_command = [
        "openstudio",
        str(OS_HPXML_PATH / "workflow" / "run_simulation.rb"),
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

    logger.debug(f"Running command: {' '.join(run_simulation_command)}")
    subprocess.run(
        run_simulation_command,
        capture_output=True,
        check=True,
    )


@app.command
def modify_xml(workflow_file: Path) -> None:
    """Modify the XML file using the OpenStudio-HPXML workflow

    Parameters
    ----------
    workflow_file: Path
        Path to the workflow file (osw) that defines the modifications to be made
    """
    modify_xml_command = [
        "openstudio",
        "run",
        "--workflow",
        str(workflow_file),
        "--measures_only",
    ]

    logger.debug(f"Running command: {' '.join(modify_xml_command)}")
    subprocess.run(
        modify_xml_command,
        capture_output=True,
        check=True,
    )


@app.command
def download_weather() -> None:
    # TODO: move the code for this to a separate module
    """Download TMY3 weather files from NREL

    Parameters
    ----------
    None
    """
    weather_files_url = "https://data.nrel.gov/system/files/128/tmy3s-cache-csv.zip"
    weather_zip_filename = weather_files_url.split("/")[-1]
    weather_zip_sha256 = "58f5d2821931e235de34a5a7874f040f7f766b46e5e6a4f85448b352de4c8846"

    # Download file
    cache_dir = get_cache_dir()
    weather_zip_filepath = cache_dir / weather_zip_filename
    if not (
        weather_zip_filepath.exists()
        and calculate_sha256(weather_zip_filepath) == weather_zip_sha256
    ):
        resp = requests.get(weather_files_url, stream=True, timeout=10)
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        block_size = 8192
        with (
            tqdm(total=total_size, unit="iB", unit_scale=True, desc=weather_zip_filename) as pbar,
            open(weather_zip_filepath, "wb") as f,
        ):
            for chunk in resp.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

    # Extract weather files
    print(f"zip saved to: {weather_zip_filepath}")
    weather_dir = OS_HPXML_PATH / "weather"
    print(f"Extracting weather files to {weather_dir}")
    with zipfile.ZipFile(weather_zip_filepath, "r") as zf:
        for filename in tqdm(zf.namelist(), desc="Extracting epws"):
            if filename.endswith(".epw") and not (weather_dir / filename).exists():
                zf.extract(filename, path=weather_dir)


if __name__ == "__main__":
    app()
