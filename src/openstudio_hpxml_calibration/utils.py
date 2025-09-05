import hashlib
import os
import zipfile
from pathlib import Path

import platformdirs
import requests
import yaml
from loguru import logger
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
    default_config_filepath = Path(__file__).resolve().parent / "default_ga_config.yaml"
    with open(default_config_filepath) as f:
        default_config = yaml.safe_load(f)
    if not config_filepath or not Path(config_filepath).exists():
        logger.info(f"Config file {config_filepath} not found. Using default configuration.")
        return default_config
    else:
        with open(config_filepath) as f:
            config = yaml.safe_load(f)
        return _merge_with_defaults(config, default_config)


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
