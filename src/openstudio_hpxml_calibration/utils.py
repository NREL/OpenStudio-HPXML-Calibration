import hashlib
import os
from pathlib import Path

import platformdirs
import yaml
from loguru import logger

OS_HPXML_PATH = Path(__file__).resolve().parent.parent / "OpenStudio-HPXML"


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
        logger.info(f"Config file {config_filepath} not found. Using default configuration.")
        return default_config
    else:
        with open(config_filepath) as f:
            config = yaml.safe_load(f)
        return _merge_with_defaults(config, default_config)
