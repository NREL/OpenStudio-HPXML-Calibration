import copy
import json
import math
import multiprocessing
import random
import shutil
import statistics
import tempfile
import time
import uuid
from datetime import datetime as dt
from datetime import timedelta
from pathlib import Path

import pandas as pd
from deap import algorithms, base, creator, tools
from loguru import logger
from pathos.multiprocessing import ProcessingPool as Pool

from openstudio_hpxml_calibration import app
from openstudio_hpxml_calibration.hpxml import FuelType, HpxmlDoc
from openstudio_hpxml_calibration.modify_hpxml import set_consumption_on_hpxml
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.utils import _load_config
from openstudio_hpxml_calibration.weather_normalization.degree_days import (
    calculate_annual_degree_days,
)
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel
from openstudio_hpxml_calibration.weather_normalization.regression import Bpi2400ModelFitError

# Ensure the creator is only created once
if "FitnessMin" not in creator.__dict__:
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if "Individual" not in creator.__dict__:
    creator.create("Individual", list, fitness=creator.FitnessMin)

global_seed = 2025
random.seed(global_seed)


def init_worker(seed):
    """Initialize the random seed for a worker process.

    :param seed: The base seed to use for randomization.
    :type seed: int
    """
    worker_id = (
        multiprocessing.current_process()._identity[0]
        if multiprocessing.current_process()._identity
        else 0
    )
    random.seed(seed + worker_id)


