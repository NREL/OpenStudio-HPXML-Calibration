import hashlib
import os
import subprocess
import zipfile
from enum import Enum
from importlib.metadata import version
from pathlib import Path

import platformdirs
import requests
from cyclopts import App
from tqdm import tqdm

OSHPXML_PATH = Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


class Granularity(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class Format(str, Enum):
    CSV = "csv"
    JSON = "json"
    MSGPACK = "msgpack"
    CSV_DVIEW = "csv_dview"


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


def get_cache_dir() -> Path:
    cache_dir = Path(platformdirs.user_cache_dir("oshit"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def calculate_sha256(filepath: os.PathLike, block_size: int = 65536):
    """Calculates the SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(block_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


@app.command
def download_weather() -> None:
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
    weather_dir = OSHPXML_PATH / "weather"
    with zipfile.ZipFile(weather_zip_filepath, "r") as zf:
        for filename in tqdm(zf.namelist(), desc="Extracting epws"):
            if filename.endswith(".epw") and not (weather_dir / filename).exists():
                zf.extract(filename, path=weather_dir)


if __name__ == "__main__":
    app()
