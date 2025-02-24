from pathlib import Path

import pytest


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