class Calibrate:
    def __init__(
        self,
        original_hpxml_filepath: Path,
        csv_bills_filepath: Path | None = None,
        config_filepath: Path | None = None,
    ):
        """Initialize the Calibrate class.

        :param original_hpxml_filepath: Path to the original HPXML file.
        :type original_hpxml_filepath: Path
        :param csv_bills_filepath: Optional path to the utility bills CSV file.
        :type csv_bills_filepath: Path | None, optional
        :param config_filepath: Optional path to the configuration file.
        :type config_filepath: Path | None, optional
        """
        self.hpxml_filepath = Path(original_hpxml_filepath).resolve()
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())
        self.ga_config = _load_config(config_filepath)

        if csv_bills_filepath:
            logger.debug(f"Adding utility data from {csv_bills_filepath} to hpxml")
            self.hpxml = set_consumption_on_hpxml(self.hpxml, csv_bills_filepath)

        self.hpxml.hpxml_data_error_checking(self.ga_config)

    def get_normalized_consumption_per_bill(self) -> dict[FuelType, pd.DataFrame]:
        """Get the normalized consumption for the building.

        :return: Dictionary containing dataframes for the normalized consumption by end use and fuel type, in mbtu.
        :rtype: dict[FuelType, pd.DataFrame]
        """

        normalized_consumption = {}
        # InverseModel is not applicable to delivered fuels, so we only use it for electricity and natural gas
        self.inv_model = InverseModel(self.hpxml, user_config=self.ga_config)
        for fuel_type, bills in self.inv_model.bills_by_fuel_type.items():
            if fuel_type in (
                FuelType.FUEL_OIL,
                FuelType.PROPANE,
                FuelType.WOOD,
                FuelType.WOOD_PELLETS,
            ):
                continue  # Delivered fuels have a separate calibration process: simplified_annual_usage()

            def _calculate_wrapped_total(row):
                """Extract the epw_daily rows that correspond to the bill month

                Search by row index because epw_daily is just 365 entries without dates
                """
                start = row["start_day_of_year"]
                end = row["end_day_of_year"]

                if start <= end:
                    subset = epw_daily_mbtu.iloc[start:end].sum()
                else:
                    # handle bills that wrap around the end of the year
                    part1 = epw_daily_mbtu.iloc[start:].sum()
                    part2 = epw_daily_mbtu.iloc[0:end].sum()
                    subset = pd.concat(objs=[part1, part2])
                    subset = subset[~subset.index.duplicated()]

                return subset

            try:
                predicted_daily_btu = self.inv_model.predict_epw_daily(fuel_type=fuel_type)
                epw_daily_kbtu = convert_units(x=predicted_daily_btu, from_="btu", to_="kbtu")

                epw_daily_mbtu = convert_units(epw_daily_kbtu, from_="kbtu", to_="mbtu")

                normalized_consumption[fuel_type.value] = pd.DataFrame(
                    data=bills.apply(_calculate_wrapped_total, axis=1)
                )
                normalized_consumption[fuel_type.value]["start_date"] = bills["start_date"]
                normalized_consumption[fuel_type.value]["end_date"] = bills["end_date"]
            except Bpi2400ModelFitError:
                continue

        return normalized_consumption

    def get_model_results(self, json_results_path: Path) -> dict[str, dict[str, float]]:
        """Retrieve annual energy usage from the HPXML model.

        :param json_results_path: Path to the JSON file containing annual results from the HPXML model.
        :type json_results_path: Path
        :return: Model results for each fuel type by end use in mbtu.
        :rtype: dict[str, dict[str, float]]
        """

        results = json.loads(json_results_path.read_text())
        if "Time" in results:
            raise ValueError(f"your file {json_results_path} is not an annual results file")

        model_output = {
            "electricity": {},
            "natural gas": {},
            "propane": {},
            "fuel oil": {},
            "wood cord": {},
            "wood pellets": {},
            "coal": {},
        }

        for end_use, consumption in results["End Use"].items():
            fuel_type = end_use.split(":")[0].lower().strip()
            # ignore electricity usage for heating (fans/pumps) when electricity is not the fuel type for any heating system
            if (
                fuel_type == "electricity"
                and "Heating" in end_use
                and FuelType.ELECTRICITY.value not in self.hpxml.get_fuel_types()["heating"]
            ):
                continue
            if "Heating" in end_use:
                model_output[fuel_type]["heating"] = round(
                    number=(model_output[fuel_type].get("heating", 0) + consumption), ndigits=3
                )
            elif "Cooling" in end_use:
                model_output[fuel_type]["cooling"] = round(
                    number=(model_output[fuel_type].get("cooling", 0) + consumption), ndigits=3
                )
            else:
                model_output[fuel_type]["baseload"] = round(
                    number=(model_output[fuel_type].get("baseload", 0) + consumption), ndigits=3
                )

        return model_output

    def compare_results(
        self, normalized_consumption: dict[str, pd.DataFrame], annual_model_results
    ) -> dict[str, dict[str, dict[str, float]]]:
        """Compare the normalized consumption with the model results.

        :param normalized_consumption: Normalized consumption data (mbtu).
        :type normalized_consumption: dict[str, pd.DataFrame]
        :param annual_model_results: Model results data (mbtu).
        :type annual_model_results: dict
        :return: Comparison results containing bias and absolute errors for each fuel type and end use.
        :rtype: dict[str, dict[str, dict[str, float]]]
        """

        # Build annual normalized bill consumption dicts
        annual_normalized_bill_consumption = {}
        for fuel_type, consumption in normalized_consumption.items():
            annual_normalized_bill_consumption[fuel_type] = {}
            for end_use in ["heating", "cooling", "baseload"]:
                if (
                    end_use not in annual_model_results[fuel_type]
                    or annual_model_results[fuel_type][end_use] == 0.0
                ):
                    continue
                annual_normalized_bill_consumption[fuel_type][end_use] = (
                    consumption[end_use].sum().round(1)
                )

        comparison_results = {}

        # combine the annual normalized bill consumption with the model results
        for model_fuel_type, disagg_results in annual_model_results.items():
            if model_fuel_type in annual_normalized_bill_consumption:
                comparison_results[model_fuel_type] = {"Bias Error": {}, "Absolute Error": {}}
                for load_type in disagg_results:
                    if load_type not in annual_normalized_bill_consumption[model_fuel_type]:
                        continue

                    disagg_result = disagg_results[load_type]
                    if model_fuel_type == "electricity":
                        # All results from simulation and normalized bills are in mbtu.
                        # convert electric loads from mbtu to kWh for bpi2400
                        annual_normalized_bill_consumption[model_fuel_type][load_type] = (
                            convert_units(
                                annual_normalized_bill_consumption[model_fuel_type][load_type],
                                from_="mbtu",
                                to_="kwh",
                            )
                        )
                        disagg_result = convert_units(disagg_result, from_="mbtu", to_="kwh")

                    # Calculate error levels
                    if annual_normalized_bill_consumption[model_fuel_type][load_type] == 0:
                        comparison_results[model_fuel_type]["Bias Error"][load_type] = float("nan")
                    else:
                        comparison_results[model_fuel_type]["Bias Error"][load_type] = round(
                            (
                                (
                                    annual_normalized_bill_consumption[model_fuel_type][load_type]
                                    - disagg_result
                                )
                                / annual_normalized_bill_consumption[model_fuel_type][load_type]
                            )
                            * 100,
                            1,
                        )
                    comparison_results[model_fuel_type]["Absolute Error"][load_type] = round(
                        abs(
                            annual_normalized_bill_consumption[model_fuel_type][load_type]
                            - disagg_result
                        ),
                        1,
                    )

        return comparison_results

    def simplified_annual_usage(
        self, model_results: dict, delivered_consumption, fuel_type: str
    ) -> dict:
        """Perform simplified annual usage calibration for delivered fuels.

        Estimates annual fuel usage and compares measured consumption with modeled results
        for fuels that cannot be weather-normalized (e.g., fuel oil, propane, wood).
        Calculates bias and absolute errors for baseload, heating, and cooling end uses.

        :param model_results: Annual model results by fuel type and end use.
        :type model_results: dict
        :param delivered_consumption: Consumption data object for the delivered fuel.
        :type delivered_consumption: object
        :param fuel_type: The fuel type being calibrated.
        :type fuel_type: str
        :return: Tuple containing bias and absolute error metrics for each end use, and weather-normalized annual consumption by end use.
        :rtype: tuple[dict, dict]
        """
        total_period_tmy_dd, total_period_actual_dd = calculate_annual_degree_days(self.hpxml)

        comparison_results = {}
        if isinstance(model_results, str):
            model_results = json.loads(model_results)

        measured_consumption = 0.0
        fuel_unit_type = delivered_consumption.ConsumptionType.Energy.UnitofMeasure
        if delivered_consumption.ConsumptionType.Energy.FuelType == fuel_type:
            first_bill_date = delivered_consumption.ConsumptionDetail[0].StartDateTime
            last_bill_date = delivered_consumption.ConsumptionDetail[-1].EndDateTime
            first_bill_date = dt.strptime(str(first_bill_date), "%Y-%m-%dT%H:%M:%S")
            last_bill_date = dt.strptime(str(last_bill_date), "%Y-%m-%dT%H:%M:%S")
            num_days = (last_bill_date - first_bill_date + timedelta(days=1)).days
            for period_consumption in delivered_consumption.ConsumptionDetail:
                measured_consumption += float(period_consumption.Consumption)
            # logger.debug(
            #     f"Measured {fuel_type} consumption: {measured_consumption:,.2f} {fuel_unit_type}"
            # )
            if fuel_unit_type == "gal" and fuel_type == FuelType.FUEL_OIL.value:
                fuel_unit_type = f"{fuel_unit_type}_fuel_oil"
            elif fuel_unit_type == "gal" and fuel_type == FuelType.PROPANE.value:
                fuel_unit_type = f"{fuel_unit_type}_propane"
            elif fuel_unit_type == "therms":
                fuel_unit_type = "therm"
        measured_consumption = convert_units(measured_consumption, str(fuel_unit_type), "mBtu")

        modeled_baseload = model_results[fuel_type].get("baseload", 0)
        modeled_heating = model_results[fuel_type].get("heating", 0)
        modeled_cooling = model_results[fuel_type].get("cooling", 0)
        total_modeled_usage = modeled_baseload + modeled_heating + modeled_cooling

        baseload_fraction = modeled_baseload / total_modeled_usage
        heating_fraction = modeled_heating / total_modeled_usage
        cooling_fraction = modeled_cooling / total_modeled_usage

        baseload = baseload_fraction * (num_days / 365)
        heating = heating_fraction * (
            total_period_actual_dd[fuel_type]["HDD65F"] / total_period_tmy_dd[fuel_type]["HDD65F"]
        )
        cooling = cooling_fraction * (
            total_period_actual_dd[fuel_type]["CDD65F"] / total_period_tmy_dd[fuel_type]["CDD65F"]
        )

        annual_delivered_fuel_usage = measured_consumption / (baseload + heating + cooling)
        # logger.debug(f"annual_delivered_fuel_usage: {annual_delivered_fuel_usage:,.2f} mBtu")

        normalized_annual_baseload = annual_delivered_fuel_usage * baseload_fraction
        normalized_annual_heating = annual_delivered_fuel_usage * heating_fraction
        normalized_annual_cooling = annual_delivered_fuel_usage * cooling_fraction

        baseload_bias_error = (
            ((normalized_annual_baseload - modeled_baseload) / normalized_annual_baseload) * 100
            if normalized_annual_baseload
            else 0
        )
        heating_bias_error = (
            ((normalized_annual_heating - modeled_heating) / normalized_annual_heating) * 100
            if normalized_annual_heating
            else 0
        )
        cooling_bias_error = (
            ((normalized_annual_cooling - modeled_cooling) / normalized_annual_cooling) * 100
            if normalized_annual_cooling
            else 0
        )

        baseload_absolute_error = abs(normalized_annual_baseload - modeled_baseload)
        heating_absolute_error = abs(normalized_annual_heating - modeled_heating)
        cooling_absolute_error = abs(normalized_annual_cooling - modeled_cooling)

        comparison_results[fuel_type] = {
            "Bias Error": {
                "baseload": round(baseload_bias_error, 2),
                "heating": round(heating_bias_error, 2),
                "cooling": round(cooling_bias_error, 2),
            },
            "Absolute Error": {
                "baseload": round(baseload_absolute_error, 2),
                "heating": round(heating_absolute_error, 2),
                "cooling": round(cooling_absolute_error, 2),
            },
        }
        normalized_annual_end_uses = {
            "baseload": round(normalized_annual_baseload, 2),
            "heating": round(normalized_annual_heating, 2),
            "cooling": round(normalized_annual_cooling, 2),
        }
        return comparison_results, normalized_annual_end_uses

    def _process_calibration_results(
        self, simulation_results, normalized_consumption_per_bill, for_summary=False
    ):
        """Process calibration results based on simulation data and consumption data.

        Handles both the evaluation of a single individual and the construction of the regression model summary.

        :param simulation_results: Simulation results from the HPXML model.
        :type simulation_results: dict
        :param normalized_consumption_per_bill: Weather-normalized consumption data.
        :type normalized_consumption_per_bill: dict
        :param for_summary: If True, returns summary information for documentation.
        :type for_summary: bool, optional
        :return: Tuple containing comparison error metrics and regression model summary details.
        :rtype: tuple
        """
        comparison = {}
        summary = {}
        delivered_fuels = (
            FuelType.FUEL_OIL.value,
            FuelType.PROPANE.value,
            FuelType.WOOD.value,
            FuelType.WOOD_PELLETS.value,
        )
        consumptions = self.hpxml.get_consumptions()

        for consumption in consumptions:
            for fuel_info in consumption.ConsumptionDetails.ConsumptionInfo:
                fuel = fuel_info.ConsumptionType.Energy.FuelType.text

                if fuel in delivered_fuels:
                    simplified_results, normalized_annual_end_uses = self.simplified_annual_usage(
                        simulation_results, fuel_info, fuel
                    )
                    comparison[fuel] = simplified_results.get(fuel, {})
                    if for_summary:
                        summary[fuel] = {
                            "calibration_type": "simplified",
                            "consumption": normalized_annual_end_uses,
                        }
                else:
                    try:
                        # detailed calibration logic
                        if for_summary:
                            for (
                                reg_model_fuel,
                                reg_model,
                            ) in self.inv_model.regression_models.items():
                                if fuel == reg_model_fuel.value:
                                    end_use_sums = (
                                        normalized_consumption_per_bill[fuel]
                                        .get(["baseload", "heating", "cooling"], 0)
                                        .sum()
                                        .to_dict()
                                    )
                                    summary[fuel] = {
                                        "calibration_type": "detailed",
                                        "model_type": getattr(reg_model, "MODEL_NAME", None),
                                        "cvrmse": getattr(reg_model, "cvrmse", None),
                                        "consumption": end_use_sums,
                                    }
                        else:
                            comparison.update(
                                self.compare_results(
                                    normalized_consumption_per_bill, simulation_results
                                )
                            )

                    except Bpi2400ModelFitError:
                        logger.info(
                            "Could not normalize consumption to weather with sufficient accuracy. Switching to simplified calibration technique."
                        )
                        simplified_results, normalized_annual_end_uses = (
                            self.simplified_annual_usage(simulation_results, fuel_info, fuel)
                        )
                        comparison[fuel] = simplified_results.get(fuel, {})
                        if for_summary:
                            summary[fuel] = {
                                "calibration_type": "simplified",
                                "consumption": normalized_annual_end_uses,
                            }

        return comparison, summary

    def create_measure_input_file(
        self, arguments: dict, output_file_path: str, measure_path: str | None = None
    ):
        if measure_path is None:
            measure_path = str(Path(__file__).resolve().parent.parent / "measures")
        data = {
            "run_directory": str(Path(arguments["save_file_path"]).parent),
            "measure_paths": [measure_path],
            "steps": [{"measure_dir_name": "ModifyXML", "arguments": arguments}],
        }
        Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def run_search(
        self,
        population_size=None,
        generations=None,
        cxpb=None,
        mutpb=None,
        num_proc=None,
        output_filepath=None,
        save_all_results=False,
    ):
        """Run the genetic algorithm search for calibration.

        :param population_size: Number of individuals in the population.
        :type population_size: int, optional
        :param generations: Number of generations to run.
        :type generations: int, optional
        :param cxpb: Crossover probability.
        :type cxpb: float, optional
        :param mutpb: Mutation probability.
        :type mutpb: float, optional
        :param num_proc: Number of parallel processes to use.
        :type num_proc: int, optional
        :param output_filepath: Directory to save output files.
        :type output_filepath: Path, optional
        :param save_all_results: If True, saves all simulation results.
        :type save_all_results: bool, optional
        :return: Tuple containing best individual, population, logbook, error series, regression models, and results.
        :rtype: tuple
        """
        print(f"Running search algorithm for '{Path(self.hpxml_filepath).name}'...")

        all_temp_dirs = set()
        best_dirs_by_gen = []
        cfg = self.ga_config
        population_size = cfg["genetic_algorithm"]["population_size"]
        generations = cfg["genetic_algorithm"]["generations"]
        bias_error_threshold = cfg["acceptance_criteria"]["bias_error_threshold"]
        abs_error_elec_threshold = cfg["acceptance_criteria"]["abs_error_elec_threshold"]
        abs_error_fuel_threshold = cfg["acceptance_criteria"]["abs_error_fuel_threshold"]
        cxpb = cfg["genetic_algorithm"]["crossover_probability"]
        mutpb = cfg["genetic_algorithm"]["mutation_probability"]
        misc_load_multiplier_choices = cfg["value_choices"]["misc_load_multiplier_choices"]
        air_leakage_multiplier_choices = cfg["value_choices"]["air_leakage_multiplier_choices"]
        heating_efficiency_multiplier_choices = cfg["value_choices"][
            "heating_efficiency_multiplier_choices"
        ]
        cooling_efficiency_multiplier_choices = cfg["value_choices"][
            "cooling_efficiency_multiplier_choices"
        ]
        roof_r_value_multiplier_choices = cfg["value_choices"]["roof_r_value_multiplier_choices"]
        ceiling_r_value_multiplier_choices = cfg["value_choices"][
            "ceiling_r_value_multiplier_choices"
        ]
        above_ground_walls_r_value_multiplier_choices = cfg["value_choices"][
            "above_ground_walls_r_value_multiplier_choices"
        ]
        below_ground_walls_r_value_multiplier_choices = cfg["value_choices"][
            "below_ground_walls_r_value_multiplier_choices"
        ]
        slab_r_value_multiplier_choices = cfg["value_choices"]["slab_r_value_multiplier_choices"]
        floor_r_value_multiplier_choices = cfg["value_choices"]["floor_r_value_multiplier_choices"]
        heating_setpoint_offset_choices = cfg["value_choices"]["heating_setpoint_offset_choices"]
        cooling_setpoint_offset_choices = cfg["value_choices"]["cooling_setpoint_offset_choices"]
        water_heater_efficiency_multiplier_choices = cfg["value_choices"][
            "water_heater_efficiency_multiplier_choices"
        ]
        water_fixtures_usage_multiplier_choices = cfg["value_choices"][
            "water_fixtures_usage_multiplier_choices"
        ]
        window_u_factor_multiplier_choices = cfg["value_choices"][
            "window_u_factor_multiplier_choices"
        ]
        window_shgc_multiplier_choices = cfg["value_choices"]["window_shgc_multiplier_choices"]
        appliance_usage_multiplier_choices = cfg["value_choices"][
            "appliance_usage_multiplier_choices"
        ]
        lighting_load_multiplier_choices = cfg["value_choices"]["lighting_load_multiplier_choices"]

        normalized_consumption_per_bill = self.get_normalized_consumption_per_bill()

        def evaluate(individual):
            try:
                (
                    misc_load_multiplier,
                    heating_setpoint_offset,
                    cooling_setpoint_offset,
                    air_leakage_multiplier,
                    heating_efficiency_multiplier,
                    cooling_efficiency_multiplier,
                    roof_r_value_multiplier,
                    ceiling_r_value_multiplier,
                    above_ground_walls_r_value_multiplier,
                    below_ground_walls_r_value_multiplier,
                    slab_r_value_multiplier,
                    floor_r_value_multiplier,
                    water_heater_efficiency_multiplier,
                    water_fixtures_usage_multiplier,
                    window_u_factor_multiplier,
                    window_shgc_multiplier,
                    appliance_usage_multiplier,
                    lighting_load_multiplier,
                ) = individual
                temp_output_dir = Path(
                    tempfile.mkdtemp(prefix=f"calib_test_{uuid.uuid4().hex[:6]}_")
                )
                mod_hpxml_path = temp_output_dir / "modified.xml"
                arguments = {
                    "xml_file_path": str(self.hpxml_filepath),
                    "save_file_path": str(mod_hpxml_path),
                    "misc_load_multiplier": misc_load_multiplier,
                    "heating_setpoint_offset": heating_setpoint_offset,
                    "cooling_setpoint_offset": cooling_setpoint_offset,
                    "air_leakage_multiplier": air_leakage_multiplier,
                    "heating_efficiency_multiplier": heating_efficiency_multiplier,
                    "cooling_efficiency_multiplier": cooling_efficiency_multiplier,
                    "roof_r_value_multiplier": roof_r_value_multiplier,
                    "ceiling_r_value_multiplier": ceiling_r_value_multiplier,
                    "above_ground_walls_r_value_multiplier": above_ground_walls_r_value_multiplier,
                    "below_ground_walls_r_value_multiplier": below_ground_walls_r_value_multiplier,
                    "slab_r_value_multiplier": slab_r_value_multiplier,
                    "floor_r_value_multiplier": floor_r_value_multiplier,
                    "water_heater_efficiency_multiplier": water_heater_efficiency_multiplier,
                    "water_fixtures_usage_multiplier": water_fixtures_usage_multiplier,
                    "window_u_factor_multiplier": window_u_factor_multiplier,
                    "window_shgc_multiplier": window_shgc_multiplier,
                    "appliance_usage_multiplier": appliance_usage_multiplier,
                    "lighting_load_multiplier": lighting_load_multiplier,
                }

                temp_osw = Path(temp_output_dir / "modify_hpxml.osw")
                self.create_measure_input_file(arguments, temp_osw)

                app(["modify-xml", str(temp_osw)])
                app(
                    [
                        "run-sim",
                        str(mod_hpxml_path),
                        "--output-dir",
                        str(temp_output_dir),
                        "--output-format",
                        "json",
                    ]
                )

                output_file = temp_output_dir / "run" / "results_annual.json"
                simulation_results = self.get_model_results(json_results_path=output_file)
                comparison, _ = self._process_calibration_results(
                    simulation_results, normalized_consumption_per_bill
                )

                for model_fuel_type, result in comparison.items():
                    bias_error_criteria = self.ga_config["acceptance_criteria"][
                        "bias_error_threshold"
                    ]
                    if model_fuel_type == "electricity":
                        absolute_error_criteria = self.ga_config["acceptance_criteria"][
                            "abs_error_elec_threshold"
                        ]
                    else:
                        absolute_error_criteria = self.ga_config["acceptance_criteria"][
                            "abs_error_fuel_threshold"
                        ]
                    for load_type in result["Bias Error"]:
                        if abs(result["Bias Error"][load_type]) > bias_error_criteria:
                            logger.debug(
                                f"Bias error for {model_fuel_type} {load_type} is {result['Bias Error'][load_type]} but the limit is +/- {bias_error_criteria}"
                            )
                        if abs(result["Absolute Error"][load_type]) > absolute_error_criteria:
                            logger.debug(
                                f"Absolute error for {model_fuel_type} {load_type} is {result['Absolute Error'][load_type]} but the limit is +/- {absolute_error_criteria}"
                            )

                combined_error_penalties = []
                for fuel_type, metrics in comparison.items():
                    for end_use, bias_error in metrics["Bias Error"].items():
                        if math.isnan(bias_error) or math.isnan(metrics["Absolute Error"][end_use]):
                            continue  # Skip NaN values

                        bias_err = abs(bias_error)
                        abs_err = abs(metrics["Absolute Error"][end_use])

                        log_bias_err = math.log1p(bias_err)  # log1p to avoid log(0)
                        log_abs_err = math.log1p(abs_err)

                        bias_error_penalty = max(0, log_bias_err) ** 2
                        abs_error_penalty = max(0, log_abs_err) ** 2
                        combined_error_penalty = bias_error_penalty + abs_error_penalty

                        combined_error_penalties.append(combined_error_penalty)

                total_score = sum(combined_error_penalties)

                return (
                    (total_score,),
                    comparison,
                    temp_output_dir,
                    simulation_results,
                )

            except Exception as e:
                logger.error(f"Error evaluating individual {individual}: {e}")
                return (float("inf"),), {}, None

        def abs_error_within_threshold(
            fuel_type: str, abs_error: float, elec_threshold: float, fuel_threshold: float
        ) -> bool:
            if fuel_type == "electricity":
                return abs(abs_error) <= elec_threshold
            else:
                return abs(abs_error) <= fuel_threshold

        def diversity(pop):
            return len({tuple(ind) for ind in pop}) / len(pop)

        def calc_stats(values):
            if not values:
                return {"min": None, "max": None, "median": None, "std": None}
            return {
                "min": min(values),
                "max": max(values),
                "median": statistics.median(values),
                "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
            }

        def meets_termination_criteria(comparison):
            all_bias_err_limit_met = True
            all_abs_err_limit_met = True
            for fuel_type, metrics in comparison.items():
                for end_use in metrics["Bias Error"]:
                    bias_err = metrics["Bias Error"][end_use]
                    abs_err = metrics["Absolute Error"][end_use]

                    # Check bias error
                    if abs(bias_err) > bias_error_threshold:
                        all_bias_err_limit_met = False

                    # Check absolute error
                    if not abs_error_within_threshold(
                        fuel_type,
                        abs_err,
                        abs_error_elec_threshold,
                        abs_error_fuel_threshold,
                    ):
                        all_abs_err_limit_met = False

            return all_bias_err_limit_met or all_abs_err_limit_met

        toolbox = base.Toolbox()
        toolbox.register("attr_misc_load_multiplier", random.choice, misc_load_multiplier_choices)
        toolbox.register(
            "attr_heating_setpoint_offset", random.choice, heating_setpoint_offset_choices
        )
        toolbox.register(
            "attr_cooling_setpoint_offset", random.choice, cooling_setpoint_offset_choices
        )
        toolbox.register(
            "attr_air_leakage_multiplier", random.choice, air_leakage_multiplier_choices
        )
        toolbox.register(
            "attr_heating_efficiency_multiplier",
            random.choice,
            heating_efficiency_multiplier_choices,
        )
        toolbox.register(
            "attr_cooling_efficiency_multiplier",
            random.choice,
            cooling_efficiency_multiplier_choices,
        )
        toolbox.register(
            "attr_roof_r_value_multiplier", random.choice, roof_r_value_multiplier_choices
        )
        toolbox.register(
            "attr_ceiling_r_value_multiplier", random.choice, ceiling_r_value_multiplier_choices
        )
        toolbox.register(
            "attr_above_ground_walls_r_value_multiplier",
            random.choice,
            above_ground_walls_r_value_multiplier_choices,
        )
        toolbox.register(
            "attr_below_ground_walls_r_value_multiplier",
            random.choice,
            below_ground_walls_r_value_multiplier_choices,
        )
        toolbox.register(
            "attr_slab_r_value_multiplier", random.choice, slab_r_value_multiplier_choices
        )
        toolbox.register(
            "attr_floor_r_value_multiplier", random.choice, floor_r_value_multiplier_choices
        )
        toolbox.register(
            "attr_water_heater_efficiency_multiplier",
            random.choice,
            water_heater_efficiency_multiplier_choices,
        )
        toolbox.register(
            "attr_water_fixtures_usage_multiplier",
            random.choice,
            water_fixtures_usage_multiplier_choices,
        )
        toolbox.register(
            "attr_window_u_factor_multiplier", random.choice, window_u_factor_multiplier_choices
        )
        toolbox.register(
            "attr_window_shgc_multiplier", random.choice, window_shgc_multiplier_choices
        )
        toolbox.register(
            "attr_appliance_usage_multiplier", random.choice, appliance_usage_multiplier_choices
        )
        toolbox.register(
            "attr_lighting_load_multiplier", random.choice, lighting_load_multiplier_choices
        )
        toolbox.register(
            "individual",
            tools.initRepeat,
            creator.Individual,
            (
                toolbox.attr_misc_load_multiplier,
                toolbox.attr_heating_setpoint_offset,
                toolbox.attr_cooling_setpoint_offset,
                toolbox.attr_air_leakage_multiplier,
                toolbox.attr_heating_efficiency_multiplier,
                toolbox.attr_cooling_efficiency_multiplier,
                toolbox.attr_roof_r_value_multiplier,
                toolbox.attr_ceiling_r_value_multiplier,
                toolbox.attr_above_ground_walls_r_value_multiplier,
                toolbox.attr_below_ground_walls_r_value_multiplier,
                toolbox.attr_slab_r_value_multiplier,
                toolbox.attr_floor_r_value_multiplier,
                toolbox.attr_water_heater_efficiency_multiplier,
                toolbox.attr_water_fixtures_usage_multiplier,
                toolbox.attr_window_u_factor_multiplier,
                toolbox.attr_window_shgc_multiplier,
                toolbox.attr_appliance_usage_multiplier,
                toolbox.attr_lighting_load_multiplier,
            ),
            n=18,
        )

        def create_seed_individual():
            return creator.Individual(
                [
                    1,  # misc_load_multiplier
                    0,  # heating_setpoint_offset
                    0,  # cooling_setpoint_offset
                    1,  # air_leakage_multiplier
                    1,  # heating_efficiency_multiplier
                    1,  # cooling_efficiency_multiplier
                    1,  # roof_r_value_multiplier
                    1,  # ceiling_r_value_multiplier
                    1,  # above_ground_walls_r_value_multiplier
                    1,  # below_ground_walls_r_value_multiplier
                    1,  # slab_r_value_multiplier
                    1,  # floor_r_value_multiplier
                    1,  # water_heater_efficiency_multiplier
                    1,  # water_fixtures_usage_multiplier
                    1,  # window_u_factor_multiplier
                    1,  # window_shgc_multiplier
                    1,  # appliance_usage_multiplier
                    1,  # lighting_load_multiplier
                ]
            )

        def generate_random_individual():
            return creator.Individual(
                [
                    random.choice(misc_load_multiplier_choices),
                    random.choice(heating_setpoint_offset_choices),
                    random.choice(cooling_setpoint_offset_choices),
                    random.choice(air_leakage_multiplier_choices),
                    random.choice(heating_efficiency_multiplier_choices),
                    random.choice(cooling_efficiency_multiplier_choices),
                    random.choice(roof_r_value_multiplier_choices),
                    random.choice(ceiling_r_value_multiplier_choices),
                    random.choice(above_ground_walls_r_value_multiplier_choices),
                    random.choice(below_ground_walls_r_value_multiplier_choices),
                    random.choice(slab_r_value_multiplier_choices),
                    random.choice(floor_r_value_multiplier_choices),
                    random.choice(water_heater_efficiency_multiplier_choices),
                    random.choice(water_fixtures_usage_multiplier_choices),
                    random.choice(window_u_factor_multiplier_choices),
                    random.choice(window_shgc_multiplier_choices),
                    random.choice(appliance_usage_multiplier_choices),
                    random.choice(lighting_load_multiplier_choices),
                ]
            )

        def is_existing_home(individual, param_choices_map):
            return all(
                val == 1
                for key, val in zip(param_choices_map.keys(), individual)
                if "multiplier" in key
            ) and all(
                val == 0
                for key, val in zip(param_choices_map.keys(), individual)
                if "offset" in key
            )

        toolbox.register("individual", generate_random_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", evaluate)
        toolbox.register("mate", tools.cxUniform, indpb=cxpb)

        # Define parameter-to-choices mapping for mutation
        param_choices_map = {
            "misc_load_multiplier": misc_load_multiplier_choices,
            "heating_setpoint_offset": heating_setpoint_offset_choices,
            "cooling_setpoint_offset": cooling_setpoint_offset_choices,
            "air_leakage_multiplier": air_leakage_multiplier_choices,
            "heating_efficiency_multiplier": heating_efficiency_multiplier_choices,
            "cooling_efficiency_multiplier": cooling_efficiency_multiplier_choices,
            "roof_r_value_multiplier": roof_r_value_multiplier_choices,
            "ceiling_r_value_multiplier": ceiling_r_value_multiplier_choices,
            "above_ground_walls_r_value_multiplier": above_ground_walls_r_value_multiplier_choices,
            "below_ground_walls_r_value_multiplier": below_ground_walls_r_value_multiplier_choices,
            "slab_r_value_multiplier": slab_r_value_multiplier_choices,
            "floor_r_value_multiplier": floor_r_value_multiplier_choices,
            "water_heater_efficiency_multiplier": water_heater_efficiency_multiplier_choices,
            "water_fixtures_usage_multiplier": water_fixtures_usage_multiplier_choices,
            "window_u_factor_multiplier": window_u_factor_multiplier_choices,
            "window_shgc_multiplier": window_shgc_multiplier_choices,
            "appliance_usage_multiplier": appliance_usage_multiplier_choices,
            "lighting_load_multiplier": lighting_load_multiplier_choices,
        }

        worst_end_uses_by_gen = []

        end_use_param_map = {
            "electricity_heating": [
                "heating_setpoint_offset",
                "air_leakage_multiplier",
                "heating_efficiency_multiplier",
                "roof_r_value_multiplier",
                "ceiling_r_value_multiplier",
                "above_ground_walls_r_value_multiplier",
                "slab_r_value_multiplier",
                "window_u_factor_multiplier",
                "window_shgc_multiplier",
            ],
            "electricity_cooling": [
                "cooling_setpoint_offset",
                "air_leakage_multiplier",
                "cooling_efficiency_multiplier",
                "roof_r_value_multiplier",
                "ceiling_r_value_multiplier",
                "above_ground_walls_r_value_multiplier",
                "slab_r_value_multiplier",
                "window_u_factor_multiplier",
                "window_shgc_multiplier",
            ],
            "electricity_baseload": [
                "misc_load_multiplier",
                "appliance_usage_multiplier",
                "lighting_load_multiplier",
            ],
            "natural_gas_heating": [
                "heating_setpoint_offset",
                "air_leakage_multiplier",
                "heating_efficiency_multiplier",
                "roof_r_value_multiplier",
                "ceiling_r_value_multiplier",
                "above_ground_walls_r_value_multiplier",
                "slab_r_value_multiplier",
                "window_u_factor_multiplier",
                "window_shgc_multiplier",
            ],
            "natural_gas_baseload": [
                "water_heater_efficiency_multiplier",
                "water_fixtures_usage_multiplier",
            ],
        }

        param_names = list(param_choices_map.keys())
        name_to_index = {name: idx for idx, name in enumerate(param_names)}
        index_to_name = {idx: name for name, idx in name_to_index.items()}

        def get_worst_abs_err_end_use(comparison):
            max_abs_err = -float("inf")
            worst_end_use_key = None
            for fuel_type, metrics in comparison.items():
                for end_use, abs_err in metrics["Absolute Error"].items():
                    key = f"{fuel_type}_{end_use}"
                    if abs(abs_err) > max_abs_err:
                        max_abs_err = abs(abs_err)
                        worst_end_use_key = key
            return worst_end_use_key

        def adaptive_mutation(individual):
            mutation_indices = set()

            if worst_end_uses_by_gen:
                worst_end_use = worst_end_uses_by_gen[-1]
                impacted_param_names = end_use_param_map.get(worst_end_use, [])
                if impacted_param_names:
                    impacted_indices = [
                        name_to_index[n] for n in impacted_param_names if n in name_to_index
                    ]
                    if impacted_indices:
                        mutation_indices.update(
                            random.sample(impacted_indices, min(len(impacted_indices), 2))
                        )

            while len(mutation_indices) < random.randint(3, 6):
                mutation_indices.add(random.randint(0, len(individual) - 1))

            for i in mutation_indices:
                current_val = individual[i]
                param_name = index_to_name[i]
                choices = [val for val in param_choices_map[param_name] if val != current_val]
                if choices:
                    individual[i] = random.choice(choices)
            return (individual,)

        toolbox.register("mutate", adaptive_mutation)
        toolbox.register("select", tools.selTournament, tournsize=2)

        calibration_success = False

        if num_proc is None:
            num_proc = multiprocessing.cpu_count() - 1

        with Pool(
            processes=num_proc,
            maxtasksperchild=15,
            initializer=init_worker,
            initargs=(global_seed,),
        ) as pool:
            toolbox.register("map", pool.map)
            pop = toolbox.population(n=population_size - 1)
            pop.append(create_seed_individual())  # Add existing model as seed individual
            hall_of_fame = tools.HallOfFame(1)
            stats = tools.Statistics(lambda ind: ind.fitness.values[0])  # noqa: PD011
            stats.register("min", min)
            stats.register("avg", lambda x: sum(x) / len(x))

            logbook = tools.Logbook()
            logbook.header = ["gen", "nevals", "min", "avg", "diversity"]

            best_bias_series = {}
            best_abs_series = {}

            # Initial evaluation
            invalid_ind = [ind for ind in pop if not ind.fitness.valid]
            fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
            for ind, (fit, comp, temp_dir, sim_results) in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
                ind.comparison = comp
                ind.temp_output_dir = temp_dir
                ind.sim_results = sim_results
                if temp_dir is not None:
                    all_temp_dirs.add(temp_dir)

            # Save all individual hpxmls
            if temp_dir is not None and Path(temp_dir).exists():
                gen_dir = output_filepath / "gen_0"
                gen_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(
                    temp_dir / "modified.xml",
                    gen_dir / f"ind_{uuid.uuid4().hex[:6]}.xml",
                )

            # Update Hall of Fame and stats
            hall_of_fame.update(pop)
            best_ind = tools.selBest(pop, 1)[0]
            best_dirs_by_gen.append(getattr(best_ind, "temp_output_dir", None))

            # Save best individual bias/abs errors
            best_comp = best_ind.comparison
            for end_use, metrics in best_comp.items():
                for fuel_type, bias_error in metrics["Bias Error"].items():
                    key = f"{end_use}_{fuel_type}"
                    best_bias_series.setdefault(key, []).append(bias_error)
                for fuel_type, abs_error in metrics["Absolute Error"].items():
                    key = f"{end_use}_{fuel_type}"
                    best_abs_series.setdefault(key, []).append(abs_error)

            # Parameter statistics
            param_stats = {
                pname: {
                    "min": min(values := [ind[i] for ind in pop]),
                    "max": max(values),
                    "median": statistics.median(values),
                    "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
                }
                for i, pname in index_to_name.items()
            }

            # Simulation result statistics
            sim_result_stats = {}
            all_results = {
                ind.temp_output_dir.stem: ind.sim_results
                for ind in pop
                if hasattr(ind, "sim_results")
            }
            if all_results:
                fuel_enduse_keys = {
                    (fuel_type, end_use)
                    for r in all_results.values()
                    for fuel_type, end_uses in r.items()
                    for end_use in end_uses
                }
                for fuel_type, end_use in fuel_enduse_keys:
                    vals = [
                        r[fuel_type][end_use]
                        for r in all_results.values()
                        if fuel_type in r and end_use in r[fuel_type]
                    ]
                    if vals:
                        sim_result_stats[f"{fuel_type}_{end_use}"] = calc_stats(vals)

            # Log generation 0
            record = stats.compile(pop)
            record.update({f"bias_error_{k}": v[-1] for k, v in best_bias_series.items()})
            record.update({f"abs_error_{k}": v[-1] for k, v in best_abs_series.items()})
            record["best_individual"] = json.dumps(dict(zip(param_choices_map.keys(), best_ind)))
            record["best_individual_sim_results"] = json.dumps(best_ind.sim_results)
            record["diversity"] = diversity(pop)
            record["parameter_choice_stats"] = json.dumps(param_stats)
            record["simulation_result_stats"] = json.dumps(sim_result_stats)
            if save_all_results:
                record["all_simulation_results"] = json.dumps(all_results)
            logbook.record(gen=0, nevals=len(invalid_ind), **record)
            print(logbook.stream)

            # Store existing home (seed individual) results
            existing_home_results = {}
            for ind in pop:
                if is_existing_home(ind, param_choices_map):
                    existing_home_results["existing_home_sim_results"] = json.dumps(ind.sim_results)
                    break

            # Construct weather-normalized regression model summary
            _, weather_norm_regression_models = self._process_calibration_results(
                existing_home_results["existing_home_sim_results"],
                normalized_consumption_per_bill,
                for_summary=True,
            )

            for gen in range(1, generations + 1):
                print(f"Running {len(pop)} simulations for search generation {gen}...")

                # Elitism: Copy the best individuals
                elite = [copy.deepcopy(ind) for ind in tools.selBest(pop, k=1)]

                # Generate offspring
                offspring = algorithms.varAnd(pop, toolbox, cxpb=cxpb, mutpb=mutpb)

                # Evaluate offspring
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
                for ind, (fit, comp, temp_dir, sim_results) in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit
                    ind.comparison = comp
                    ind.temp_output_dir = temp_dir
                    ind.sim_results = sim_results
                    all_temp_dirs.add(temp_dir)

                # Select next generation (excluding elites), then add elites
                if invalid_ind:
                    worst_key = get_worst_abs_err_end_use(invalid_ind[0].comparison)
                    worst_end_uses_by_gen.append(worst_key)

                pop = toolbox.select(offspring, population_size - len(elite))
                pop.extend(elite)

                # Save all individual hpxmls
                if temp_dir is not None and Path(temp_dir).exists():
                    gen_dir = output_filepath / f"gen_{gen}"
                    gen_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        temp_dir / "modified.xml",
                        gen_dir / f"ind_{uuid.uuid4().hex[:6]}.xml",
                    )

                # Update Hall of Fame and stats
                hall_of_fame.update(pop)
                best_ind = tools.selBest(pop, 1)[0]
                best_dirs_by_gen.append(getattr(best_ind, "temp_output_dir", None))

                # Save hall of fame bias/abs errors
                best_comp = best_ind.comparison
                for end_use, metrics in best_comp.items():
                    for fuel_type, bias_error in metrics["Bias Error"].items():
                        key = f"{end_use}_{fuel_type}"
                        best_bias_series.setdefault(key, []).append(bias_error)
                    for fuel_type, abs_error in metrics["Absolute Error"].items():
                        key = f"{end_use}_{fuel_type}"
                        best_abs_series.setdefault(key, []).append(abs_error)

                # Parameter statistics
                param_stats = {
                    pname: {
                        "min": min(values := [ind[i] for ind in pop]),
                        "max": max(values),
                        "median": statistics.median(values),
                        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
                    }
                    for i, pname in index_to_name.items()
                }

                # Simulation result statistics
                sim_result_stats = {}
                all_results = {
                    ind.temp_output_dir.stem: ind.sim_results
                    for ind in pop
                    if hasattr(ind, "sim_results")
                }
                if all_results:
                    fuel_enduse_keys = {
                        (fuel_type, end_use)
                        for r in all_results.values()
                        for fuel_type, end_uses in r.items()
                        for end_use in end_uses
                    }
                    for fuel_type, end_use in fuel_enduse_keys:
                        vals = [
                            r[fuel_type][end_use]
                            for r in all_results.values()
                            if fuel_type in r and end_use in r[fuel_type]
                        ]
                        if vals:
                            sim_result_stats[f"{fuel_type}_{end_use}"] = calc_stats(vals)

                # Log the current generation
                record = stats.compile(pop)
                record.update({f"bias_error_{k}": v[-1] for k, v in best_bias_series.items()})
                record.update({f"abs_error_{k}": v[-1] for k, v in best_abs_series.items()})
                record["best_individual"] = json.dumps(
                    dict(zip(param_choices_map.keys(), best_ind))
                )
                record["best_individual_sim_results"] = json.dumps(best_ind.sim_results)
                record["diversity"] = diversity(pop)
                record["parameter_choice_stats"] = json.dumps(param_stats)
                record["simulation_result_stats"] = json.dumps(sim_result_stats)
                if save_all_results:
                    record["all_simulation_results"] = json.dumps(all_results)
                logbook.record(gen=gen, nevals=len(invalid_ind), **record)
                print(logbook.stream)

                # Early termination conditions
                if meets_termination_criteria(best_comp):
                    calibration_success = True
                    if gen < generations:
                        print(f"Early stopping: termination criteria met at generation {gen}")
                    break

        best_individual = hall_of_fame[0]
        best_individual_dict = dict(zip(param_choices_map.keys(), best_individual))

        best_individual_hpxml = best_individual.temp_output_dir / "modified.xml"
        if best_individual_hpxml.exists():
            shutil.copy(best_individual_hpxml, output_filepath / "best_individual.xml")

        # Cleanup
        time.sleep(0.5)
        for temp_dir in all_temp_dirs:
            if temp_dir and Path(temp_dir).exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        if calibration_success:
            print(
                "Search has completed successfully: A solution satisfying error thresholds was found."
            )
        else:
            print(
                "Search has completed. However, no solution was found that satisfies the bias error "
                "and absolute error thresholds before reaching the maximum number of generations."
            )

        return (
            best_individual_dict,
            pop,
            logbook,
            best_bias_series,
            best_abs_series,
            weather_norm_regression_models,
            existing_home_results,
            calibration_success,
        )
