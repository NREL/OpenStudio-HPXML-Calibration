import copy
import json
import random
import shutil
import tempfile
from pathlib import Path

import pandas as pd
from deap import algorithms, base, creator, tools
from loguru import logger
from pathos.multiprocessing import ProcessingPool as Pool

from openstudio_hpxml_calibration import app
from openstudio_hpxml_calibration.hpxml import FuelType, HpxmlDoc
from openstudio_hpxml_calibration.modify_hpxml import set_consumption_on_hpxml
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel

# Ensure the creator is only created once
if "FitnessMin" not in creator.__dict__:
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
if "Individual" not in creator.__dict__:
    creator.create("Individual", list, fitness=creator.FitnessMin)


class Calibrate:
    def __init__(self, original_hpxml_filepath: Path, csv_bills_filepath: Path | None = None):
        self.hpxml_filepath = Path(original_hpxml_filepath).resolve()
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())

        if csv_bills_filepath:
            logger.info(f"Adding utility data from {csv_bills_filepath} to hpxml")
            self.hpxml = set_consumption_on_hpxml(self.hpxml, csv_bills_filepath)

        self.inv_model = InverseModel(self.hpxml)

    def get_normalized_consumption_per_bill(self) -> dict[FuelType, pd.DataFrame]:
        """
        Get the normalized consumption for the building.

        Returns:
            dict: A dictionary containing dataframes for the normalized consumption by end use and fuel type, in mbtu.
        """

        normalized_consumption = {}
        for fuel_type, bills in self.inv_model.bills_by_fuel_type.items():

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

            epw_daily = convert_units(
                x=self.inv_model.predict_epw_daily(fuel_type=fuel_type), from_="btu", to_="kbtu"
            )

            epw_daily_mbtu = convert_units(epw_daily, from_="kbtu", to_="mbtu")

            normalized_consumption[fuel_type.value] = pd.DataFrame(
                data=bills.apply(_calculate_wrapped_total, axis=1)
            )
            normalized_consumption[fuel_type.value]["start_date"] = bills["start_date"]
            normalized_consumption[fuel_type.value]["end_date"] = bills["end_date"]

        return normalized_consumption

    def get_model_results(self, json_results_path: Path) -> dict[str, dict[str, float]]:
        """
        Retrieve annual energy usage from the HPXML model.

        Args:
            annual_json_results_path (Path): Path to the JSON file containing annual results from the HPXML model

        Returns:
            dict[str, dict[str, float]]: A dict of dicts containing the model results for each fuel type by end use in mbtu (because the annual results are in mbtu).
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

        # TODO: Use bill date parts of this code to handle calibration by bill-period
        # Most of it can be scrapped. Adapt bill dates to the above style.

        # results = json.loads(json_results_path.read_text())
        # # if "Time" in results:
        # #     daily_results = results
        # model_output = {}
        # for fuel_type, bills in self.inv_model.bills_by_fuel_type.items():
        #     bill_dates = list(zip(bills["start_day_of_year"], bills["end_day_of_year"]))
        #     model_output[fuel_type.value] = {}
        #     for bill in bill_dates:
        #         # bill is a tuple of start_day_of_year and end_day_of_year of utility bill
        #         model_output[fuel_type.value][f"{bill}"] = {}
        #         for end_use, consumption_list in daily_results["End Use"].items():
        #             if "Heating" in end_use:
        #                 # if end_use.lower().startswith(fuel_type.value):
        #                 if "heating_energy" in model_output[fuel_type.value][f"{bill}"]:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["heating_energy"] += sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         )
        #                         model_output[fuel_type.value][f"{bill}"]["heating_energy"] += sum(
        #                             consumption_list[0 : bill[1]]
        #                         )
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["heating_energy"] += sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )
        #                 else:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["heating_energy"] = sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         ) + sum(consumption_list[0 : bill[1]])
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["heating_energy"] = sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )
        #             elif "Cooling" in end_use:
        #                 if "cooling_energy" in model_output[fuel_type.value][f"{bill}"]:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["cooling_energy"] += sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         )
        #                         model_output[fuel_type.value][f"{bill}"]["cooling_energy"] += sum(
        #                             consumption_list[0 : bill[1]]
        #                         )
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["cooling_energy"] += sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )
        #                 else:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["cooling_energy"] = sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         ) + sum(consumption_list[0 : bill[1]])
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["cooling_energy"] = sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )
        #             # elif "Hot Water" in end_use:
        #             #     if "hot_water_energy" in model_output[fuel_type.value][f"{bill}"]:
        #             #         model_output[fuel_type.value][f"{bill}"]["hot_water_energy"] += sum(
        #             #             consumption_list[bill[0] : bill[1]]
        #             #         )
        #             #     else:
        #             #         model_output[fuel_type.value][f"{bill}"]["hot_water_energy"] = sum(
        #             #             consumption_list[bill[0] : bill[1]]
        #             #         )
        #             # elif "Lighting" in end_use:
        #             #     if "lighting_energy" in model_output[fuel_type.value][f"{bill}"]:
        #             #         model_output[fuel_type.value][f"{bill}"]["lighting_energy"] += sum(
        #             #             consumption_list[bill[0] : bill[1]]
        #             #         )
        #             #     else:
        #             #         model_output[fuel_type.value][f"{bill}"]["lighting_energy"] = sum(
        #             #             consumption_list[bill[0] : bill[1]]
        #             #         )
        #             else:
        #                 if "other_energy" in model_output[fuel_type.value][f"{bill}"]:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["other_energy"] += sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         )
        #                         model_output[fuel_type.value][f"{bill}"]["other_energy"] += sum(
        #                             consumption_list[0 : bill[1]]
        #                         )
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["other_energy"] += sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )
        #                 else:
        #                     if bill[0] > bill[1]:
        #                         # handle bills that wrap around the end of the year
        #                         model_output[fuel_type.value][f"{bill}"]["other_energy"] = sum(
        #                             consumption_list[bill[0] : len(consumption_list)]
        #                         ) + sum(consumption_list[0 : bill[1]])
        #                     else:
        #                         model_output[fuel_type.value][f"{bill}"]["other_energy"] = sum(
        #                             consumption_list[bill[0] : bill[1]]
        #                         )

        # model_output_dfs = {}
        # for fuel_type, monthly_usage in model_output.items():
        #     monthly_usage_df = pd.DataFrame(monthly_usage)
        #     rows = []
        #     for col in monthly_usage_df.columns:
        #         # Parse the column name to get start_date and end_date
        #         start_date, end_date = literal_eval(col)
        #         row = {
        #             "heating_energy": monthly_usage_df.loc["heating_energy", col],
        #             "cooling_energy": monthly_usage_df.loc["cooling_energy", col],
        #             "other_energy": monthly_usage_df.loc["other_energy", col],
        #             "start_date": start_date,
        #             "end_date": end_date,
        #         }
        #         rows.append(row)

        #     reshaped_df = pd.DataFrame(
        #         rows,
        #         columns=[
        #             "heating_energy",
        #             "cooling_energy",
        #             "other_energy",
        #             "start_date",
        #             "end_date",
        #         ],
        #     ).reset_index(drop=True)
        #     model_output_dfs[f"{fuel_type}_df"] = reshaped_df

        return model_output

    def compare_results(
        self, normalized_consumption: dict[str, pd.DataFrame], annual_model_results
    ) -> dict[str, dict[str, dict[str, float]]]:
        """
        Compare the normalized consumption with the model results.

        Args:
            normalized_consumption (dict): Normalized consumption data (mbtu)
            annual_model_results (dict): Model results data (mbtu)

        Returns:
            dict: A dictionary containing the comparison results:
            "{
                <fuel_type>: {
                    "Bias Error": {
                        <load_type - heating/cooling/baseline>: <percentage error>
                    },
                    "Absolute Error": {
                        <load_type - heating/cooling/baseline>: <error in mbtu or kWh>
                    }
                },
                <fuel_type>: {...}
            }"
        """

        # TODO: prevent double-calculating when running multiple times in the same kernel session

        # Build annual normalized bill consumption dicts
        annual_normalized_bill_consumption = {}
        for fuel_type, consumption in normalized_consumption.items():
            annual_normalized_bill_consumption[fuel_type] = {}
            for end_use in ["heating", "cooling", "baseload"]:
                annual_normalized_bill_consumption[fuel_type][end_use] = (
                    consumption[end_use].sum().round(1)
                )

        comparison_results = {}

        # combine the annual normalized bill consumption with the model results
        for model_fuel_type, disagg_results in annual_model_results.items():
            bias_error_criteria = 5  # percent
            absolute_error_criteria = 5  # measured in mbtu
            if model_fuel_type in annual_normalized_bill_consumption:
                comparison_results[model_fuel_type] = {"Bias Error": {}, "Absolute Error": {}}
                for load_type in disagg_results:
                    if model_fuel_type == "electricity":
                        absolute_error_criteria = 500  # measured in kWh
                        # All results from simulation and normalized bills are in mbtu.
                        # convert electric loads from mbtu to kWh for bpi2400
                        annual_normalized_bill_consumption[model_fuel_type][load_type] = (
                            convert_units(
                                annual_normalized_bill_consumption[model_fuel_type][load_type],
                                from_="mbtu",
                                to_="kwh",
                            )
                        )
                        disagg_results[load_type] = convert_units(
                            disagg_results[load_type], from_="mbtu", to_="kwh"
                        )

                    # Calculate error levels
                    comparison_results[model_fuel_type]["Bias Error"][load_type] = round(
                        (
                            (
                                annual_normalized_bill_consumption[model_fuel_type][load_type]
                                - disagg_results[load_type]
                            )
                            / annual_normalized_bill_consumption[model_fuel_type][load_type]
                        )
                        * 100,
                        1,
                    )
                    comparison_results[model_fuel_type]["Absolute Error"][load_type] = round(
                        abs(
                            annual_normalized_bill_consumption[model_fuel_type][load_type]
                            - disagg_results[load_type]
                        ),
                        1,
                    )
                    # Warn if either error exceeds the criteria
                    # TODO: Instead of warning, adjust the modification and simulate again
                    if (
                        abs(comparison_results[model_fuel_type]["Bias Error"][load_type])
                        > bias_error_criteria
                    ):
                        logger.warning(
                            f"Bias error for {model_fuel_type} {load_type} is {comparison_results[model_fuel_type]['Bias Error'][load_type]} but the limit is +/- {bias_error_criteria}"
                        )
                    if (
                        abs(comparison_results[model_fuel_type]["Absolute Error"][load_type])
                        > absolute_error_criteria
                    ):
                        logger.warning(
                            f"Absolute error for {model_fuel_type} {load_type} is {comparison_results[model_fuel_type]['Absolute Error'][load_type]} but the limit is +/- {absolute_error_criteria}"
                        )

        return comparison_results

    def run_ga_search(self, population_size=100, generations=100):
        all_temp_dirs = set()
        best_dirs_by_gen = []

        def evaluate(individual):
            (
                plug_load_pct_change,
                heating_setpoint_offset,
                cooling_setpoint_offset,
                air_leakage_pct_change,
                heating_efficiency_pct_change,
                cooling_efficiency_pct_change,
                roof_r_value_pct_change,
                ceiling_r_value_pct_change,
                above_ground_walls_r_value_pct_change,
                below_ground_walls_r_value_pct_change,
                slab_r_value_pct_change,
                floor_r_value_pct_change,
            ) = individual
            temp_output_dir = Path(tempfile.mkdtemp(prefix="calib_test_"))
            mod_hpxml_path = temp_output_dir / "modified.xml"
            arguments = {
                "xml_file_path": str(self.hpxml_filepath),
                "save_file_path": str(mod_hpxml_path),
                "heating_setpoint_offset": heating_setpoint_offset,
                "cooling_setpoint_offset": cooling_setpoint_offset,
                "plug_load_pct_change": plug_load_pct_change,
                "air_leakage_pct_change": air_leakage_pct_change,
                "heating_efficiency_pct_change": heating_efficiency_pct_change,
                "cooling_efficiency_pct_change": cooling_efficiency_pct_change,
                "roof_r_value_pct_change": roof_r_value_pct_change,
                "ceiling_r_value_pct_change": ceiling_r_value_pct_change,
                "above_ground_walls_r_value_pct_change": above_ground_walls_r_value_pct_change,
                "below_ground_walls_r_value_pct_change": below_ground_walls_r_value_pct_change,
                "slab_r_value_pct_change": slab_r_value_pct_change,
                "floor_r_value_pct_change": floor_r_value_pct_change,
            }

            temp_osw = Path(temp_output_dir / "modify_hpxml.osw")
            create_measure_input_file(arguments, temp_osw)

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
            normalized_consumption = self.get_normalized_consumption_per_bill()
            comparison = self.compare_results(normalized_consumption, simulation_results)

            errors = []
            for end_use, metrics in comparison.items():
                for fuel_type, bias in metrics["Bias Error"].items():
                    penalty = max(0, abs(bias) - 5)  # Bias within 5% still penalized
                    errors.append(penalty**2)  # quadratic penalty
            total_score = sum(errors)

            return (total_score,), comparison, temp_output_dir

        def create_measure_input_file(arguments: dict, output_file_path: str):
            data = {
                "run_directory": str(Path(arguments["save_file_path"]).parent),
                "measure_paths": ["C:\\Github\\OpenStudio-HPXML-Calibration\\src\\measures"],
                "steps": [{"measure_dir_name": "ModifyXML", "arguments": arguments}],
            }
            Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        def diversity(pop):
            return len({tuple(ind) for ind in pop}) / len(pop)

        toolbox = base.Toolbox()
        plug_load_pct_choices = [
            -0.9,
            -0.8,
            -0.7,
            -0.6,
            -0.5,
            -0.4,
            -0.3,
            -0.2,
            -0.1,
            0,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            1,
            5,
            10,
        ]
        air_leakage_pct_choices = [
            -0.9,
            -0.8,
            -0.7,
            -0.6,
            -0.5,
            -0.4,
            -0.3,
            -0.2,
            -0.1,
            0,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            1,
            5,
            10,
        ]
        hvac_eff_pct_choices = [round(x * 0.01, 1) for x in range(-90, 91)]
        r_value_pct_choices = [
            -0.9,
            -0.8,
            -0.7,
            -0.6,
            -0.5,
            -0.4,
            -0.3,
            -0.2,
            -0.1,
            0,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            1,
            5,
            10,
        ]
        heating_setpoint_choices = [-9, -7, -5, -3, -1, 0, 1, 3, 5, 7, 9]
        cooling_setpoint_choices = [-9, -7, -5, -2, -1, 0, 1, 3, 5, 7, 9]
        toolbox.register("attr_plug_load_pct_change", random.choice, plug_load_pct_choices)
        toolbox.register("attr_heating_setpoint_offset", random.choice, heating_setpoint_choices)
        toolbox.register("attr_cooling_setpoint_offset", random.choice, cooling_setpoint_choices)
        toolbox.register("attr_air_leakage_pct_change", random.choice, air_leakage_pct_choices)
        toolbox.register("attr_heating_efficiency_pct_change", random.choice, hvac_eff_pct_choices)
        toolbox.register("attr_cooling_efficiency_pct_change", random.choice, hvac_eff_pct_choices)
        toolbox.register("attr_roof_r_value_pct_change", random.choice, r_value_pct_choices)
        toolbox.register("attr_ceiling_r_value_pct_change", random.choice, r_value_pct_choices)
        toolbox.register(
            "attr_above_ground_walls_r_value_pct_change", random.choice, r_value_pct_choices
        )
        toolbox.register(
            "attr_below_ground_walls_r_value_pct_change", random.choice, r_value_pct_choices
        )
        toolbox.register("attr_slab_r_value_pct_change", random.choice, r_value_pct_choices)
        toolbox.register("attr_floor_r_value_pct_change", random.choice, r_value_pct_choices)
        toolbox.register(
            "individual",
            tools.initRepeat,
            creator.Individual,
            (
                toolbox.attr_plug_load_pct_change,
                toolbox.attr_heating_setpoint_offset,
                toolbox.attr_cooling_setpoint_offset,
                toolbox.attr_air_leakage_pct_change,
                toolbox.attr_heating_efficiency_pct_change,
                toolbox.attr_cooling_efficiency_pct_change,
                toolbox.attr_roof_r_value_pct_change,
                toolbox.attr_ceiling_r_value_pct_change,
                toolbox.attr_above_ground_walls_r_value_pct_change,
                toolbox.attr_below_ground_walls_r_value_pct_change,
                toolbox.attr_slab_r_value_pct_change,
                toolbox.attr_floor_r_value_pct_change,
            ),
            n=12,
        )

        def generate_random_individual():
            return creator.Individual(
                [
                    random.choice(plug_load_pct_choices),
                    random.choice(heating_setpoint_choices),
                    random.choice(cooling_setpoint_choices),
                    random.choice(air_leakage_pct_choices),
                    random.choice(hvac_eff_pct_choices),
                    random.choice(hvac_eff_pct_choices),
                    random.choice(r_value_pct_choices),
                    random.choice(r_value_pct_choices),
                    random.choice(r_value_pct_choices),
                    random.choice(r_value_pct_choices),
                    random.choice(r_value_pct_choices),
                    random.choice(r_value_pct_choices),
                ]
            )

        toolbox.register("individual", generate_random_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", evaluate)
        toolbox.register("mate", tools.cxUniform, indpb=0.4)

        # Define parameter-to-choices mapping for mutation
        param_choices_map = {
            0: plug_load_pct_choices,
            1: heating_setpoint_choices,
            2: cooling_setpoint_choices,
            3: air_leakage_pct_choices,
            4: hvac_eff_pct_choices,
            5: hvac_eff_pct_choices,
            6: r_value_pct_choices,
            7: r_value_pct_choices,
            8: r_value_pct_choices,
            9: r_value_pct_choices,
            10: r_value_pct_choices,
            11: r_value_pct_choices,
        }

        def discrete_mutation(individual):
            num_mutations = random.randint(3, 6)  # at least 3-6 gene mutation
            mutation_indices = random.sample(range(len(individual)), num_mutations)
            for i in mutation_indices:
                current_val = individual[i]
                choices = [val for val in param_choices_map[i] if val != current_val]
                if choices:
                    individual[i] = random.choice(choices)
            return (individual,)

        toolbox.register("mutate", discrete_mutation)
        toolbox.register("select", tools.selTournament, tournsize=2)

        with Pool() as pool:
            toolbox.register("map", pool.map)
            pop = toolbox.population(n=population_size)
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
            for ind, (fit, comp, temp_dir) in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
                ind.comparison = comp
                ind.temp_output_dir = temp_dir
                all_temp_dirs.add(temp_dir)

            hall_of_fame.update(pop)
            best_ind = tools.selBest(pop, 1)[0]
            best_dirs_by_gen.append(getattr(best_ind, "temp_output_dir", None))

            # Save best individual bias/abs errors
            best_comp = best_ind.comparison
            for end_use, metrics in best_comp.items():
                for fuel_type, bias in metrics["Bias Error"].items():
                    key = f"{end_use}_{fuel_type}"
                    best_bias_series.setdefault(key, []).append(bias)
                    best_abs_series.setdefault(key, []).append(abs(bias))

            # Log generation 0
            record = stats.compile(pop)
            record.update({f"bias_error_{k}": v[-1] for k, v in best_bias_series.items()})
            record.update({f"abs_error_{k}": v[-1] for k, v in best_abs_series.items()})
            record["best_individual"] = list(best_ind)
            record["diversity"] = diversity(pop)
            record["best_individual_filepath"] = str(best_ind.temp_output_dir)
            logbook.record(gen=0, nevals=len(invalid_ind), **record)
            print(logbook.stream)

            for gen in range(1, generations + 1):
                # Elitism: Copy the best individuals
                elite = [copy.deepcopy(ind) for ind in tools.selBest(pop, k=1)]

                # Generate offspring
                offspring = algorithms.varAnd(pop, toolbox, cxpb=0.4, mutpb=0.2)

                # Evaluate offspring
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
                for ind, (fit, comp, temp_dir) in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit
                    ind.comparison = comp
                    ind.temp_output_dir = temp_dir
                    all_temp_dirs.add(temp_dir)

                # Select next generation (excluding elites), then add elites
                pop = toolbox.select(offspring, population_size - len(elite))
                pop.extend(elite)

                # Update Hall of Fame and stats
                hall_of_fame.update(pop)
                best_ind = tools.selBest(pop, 1)[0]
                best_dirs_by_gen.append(getattr(best_ind, "temp_output_dir", None))

                # Save hall of fame bias/abs errors
                best_comp = best_ind.comparison
                for end_use, metrics in best_comp.items():
                    for fuel_type, bias in metrics["Bias Error"].items():
                        key = f"{end_use}_{fuel_type}"
                        best_bias_series.setdefault(key, []).append(bias)
                        best_abs_series.setdefault(key, []).append(abs(bias))

                record = stats.compile(pop)
                record.update(
                    {f"bias_error_{k}": best_bias_series[k][-1] for k in best_bias_series}
                )
                record.update({f"abs_error_{k}": best_abs_series[k][-1] for k in best_abs_series})
                record["best_individual"] = list(best_ind)
                record["diversity"] = diversity(pop)
                record["best_individual_filepath"] = str(best_ind.temp_output_dir)
                logbook.record(gen=gen, nevals=len(invalid_ind), **record)
                print(logbook.stream)

        best_individual = hall_of_fame[0]

        # Cleanup
        for temp_dir in all_temp_dirs:
            if temp_dir not in best_dirs_by_gen and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        return best_individual, pop, logbook, best_bias_series, best_abs_series
