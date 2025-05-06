import hashlib
import os
from pathlib import Path

import platformdirs

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


def convert_c_to_f(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (temp_c * 9 / 5) + 32


def convert_mmbtu_to_kwh(mmbtu: float) -> float:
    """Convert MMBtu to kWh."""
    return mmbtu * 293.07107
