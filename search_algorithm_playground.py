import json
import shutil
import statistics
import time
from pathlib import Path

import matplotlib.pyplot as plt

from openstudio_hpxml_calibration.calibrate import Calibrate


def main(filepath):
    filename = Path(filepath).stem
    output_filepath = Path(__file__).resolve().parent / "tests" / "ga_search_results" / filename

    # Remove old results if they exist
    if output_filepath.exists():
        shutil.rmtree(output_filepath)

    output_filepath.mkdir(parents=True, exist_ok=True)

    cal = Calibrate(
        original_hpxml_filepath=filepath,
    )
    start = time.time()
    best_individual, pop, logbook, best_bias_series, best_abs_series = cal.run_ga_search(
        output_filepath=output_filepath
    )
    print(f"Evaluation took {time.time() - start:.2f} seconds")

    # Save the logbook
    log_data = []
    for gen, record in enumerate(logbook):
        log_data.append(record)

    logbook_path = output_filepath / "logbook.json"
    with open(logbook_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

    # Extract penalties per generation
    min_penalty = [entry["min"] for entry in logbook]
    avg_penalty = [entry["avg"] for entry in logbook]

    # Extract bias error series per end use
    best_bias_series = {}
    for entry in logbook:
        for key, value in entry.items():
            if key.startswith("bias_error_"):
                if key not in best_bias_series:
                    best_bias_series[key] = []
                best_bias_series[key].append(value)

    # Plot minimum penalty over generations
    plt.figure(figsize=(10, 6))
    plt.plot(min_penalty, label="Min Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Hall-of-Fame Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "min_penalty_plot.png"))
    plt.close()

    # Plot average penalty over generations
    plt.figure(figsize=(10, 6))
    plt.plot(avg_penalty, label="Avg Penalty")
    plt.xlabel("Generation")
    plt.ylabel("Penalty")
    plt.title("Average Penalty Over Generations")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "avg_penalty_plot.png"))
    plt.close()

    # Plot bias error per end-use
    plt.figure(figsize=(12, 6))
    for key, values in best_bias_series.items():
        label = key.replace("bias_error_", "")
        plt.plot(values, label=label)
    plt.xlabel("Generation")
    plt.ylabel("Bias Error (%)")
    plt.title("Hall-of-Fame Per-End-Use Bias Error Over Generations")
    plt.legend(loc="best", fontsize="small")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "bias_error_plot.png"), bbox_inches="tight")
    plt.close()

    # Plot absolute error per end-use
    best_abs_series = {}
    # Build series from each generation entry
    for entry in logbook:
        for key, value in entry.items():
            if key.startswith("abs_error_"):
                if key not in best_abs_series:
                    best_abs_series[key] = []
                best_abs_series[key].append(value)
    # Separate keys into electricity (kWh) and gas (MBtu)
    electric_keys = [k for k in best_abs_series if "electricity" in k]
    gas_keys = [k for k in best_abs_series if "natural gas" in k]
    # Plotting
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()
    colors = plt.cm.tab20.colors
    # Plot electricity errors
    for i, key in enumerate(electric_keys):
        ax1.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (kWh)",
            color=colors[i % len(colors)],
        )
    # Plot fossil fuel errors
    for i, key in enumerate(gas_keys):
        ax2.plot(
            best_abs_series[key],
            label=key.replace("abs_error_", "") + " (MBtu)",
            color=colors[(i + len(electric_keys)) % len(colors)],
        )
    # Labeling
    ax1.set_xlabel("Generation")
    ax1.set_ylabel("Absolute Error for Electricity End-Uses (kWh)", color="blue")
    ax2.set_ylabel("Absolute Error for Natural Gas End-Uses (MBtu)", color="red")
    plt.title("Per-End-Use Absolute Errors Over Generations")
    # Combine legends
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="best", fontsize="small")
    # Grid and save
    ax1.grid(True)
    plt.tight_layout()
    plt.savefig(str(output_filepath / "absolute_error_plot.png"), bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    test_hpxml_files = []
    ihmh_home_hpxml_dir = Path("test_hpxmls/ihmh_homes")
    ihmh_hpxml_files = ihmh_home_hpxml_dir.glob("*.xml")
    test_hpxml_files.extend(ihmh_hpxml_files)
    real_home_hpxml_dir = Path("test_hpxmls/real_homes")
    real_home_hpxml_files = real_home_hpxml_dir.glob("*.xml")
    test_hpxml_files.extend(real_home_hpxml_files)

    gen_values = []

    for test_hpxml_file in test_hpxml_files:
        try:
            main(str(test_hpxml_file))
        except Exception as e:
            print(f"Failed on {test_hpxml_file.name}: {e}")
            continue

        # Derive expected logbook.json path
        filename_stem = test_hpxml_file.stem
        logbook_path = (
            Path(__file__).resolve().parent
            / "tests"
            / "ga_search_results"
            / filename_stem
            / "logbook.json"
        )

        if not logbook_path.exists():
            print(f"Logbook not found for {filename_stem}")
            continue

        try:
            with open(logbook_path) as f:
                logbook = json.load(f)
                if isinstance(logbook, list) and logbook:
                    final_gen = logbook[-1].get("gen")
                    if final_gen is not None:
                        gen_values.append(final_gen)
                        print(f"Final gen for {filename_stem}: {final_gen}")
                    else:
                        print(f"No 'gen' key in final record of {filename_stem}")
                else:
                    print(f"Empty or invalid logbook for {filename_stem}")
        except Exception as e:
            print(f"Error reading logbook for {filename_stem}: {e}")

    if gen_values:
        avg_gen = statistics.mean(gen_values)
        print(f"\nAverage generations to solution: {avg_gen:.2f}")

        # Write the result to a text file
        output_txt_path = (
            Path(__file__).resolve().parent
            / "tests"
            / "ga_search_results"
            / "average_ga_performace.txt"
        )
        output_txt_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        with open(output_txt_path, "w") as f:
            f.write(f"Average generations to solution: {avg_gen:.2f}\n")
    else:
        print("\nNo generation data collected.")
