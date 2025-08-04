import json
import subprocess
import time
import zipfile
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
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
    debug: bool = False,
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
    if debug:
        # the run_simulation.rb script sets skip-validation to false by default.
        # By not including it here, we perform the validation.
        # We also add the --debug flag to enable debug mode for run_simulation.rb.
        debug_flags = ["--debug"]
    else:
        # Our default is to skip validation, for faster simulation runs.
        debug_flags = ["--skip-validation"]
    run_simulation_command.extend(debug_flags)

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


@app.command
def calibrate(
    hpxml_filepath: str,
    config_filepath: str | None = None,
    output_dir: str | None = None,
) -> None:
    """
    Run calibration using a genetic algorithm on an HPXML file.

    Parameters
    ----------
    hpxml_filepath: str
        Path to the HPXML file
    config_filepath: str
        Optional path to calibration config file
    output_dir: str
        Optional output directory to save results
    """

    from openstudio_hpxml_calibration.calibrate import Calibrate

    filename = Path(hpxml_filepath).stem
    cal = Calibrate(original_hpxml_filepath=hpxml_filepath, config_filepath=config_filepath)

    start = time.time()
    best_individual, pop, logbook, best_bias_series, best_abs_series = cal.run_ga_search()
    logger.info(f"Calibration took {time.time() - start:.2f} seconds")

    # Output directory
    if output_dir is None:
        output_filepath = (
            Path(__file__).resolve().parent.parent / "tests" / "ga_search_results" / filename
        )
    else:
        output_filepath = Path(output_dir)
    output_filepath.mkdir(parents=True, exist_ok=True)

    # Save logbook
    logbook_path = output_filepath / "logbook.json"
    with open(logbook_path, "w", encoding="utf-8") as f:
        json.dump(logbook, f, indent=2)

    # Min and avg penalties
    min_penalty = [entry["min"] for entry in logbook]
    avg_penalty = [entry["avg"] for entry in logbook]

    # Plot Min Penalty
    plt.figure(figsize=(10, 6))
    plt.plot(min_penalty, label="Min Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Min Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "min_penalty_plot.png"))

    # Plot Avg Penalty
    plt.figure(figsize=(10, 6))
    plt.plot(avg_penalty, label="Avg Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Avg Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "avg_penalty_plot.png"))

    # Bias error series
    best_bias_series = {}
    for entry in logbook:
        for key, value in entry.items():
            if key.startswith("bias_error_"):
                best_bias_series.setdefault(key, []).append(value)

    plt.figure(figsize=(12, 6))
    for key, values in best_bias_series.items():
        label = key.replace("bias_error_", "")
        plt.plot(values, label=label)
    plt.xlabel("Generation")
    plt.ylabel("Bias Error (%)")
    plt.title("Per-End-Use Bias Error Over Generations")
    plt.legend(loc="best", fontsize="small")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "bias_error_plot.png"), bbox_inches="tight")

    # Absolute error series
    best_abs_series = {}
    for entry in logbook:
        for key, value in entry.items():
            if key.startswith("abs_error_"):
                best_abs_series.setdefault(key, []).append(value)

    electric_keys = [k for k in best_abs_series if "electricity" in k]
    gas_keys = [k for k in best_abs_series if "natural gas" in k]

    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()
    colors = plt.cm.tab20.colors

    for i, key in enumerate(electric_keys):
        ax1.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (kWh)",
            color=colors[i % len(colors)],
        )
    for i, key in enumerate(gas_keys):
        ax2.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (MBtu)",
            color=colors[(i + len(electric_keys)) % len(colors)],
        )

    ax1.set_xlabel("Generation")
    ax1.set_ylabel("Electricity Abs Error (kWh)", color="blue")
    ax2.set_ylabel("Gas Abs Error (MBtu)", color="red")
    plt.title("Per-End-Use Absolute Errors Over Generations")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize="small")
    ax1.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "absolute_error_plot.png"), bbox_inches="tight")


if __name__ == "__main__":
    app()
