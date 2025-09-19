import hashlib
import os
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import platformdirs
import requests
import yaml
from loguru import logger
from matplotlib.ticker import MaxNLocator
from tqdm import tqdm

OS_HPXML_PATH = Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


def get_cache_dir() -> Path:
    cache_dir = Path(platformdirs.user_cache_dir("oshc"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def calculate_sha256(filepath: os.PathLike, block_size: int = 65536):
    """Calculates the SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(block_size), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _merge_with_defaults(user_config, default_config: dict) -> dict:
    """Merge default values into user's config"""
    if not isinstance(user_config, dict):
        return user_config
    merged = default_config.copy()
    for key, val in user_config.items():
        if key in merged and isinstance(merged[key], dict):
            merged[key] = _merge_with_defaults(val, merged[key])
        else:
            merged[key] = val
    return merged


def _load_config(config_filepath: Path | None = None) -> dict:
    default_config_filepath = Path(__file__).resolve().parent / "default_calibration_config.yaml"
    with open(default_config_filepath) as f:
        default_config = yaml.safe_load(f)
    if not config_filepath or not Path(config_filepath).exists():
        raise FileNotFoundError(f"Config file {config_filepath} not found.")
    else:
        with open(config_filepath) as f:
            config = yaml.safe_load(f)
        return _merge_with_defaults(config, default_config)


def plot_fuel_type_curve_fits(inv_model, output_filepath, filename: str) -> None:
    """
    Plot fuel type curve fits for a given inverse model.

    Parameters
    ----------
    inv_model: object
        Inverse model with regression_models, bills_weather_by_fuel_type_in_btu, get_model
    output_filepath: Path
        Directory where plots should be saved
    filename: str
        Base filename used in plot titles and file naming
    """
    for fuel_type, _ in inv_model.regression_models.items():
        model = inv_model.get_model(fuel_type)
        bills_temps = inv_model.bills_weather_by_fuel_type_in_btu[fuel_type]
        temps_range = np.linspace(bills_temps["avg_temp"].min(), bills_temps["avg_temp"].max(), 500)
        fig = plt.figure(figsize=(8, 6))
        daily_consumption_pred = model(temps_range)
        cvrmse = model.calc_cvrmse(bills_temps)
        num_params = len(model.parameters)

        if num_params == 5:
            plt.plot(
                temps_range,
                daily_consumption_pred,
                label=(
                    f"{model.MODEL_NAME}, CVRMSE = {cvrmse:.1%}\n Model parameters:\n"
                    f"1) Baseload value: {model.parameters[0]:.3f}\n"
                    f"2) Slopes: {model.parameters[1]:.3f}, {model.parameters[2]:.3f}\n"
                    f"3) Inflection points: {model.parameters[-2]:.1f}, {model.parameters[-1]:.1f}"
                ),
            )
        elif num_params == 3:
            plt.plot(
                temps_range,
                daily_consumption_pred,
                label=(
                    f"{model.MODEL_NAME}, CVRMSE = {cvrmse:.1%}\n Model parameters:\n"
                    f"1) Baseload value: {model.parameters[0]:.3f}\n"
                    f"2) Slope: {model.parameters[1]:.3f}\n"
                    f"3) Inflection point: {model.parameters[-1]:.1f}"
                ),
            )

        plt.scatter(
            bills_temps["avg_temp"],
            bills_temps["daily_consumption"],
            label="data",
            color="darkgreen",
        )
        plt.title(f"{filename} {fuel_type.value}")
        plt.xlabel("Avg Daily Temperature [degF]")
        plt.ylabel("Daily Consumption [BTU]")
        plt.legend()
        fig.savefig(output_filepath / f"{filename}_{fuel_type.value}_curve_fit.png", dpi=200)
        plt.close(fig)


def plot_min_penalty(min_penalty, output_filepath, filename):
    plt.figure(figsize=(10, 6))
    plt.plot(min_penalty, label="Min Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Min Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig(str(output_filepath / f"{filename}_min_penalty_plot.png"))
    plt.close()


def plot_avg_penalty(avg_penalty, output_filepath, filename):
    plt.figure(figsize=(10, 6))
    plt.plot(avg_penalty, label="Avg Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Avg Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig(str(output_filepath / f"{filename}_avg_penalty_plot.png"))
    plt.close()


def plot_bias_error_series(logbook, output_filepath, filename):
    best_bias_series = {}
    for entry in logbook:
        for key, value in entry.items():
            if value == 0:
                continue
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
    plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig(str(output_filepath / f"{filename}_bias_error_plot.png"), bbox_inches="tight")
    plt.close()


def plot_absolute_error_series(logbook, output_filepath, filename):
    best_abs_series = {}
    for entry in logbook:
        for key, value in entry.items():
            if value == 0:
                continue
            if key.startswith("abs_error_"):
                best_abs_series.setdefault(key, []).append(value)

    electric_keys = [k for k in best_abs_series if "electricity" in k]
    fuel_keys = [
        k for k in best_abs_series if "natural gas" in k or "fuel oil" in k or "propane" in k
    ]

    _fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()
    colors = plt.cm.tab20.colors

    for i, key in enumerate(electric_keys):
        ax1.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (kWh)",
            color=colors[i % len(colors)],
        )
    for i, key in enumerate(fuel_keys):
        ax2.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (MBtu)",
            color=colors[(i + len(electric_keys)) % len(colors)],
        )

    ax1.set_xlabel("Generation")
    ax1.set_ylabel("Electricity Abs Error (kWh)", color="blue")
    ax2.set_ylabel("Fossil Fuel Abs Error (MBtu)", color="red")
    plt.title("Per-End-Use Absolute Errors Over Generations")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize="small")
    ax1.grid(True)
    plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True))
    plt.tight_layout()
    plt.savefig(str(output_filepath / f"{filename}_absolute_error_plot.png"), bbox_inches="tight")
    plt.close()


def get_tmy3_weather():
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
    logger.debug(f"zip saved to: {weather_zip_filepath}")
    weather_dir = OS_HPXML_PATH / "weather"
    logger.debug(f"Extracting weather files to {weather_dir}")
    with zipfile.ZipFile(weather_zip_filepath, "r") as zf:
        for filename in tqdm(zf.namelist(), desc="Extracting epws"):
            if filename.endswith(".epw") and not (weather_dir / filename).exists():
                zf.extract(filename, path=weather_dir)
