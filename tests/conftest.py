import sys
from pathlib import Path

import eeweather.cache as ec
import matplotlib as mpl
import pytest

mpl.use("Agg")  # Use non-interactive backend for testing

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.post_process import generate_cvrmse_comparison_plot


@pytest.fixture(scope="session")
def results_dir(worker_id):
    """Session-scoped fixture to create and clean results directory, xdist-safe."""
    results_dir = Path(__file__).resolve().parent / "results"

    base_worker = False
    # if worker_id in ("gw0", "master") and results_dir.is_dir():
    #     base_worker = True
    #     shutil.rmtree(results_dir)

    results_dir.mkdir(exist_ok=True)

    with open(results_dir / f"{worker_id}_checkin.txt", "a") as f:
        f.write(f"{worker_id}\nbase_worker = {base_worker}")

    sub_dirs = ["weather_normalization"]
    for dir in sub_dirs:
        (results_dir / dir).mkdir(parents=True, exist_ok=True)

    return results_dir


def pytest_sessionfinish(session, exitstatus):
    """Hook to run after all tests finish."""
    generate_cvrmse_comparison_plot()


@pytest.fixture(autouse=True)
def isolate_eeweather_cache(tmp_path, monkeypatch):
    """Isolate the eeweather cache directory per worker"""
    monkeypatch.setattr(ec.KeyValueStore, "_get_url", lambda _: f"sqlite:///{tmp_path}/cache.db")
