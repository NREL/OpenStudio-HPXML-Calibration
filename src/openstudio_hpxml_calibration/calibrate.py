import json
from pathlib import Path

import pandas as pd
from loguru import logger

from openstudio_hpxml_calibration.hpxml import FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel


class Calibrate:
    def __init__(self, original_hpxml_filepath: Path):
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())
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
        #         for end_use, consumption_list in results["End Use"].items():
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
                        <load_type>: <percentage error>
                    },
                    "Absolute Error": {
                        <load_type>: <error in mbtu or kWh>
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
                    consumption[end_use].sum().round(3)
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
                        # convert from mbtu to kWh
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
                        3,
                    )
                    comparison_results[model_fuel_type]["Absolute Error"][load_type] = round(
                        abs(
                            annual_normalized_bill_consumption[model_fuel_type][load_type]
                            - disagg_results[load_type]
                        ),
                        3,
                    )
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

    # def run_simulation(self):
    #     run_simulation_command = [
    #         "openstudio",
    #         str(OS_HPXML_PATH / "workflow" / "run_simulation.rb"),
    #         "--xml",
    #         self.original_hpxml.file_path,
    #     ]

    #     subprocess.run(
    #         run_simulation_command,
    #         capture_output=True,
    #         check=True,
    #     )

    # def calibrate(self, workflow_file):
    # modify_xml_command = [
    #     "openstudio",
    #     "run",
    #     "--workflow",
    #     str(workflow_file),
    #     "--measures_only",
    # ]

    # subprocess.run(
    #     modify_xml_command,
    #     capture_output=True,
    #     check=True,
    # )
