import contextlib
import json
import shutil
import statistics
import time
from pathlib import Path

from openstudio_hpxml_calibration.calibrate import Calibrate
from openstudio_hpxml_calibration.utils import (
    plot_absolute_error_series,
    plot_avg_penalty,
    plot_bias_error_series,
    plot_fuel_type_curve_fits,
    plot_min_penalty,
)


def main(filepath):
    filename = Path(filepath).stem
    test_config_filepath = Path(__file__).resolve().parent / "tests" / "data" / "test_config.yaml"
    output_filepath = Path(__file__).resolve().parent / "tests" / "calibration_results" / filename

    # Remove old results if they exist
    if output_filepath.exists():
        shutil.rmtree(output_filepath)

    output_filepath.mkdir(parents=True, exist_ok=True)

    cal = Calibrate(original_hpxml_filepath=filepath, config_filepath=test_config_filepath)
    start = time.time()
    (
        best_individual_dict,
        pop,
        logbook,
        best_bias_series,
        best_abs_series,
        weather_norm_reg_models,
        inv_model,
        existing_home_results,
    ) = cal.run_search(output_filepath=output_filepath)
    print(f"Evaluation took {time.time() - start:.2f} seconds")

    # Save the logbook
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
        "calibration_results": log_data,
    }

    logbook_path = output_filepath / "logbook.json"
    with open(logbook_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    # Min and avg penalties
    min_penalty = [entry["min"] for entry in logbook]
    avg_penalty = [entry["avg"] for entry in logbook]

    # plot calibration results
    plot_min_penalty(min_penalty, output_filepath)
    plot_avg_penalty(avg_penalty, output_filepath)
    plot_bias_error_series(logbook, output_filepath)
    plot_absolute_error_series(logbook, output_filepath)

    # Plot fuel type curve fits
    plot_fuel_type_curve_fits(inv_model, output_filepath, filename)


if __name__ == "__main__":
    test_hpxml_files = []
    ihmh_home_hpxml_dir = Path("test_hpxmls/ihmh_homes")
    ihmh_hpxml_files = ihmh_home_hpxml_dir.glob("ihmh4.xml")
    test_hpxml_files.extend(ihmh_hpxml_files)
    real_home_hpxml_dir = Path("test_hpxmls/real_homes")
    real_home_hpxml_files = real_home_hpxml_dir.glob("house21.xml")
    test_hpxml_files.extend(real_home_hpxml_files)
    output_path = Path(__file__).resolve().parent / "tests" / "calibration_results"

    gen_values = []

    for test_hpxml_file in test_hpxml_files:
        try:
            main(str(test_hpxml_file))
        except Exception as e:
            print(f"Failed on {test_hpxml_file.name}: {e}")
            continue

        # Derive expected logbook.json path
        filename_stem = test_hpxml_file.stem
        logbook_path = output_path / filename_stem / "logbook.json"

        if not logbook_path.exists():
            print(f"Logbook not found for {filename_stem}")
            continue

        try:
            with open(logbook_path) as f:
                logbook = json.load(f)
                if logbook:
                    final_gen = logbook["calibration_results"][-1].get("gen")
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
        output_txt_path = output_path / "average_calibration_performace.txt"
        output_txt_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        with open(output_txt_path, "w") as f:
            f.write(f"Average generations to solution: {avg_gen:.2f}\n")
    else:
        print("\nNo generation data collected.")
