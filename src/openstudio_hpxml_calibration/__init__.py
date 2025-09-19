import contextlib
import json
import shutil
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter
from loguru import logger

from openstudio_hpxml_calibration.utils import (
    OS_HPXML_PATH,
    get_tmy3_weather,
    plot_absolute_error_series,
    plot_avg_penalty,
    plot_bias_error_series,
    plot_fuel_type_curve_fits,
    plot_min_penalty,
)

from .enums import Format, Granularity

app = App(
    version=version("openstudio-hpxml-calibration"),
    version_flags=["--version", "-V"],
    help="Calibrate an HPXML model to provided utility data using OpenStudio-HPXML",
)


def set_log_level(verbose: int = 0) -> None:
    logger.remove()
    if verbose > 2:
        logger.add(sys.stderr, level="TRACE")
    elif verbose == 2:
        logger.add(sys.stderr, level="DEBUG")
    elif verbose == 1:
        logger.add(sys.stderr, level="INFO")
    else:
        logger.add(sys.stderr, level="WARNING")


@app.command
def openstudio_version(
    verbose: Annotated[list[bool], Parameter(alias="-v")] = (),
) -> None:
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
    validate: bool = False,
    verbose: Annotated[list[bool], Parameter(alias="-v")] = (),
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
    validate: flag
        Enable validation of the HPXML file before simulation.
    verbose: flag
        Enable verbose logging. Repeat flag for more verbosity.
    """
    verbosity = sum(verbose)
    set_log_level(verbosity)
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
    if validate:
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
def modify_xml(
    workflow_file: Path,
    verbose: Annotated[list[bool], Parameter(alias="-v")] = (),
) -> None:
    """Modify the XML file using the OpenStudio-HPXML workflow

    Parameters
    ----------
    workflow_file: Path
        Path to the workflow file (osw) that defines the modifications to be made
    verbose: flag
        Enable verbose logging. Repeat flag for more verbosity.
    """
    verbosity = sum(verbose)
    set_log_level(verbosity)
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
def download_weather(
    verbose: Annotated[list[bool], Parameter(alias="-v")] = (),
) -> None:
    """Download TMY3 weather files from NREL"""
    verbosity = sum(verbose)
    set_log_level(verbosity)
    get_tmy3_weather()


@app.command
def calibrate(
    hpxml_filepath: str,
    csv_bills_filepath: str | None = None,
    config_filepath: str | None = None,
    output_dir: str | None = None,
    num_proc: int | None = None,
    save_all_results: bool = False,
    verbose: Annotated[list[bool], Parameter(alias="-v")] = (),
) -> None:
    """
    Run calibration using a genetic algorithm on an HPXML file.

    Parameters
    ----------
    hpxml_filepath: str
        Path to the HPXML file
    csv_bills_filepath: str
        Optional path to utility bill CSV file
    config_filepath: str
        Optional path to calibration config file
    output_dir: str
        Optional output directory to save results
    num_proc: int
        Optional number of processors for parallel simulations
    save_all_results: bool
        Whether to save all simulation results. Default is False.
    verbose: flag
        Enable verbose logging. Repeat flag for more verbosity.
    """

    verbosity = sum(verbose)
    set_log_level(verbosity)
    from openstudio_hpxml_calibration.calibrate import Calibrate

    filename = Path(hpxml_filepath).stem

    if output_dir is None:
        output_filepath = (
            Path(__file__).resolve().parent.parent.parent
            / "tests"
            / "calibration_results"
            / filename
        )
    else:
        output_filepath = Path(output_dir)
    # Remove old output_filepath if it exists
    if output_filepath.exists() and output_filepath.is_dir():
        shutil.rmtree(output_filepath)
    output_filepath.mkdir(parents=True, exist_ok=True)

    cal = Calibrate(
        original_hpxml_filepath=hpxml_filepath,
        config_filepath=config_filepath,
        csv_bills_filepath=csv_bills_filepath,
    )

    start = time.time()
    (
        _best_individual_dict,
        _pop,
        logbook,
        _best_bias_series,
        _best_abs_series,
        weather_norm_reg_models,
        existing_home_results,
        calibration_success,
    ) = cal.run_search(
        num_proc=num_proc, output_filepath=output_filepath, save_all_results=save_all_results
    )
    print(f"Calibration took {time.time() - start:.2f} seconds")

    # Save logbook
    log_data = []
    json_keys = [
        "best_individual",
        "best_individual_sim_results",
        "parameter_choice_stats",
        "simulation_result_stats",
        "existing_home",
        "existing_home_sim_results",
        "all_simulation_results",
    ]
    for record in logbook:
        rec = record.copy()
        for key in json_keys:
            if key in rec and isinstance(rec[key], str):
                with contextlib.suppress(json.JSONDecodeError):
                    rec[key] = json.loads(rec[key])
        log_data.append(rec)
    parsed_existing_home = {}
    for key in json_keys:
        if key in existing_home_results and isinstance(existing_home_results[key], str):
            with contextlib.suppress(json.JSONDecodeError):
                parsed_existing_home[key] = json.loads(existing_home_results[key])

    output_data = {
        "weather_normalization_results": weather_norm_reg_models,
        "existing_home_results": parsed_existing_home,
        "calibration_success": calibration_success,
        "calibration_results": log_data,
    }

    logbook_path = output_filepath / "logbook.json"
    with open(logbook_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    # Min and avg penalties
    min_penalty = [entry["min"] for entry in logbook]
    avg_penalty = [entry["avg"] for entry in logbook]

    # plot calibration results
    plot_min_penalty(min_penalty, output_filepath, filename)
    plot_avg_penalty(avg_penalty, output_filepath, filename)
    plot_bias_error_series(logbook, output_filepath, filename)
    plot_absolute_error_series(logbook, output_filepath, filename)

    # Plot fuel type curve fits
    plot_fuel_type_curve_fits(cal.inv_model, output_filepath, filename)


if __name__ == "__main__":
    app()
