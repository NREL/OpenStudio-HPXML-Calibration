import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def generate_cvrmse_comparison_plot():
    results_dir = (
        Path(__file__).resolve().parent.parent / "tests" / "results" / "weather_normalization"
    )
    summary_file = results_dir / "cvrmse_summary.json"
    all_jsons = list(results_dir.glob("*.json"))

    model_cvrmses = {}

    for jf in all_jsons:
        if jf.name == summary_file.name:
            continue
        with open(jf) as f:
            partial = json.load(f)
            model_cvrmses.update(partial)

    # Save merged summary
    with open(summary_file, "w") as f:
        json.dump(model_cvrmses, f, indent=2)

    model_names = list(model_cvrmses.keys())
    cvrmse_values = list(model_cvrmses.values())

    fig, ax = plt.subplots(figsize=(12, max(6, len(model_names) * 0.3)))
    bars = ax.barh(model_names, cvrmse_values, color="skyblue")

    ax.set_xlabel("CVRMSE")
    ax.set_title("CVRMSE comparison across all test HPXMLs")
    ax.invert_yaxis()

    for bar, value in zip(bars, cvrmse_values):
        ax.text(value + 0.005, bar.get_y() + bar.get_height() / 2, f"{value:.2%}", va="center")

    fig.tight_layout()
    fig.savefig(results_dir / "cvrmse_comparison.png", dpi=200)
    plt.close(fig)

    # Save average CVRMSE
    average_cvrmse = np.mean(cvrmse_values)
    with open(results_dir / "cvrmse_average.txt", "w") as f:
        f.write(f"Average CVRMSE: {average_cvrmse:.2%}")

    if average_cvrmse >= 0.30:
        raise ValueError(f"Average CVRMSE too high: {average_cvrmse:.2%}")
