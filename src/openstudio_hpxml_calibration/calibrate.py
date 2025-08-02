import copy
import json
import random
import shutil
import tempfile
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import yaml
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


def load_config(config_filename="ga_config.yaml", default={}):
    config_path = Path(__file__).parent / config_filename
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return merge_with_defaults(config, default)


def merge_with_defaults(user_config, default_config):
    """Merge default values into user's config"""
    if not isinstance(user_config, dict):
        return user_config
    merged = default_config.copy()
    for key, val in user_config.items():
        if key in merged and isinstance(merged[key], dict):
            merged[key] = merge_with_defaults(val, merged[key])
        else:
            merged[key] = val
    return merged


class Calibrate:
    def __init__(self, original_hpxml_filepath: Path, csv_bills_filepath: Path | None = None):
        default_ga_config = {
            "genetic_algorithm": {
                "population_size": 70,
                "generations": 100,
                "crossover_probability": 0.4,
                "mutation_probability": 0.4,
                "bias_error_threshold": 10,
                "abs_error_elec_threshold": 500,
                "abs_error_fuel_threshold": 5,
            },
            "value_choices": {
                "misc_load_pct_choices": [round(x * 0.1, 1) for x in range(-9, 11)] + [5, 10],
                "air_leakage_pct_choices": [round(x * 0.1, 1) for x in range(-5, 11)] + [2],
                "hvac_eff_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "roof_r_value_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "ceiling_r_value_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "above_ground_walls_r_value_pct_choices": [
                    round(x * 0.1, 2) for x in range(-2, 13)
                ],
                "below_ground_walls_r_value_pct_choices": [
                    round(x * 0.1, 2) for x in range(-2, 13)
                ],
                "slab_r_value_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "floor_r_value_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "heating_setpoint_choices": [-5, -3, -1, 0, 1, 3, 5],
                "cooling_setpoint_choices": [-5, -3, -1, 0, 1, 3, 5],
                "water_heater_efficiency_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "water_fixtures_usage_pct_choices": [round(x * 0.1, 1) for x in range(-9, 11)]
                + [5, 10],
                "window_u_factor_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "window_shgc_pct_choices": [round(x * 0.1, 2) for x in range(-2, 13)],
                "appliance_usage_pct_choices": [round(x * 0.1, 1) for x in range(-9, 11)] + [5, 10],
                "lighting_load_pct_choices": [round(x * 0.1, 1) for x in range(-9, 11)] + [5, 10],
            },
        }
        self.hpxml_filepath = Path(original_hpxml_filepath).resolve()
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())
        self.ga_config = load_config(config_filename="ga_config.yaml", default=default_ga_config)

        if csv_bills_filepath:
            logger.info(f"Adding utility data from {csv_bills_filepath} to hpxml")
            self.hpxml = set_consumption_on_hpxml(self.hpxml, csv_bills_filepath)

        self.hpxml_data_error_checking()

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
            # ignore electricity usage for heating (fans/pumps) when electricity is not the fuel type for any heating system
            if (
                fuel_type == "electricity"
                and "Heating" in end_use
                and FuelType.ELECTRICITY.value
                not in self.hpxml.get_fuel_types()[0]  # heating fuels
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

    def hpxml_data_error_checking(self) -> None:
        """Check for common HPXML errors

        :raises ValueError: If an error is found
        """
        now = dt.now()
        building = self.hpxml.get_building()
        try:
            consumption = self.hpxml.get_consumption()
        except IndexError:
            raise ValueError("No Consumption section found in HPXML file.")

        # Check that the building doesn't have PV
        try:
            building.BuildingDetails.Systems.Photovoltaics
            raise ValueError("PV is not supported with automated calibration at this time.")
        except AttributeError:
            pass

        # Check that consumption types are appropriate (not mixing Energy and Water)
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            try:
                if fuel.ConsumptionType.Energy.FuelType in FuelType._value2member_map_:
                    continue
            except AttributeError:
                raise ValueError(
                    "ConsumptionType.Energy.FuelType is missing or not recognized in Consumption. "
                    "We only calibrate energy consumption, not water."
                )

        # Check that build ID matches consumption BuildingID
        if not consumption.BuildingID.attrib["idref"] == building.BuildingID.attrib["id"]:
            raise ValueError(
                f"Consumption BuildingID idref '{consumption.BuildingID.attrib['idref']}' does "
                f"not match Building ID '{building.BuildingID.attrib['id']}'"
            )

        # Check consumption energy units are appropriate for the fuel type
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            match fuel.ConsumptionType.Energy.FuelType:
                case FuelType.ELECTRICITY.value:
                    if fuel.ConsumptionType.Energy.UnitofMeasure not in ("kWh", "MWh"):
                        raise ValueError(
                            "Electricity consumption unit must be 'kWh' or 'MWh', "
                            f"got '{fuel.ConsumptionType.Energy.UnitofMeasure}'"
                        )
                case FuelType.NATURAL_GAS.value:
                    if fuel.ConsumptionType.Energy.UnitofMeasure not in (
                        "therms",
                        "Btu",
                        "kBtu",
                        "MBtu",
                        "ccf",
                        "kcf",
                        "Mcf",
                    ):
                        raise ValueError(
                            "Natural gas consumption unit must be 'therm' or 'CCF', "
                            f"got '{fuel.ConsumptionType.Energy.UnitofMeasure}'"
                        )
                case FuelType.FUEL_OIL.value:
                    if fuel.ConsumptionType.Energy.UnitofMeasure not in (
                        "gal",
                        "Btu",
                        "kBtu",
                        "MBtu",
                    ):
                        raise ValueError(
                            f"Fuel oil consumption unit must be 'gal', 'Btu', 'kBtu', or 'MBtu', "
                            f"got '{fuel.ConsumptionType.Energy.UnitofMeasure}'"
                        )
                case FuelType.PROPANE.value:
                    if fuel.ConsumptionType.Energy.UnitofMeasure not in (
                        "gal",
                        "Btu",
                        "kBtu",
                        "MBtu",
                    ):
                        raise ValueError(
                            f"Propane consumption unit must be 'gal', 'Btu', 'kBtu', or 'MBtu', "
                            f"got '{fuel.ConsumptionType.Energy.UnitofMeasure}'"
                        )
                case _:
                    raise ValueError(
                        f"Unsupported fuel type '{fuel.ConsumptionType.Energy.FuelType}' with "
                        f"unit '{fuel.ConsumptionType.Energy.UnitofMeasure}'"
                    )

        # Check that consumption dates have no gaps nor are overlapping
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            details = fuel.ConsumptionDetail
            for i, detail in enumerate(details):
                # Check that start and end dates are present
                try:
                    start_date = dt.strptime(str(detail.StartDateTime), "%Y-%m-%dT%H:%M:%S")
                except AttributeError:
                    raise ValueError(
                        f"Consumption detail {i} for {fuel.ConsumptionType.Energy.FuelType} is missing StartDateTime."
                    )
                try:
                    end_date = dt.strptime(str(detail.EndDateTime), "%Y-%m-%dT%H:%M:%S")
                except AttributeError:
                    raise ValueError(
                        f"Consumption detail {i} for {fuel.ConsumptionType.Energy.FuelType} is missing EndDateTime."
                    )
                # Compare with previous detail if not the first
                if i > 0:
                    prev_detail = details[i - 1]
                    if detail.StartDateTime < prev_detail.EndDateTime:
                        raise ValueError(
                            f"Consumption details for {fuel.ConsumptionType.Energy.FuelType} overlap: "
                            f"{prev_detail.StartDateTime} - {prev_detail.EndDateTime} overlaps with "
                            f"{detail.StartDateTime} - {detail.EndDateTime}"
                        )
                    if detail.StartDateTime > prev_detail.EndDateTime:
                        raise ValueError(
                            f"Gap in consumption data for {fuel.ConsumptionType.Energy.FuelType}: "
                            f"Period between {prev_detail.EndDateTime} and {detail.StartDateTime} is not covered.\n"
                            "Are the bill periods consecutive?"
                        )

        # Check that consumption values are above zero
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            for detail in fuel.ConsumptionDetail:
                if detail.Consumption <= 0:
                    raise ValueError(
                        f"Consumption value for {fuel.ConsumptionType.Energy.FuelType} cannot be "
                        f"zero or negative for bill-period: {detail.StartDateTime}"
                    )

        # Check if consumption is estimated
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            for detail in fuel.ConsumptionDetail:
                try:
                    reading_type = str(detail.ReadingType)
                    if reading_type.lower() == "estimate":
                        # TODO: bump to simplified calibration instead of raising an error
                        raise ValueError(
                            f"Estimated consumption value for {fuel.ConsumptionType.Energy.FuelType} cannot be greater than zero for bill-period: {detail.StartDateTime}"
                        )
                except AttributeError:
                    # If there is no ReadingType, assume it's not estimated
                    pass

        # Check that there is only one consumption section per fuel type
        fuel_types = set()
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            fuel_type = fuel.ConsumptionType.Energy.FuelType
            if fuel_type in fuel_types:
                raise ValueError(
                    f"Multiple Consumption sections found for fuel type '{fuel_type}'. "
                    "Only one section per fuel type is allowed."
                )
            fuel_types.add(fuel_type)

        # Check that electricity consumption is present
        if FuelType.ELECTRICITY.value not in fuel_types:
            raise ValueError(
                "Electricity consumption is required for calibration. "
                "Please provide electricity consumption data in the HPXML file."
            )

        # Check that the consumed fuel matches the equipment fuel type
        try:
            heating_fuel_type = (
                building.BuildingDetails.Systems.HVAC.HVACPlant.HeatingSystem.HeatingSystemFuel
            )
        except AttributeError:
            raise ValueError(
                "Heating system fuel type is missing in the HPXML file. "
                "Please provide the heating system fuel type in the HPXML file."
            )
        try:
            water_heating_fuel_type = (
                building.BuildingDetails.Systems.WaterHeating.WaterHeatingSystem.FuelType
            )
        except AttributeError:
            raise ValueError(
                "Water heating system fuel type is missing in the HPXML file. "
                "Please provide the water heating system fuel type in the HPXML file."
            )
        try:
            clothes_dryer_fuel_type = building.BuildingDetails.Appliances.ClothesDryer.FuelType
        except AttributeError:
            raise ValueError(
                "Clothes dryer fuel type is missing in the HPXML file. "
                "Please provide the clothes dryer fuel type in the HPXML file."
            )
        if heating_fuel_type not in fuel_types:
            raise ValueError(
                f"Heating equipment fuel type {heating_fuel_type} does not match any consumption "
                f"fuel type. Consumption fuel types: {fuel_types}."
            )
        if water_heating_fuel_type not in fuel_types:
            raise ValueError(
                f"Heating equipment fuel type {water_heating_fuel_type} does not match any consumption "
                f"fuel type. Consumption fuel types: {fuel_types}."
            )
        if clothes_dryer_fuel_type not in fuel_types:
            raise ValueError(
                f"Heating equipment fuel type {clothes_dryer_fuel_type} does not match any consumption "
                f"fuel type. Consumption fuel types: {fuel_types}."
            )

        # Check that electricity has at least 10 bill periods per year
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            if fuel.ConsumptionType.Energy.FuelType == FuelType.ELECTRICITY.value:
                num_elec_bills = len(fuel.ConsumptionDetail)
                if num_elec_bills < 10:
                    raise ValueError(
                        f"Electricity consumption must have at least 10 bill periods, found {num_elec_bills}."
                    )

        # Check that the consumption dates are within the past 5 years
        for fuel in consumption.ConsumptionDetails.ConsumptionInfo:
            # Check that there are at least 330 days of consumption data
            if (
                dt.strptime(str(fuel.ConsumptionDetail[-1].EndDateTime), "%Y-%m-%dT%H:%M:%S")
                - dt.strptime(str(fuel.ConsumptionDetail[0].StartDateTime), "%Y-%m-%dT%H:%M:%S")
            ).days < 330:
                raise ValueError(
                    f"Consumption dates for {fuel.ConsumptionType.Energy.FuelType} must cover at least 330 days."
                )
            for idx, detail in enumerate(fuel.ConsumptionDetail):
                # Check that StartDateTime and EndDateTime are present
                start_date = dt.strptime(str(detail.StartDateTime), "%Y-%m-%dT%H:%M:%S")
                end_date = dt.strptime(str(detail.EndDateTime), "%Y-%m-%dT%H:%M:%S")

                # Check that dates are within the past 5 years
                if start_date > now or end_date > now:
                    raise ValueError(
                        f"Consumption dates {start_date} - {end_date} cannot be in the future."
                    )
                if (now - start_date).days > 5 * 365 or (now - end_date).days > 5 * 365:
                    raise ValueError(
                        f"Consumption dates {start_date} - {end_date} must be within the past 5 years."
                    )

                # Check that electricity bill periods are between 20 & 45 days
                longest_bill_period = 45  # days
                shortest_bill_period = 20  # days
                if fuel.ConsumptionType.Energy.FuelType == FuelType.ELECTRICITY.value:
                    if (end_date - start_date).days > longest_bill_period:
                        raise ValueError(
                            f"Electricity consumption bill period {start_date} - {end_date} cannot be longer than {longest_bill_period} days."
                        )
                    if (end_date - start_date).days < shortest_bill_period:
                        raise ValueError(
                            f"Electricity consumption bill period {start_date} - {end_date} cannot be shorter than {shortest_bill_period} days."
                        )

    def run_ga_search(self, population_size=None, generations=None, cxpb=None, mutpb=None):
        all_temp_dirs = set()
        best_dirs_by_gen = []
        cfg = self.ga_config
        population_size = cfg["genetic_algorithm"]["population_size"]
        generations = cfg["genetic_algorithm"]["generations"]
        bias_error_threshold = cfg["genetic_algorithm"]["bias_error_threshold"]
        abs_error_elec_threshold = cfg["genetic_algorithm"]["abs_error_elec_threshold"]
        abs_error_fuel_threshold = cfg["genetic_algorithm"]["abs_error_fuel_threshold"]
        cxpb = cfg["genetic_algorithm"]["crossover_probability"]
        mutpb = cfg["genetic_algorithm"]["mutation_probability"]
        misc_load_pct_choices = cfg["value_choices"]["misc_load_pct_choices"]
        air_leakage_pct_choices = cfg["value_choices"]["air_leakage_pct_choices"]
        hvac_eff_pct_choices = cfg["value_choices"]["hvac_eff_pct_choices"]
        roof_r_value_pct_choices = cfg["value_choices"]["roof_r_value_pct_choices"]
        ceiling_r_value_pct_choices = cfg["value_choices"]["ceiling_r_value_pct_choices"]
        above_ground_walls_r_value_pct_choices = cfg["value_choices"][
            "above_ground_walls_r_value_pct_choices"
        ]
        below_ground_walls_r_value_pct_choices = cfg["value_choices"][
            "below_ground_walls_r_value_pct_choices"
        ]
        slab_r_value_pct_choices = cfg["value_choices"]["slab_r_value_pct_choices"]
        floor_r_value_pct_choices = cfg["value_choices"]["floor_r_value_pct_choices"]
        heating_setpoint_choices = cfg["value_choices"]["heating_setpoint_choices"]
        cooling_setpoint_choices = cfg["value_choices"]["cooling_setpoint_choices"]
        water_heater_efficiency_pct_choices = cfg["value_choices"][
            "water_heater_efficiency_pct_choices"
        ]
        water_fixtures_usage_pct_choices = cfg["value_choices"]["water_fixtures_usage_pct_choices"]
        window_u_factor_pct_choices = cfg["value_choices"]["window_u_factor_pct_choices"]
        window_shgc_pct_choices = cfg["value_choices"]["window_shgc_pct_choices"]
        appliance_usage_pct_choices = cfg["value_choices"]["appliance_usage_pct_choices"]
        lighting_load_pct_choices = cfg["value_choices"]["lighting_load_pct_choices"]

        def evaluate(individual):
            (
                misc_load_pct_change,
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
                water_heater_efficiency_pct_change,
                water_fixtures_usage_pct_change,
                window_u_factor_pct_change,
                window_shgc_pct_change,
                appliance_usage_pct_change,
                lighting_load_pct_change,
            ) = individual
            temp_output_dir = Path(tempfile.mkdtemp(prefix="calib_test_"))
            mod_hpxml_path = temp_output_dir / "modified.xml"
            arguments = {
                "xml_file_path": str(self.hpxml_filepath),
                "save_file_path": str(mod_hpxml_path),
                "heating_setpoint_offset": heating_setpoint_offset,
                "cooling_setpoint_offset": cooling_setpoint_offset,
                "misc_load_pct_change": misc_load_pct_change,
                "air_leakage_pct_change": air_leakage_pct_change,
                "heating_efficiency_pct_change": heating_efficiency_pct_change,
                "cooling_efficiency_pct_change": cooling_efficiency_pct_change,
                "roof_r_value_pct_change": roof_r_value_pct_change,
                "ceiling_r_value_pct_change": ceiling_r_value_pct_change,
                "above_ground_walls_r_value_pct_change": above_ground_walls_r_value_pct_change,
                "below_ground_walls_r_value_pct_change": below_ground_walls_r_value_pct_change,
                "slab_r_value_pct_change": slab_r_value_pct_change,
                "floor_r_value_pct_change": floor_r_value_pct_change,
                "water_heater_efficiency_pct_change": water_heater_efficiency_pct_change,
                "water_fixtures_usage_pct_change": water_fixtures_usage_pct_change,
                "window_u_factor_pct_change": window_u_factor_pct_change,
                "window_shgc_pct_change": window_shgc_pct_change,
                "appliance_usage_pct_change": appliance_usage_pct_change,
                "lighting_load_pct_change": lighting_load_pct_change,
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

            bias_error_penalties = []
            for fuel_type, metrics in comparison.items():
                for end_use, bias_error in metrics["Bias Error"].items():
                    bias_error_penalty = max(0, abs(bias_error)) ** 2
                    # if absolute error is within the bpi2400 criteria, relax the penalty
                    if abs_error_within_threshold(
                        fuel_type,
                        abs(metrics["Absolute Error"][end_use]),
                        abs_error_elec_threshold,
                        abs_error_fuel_threshold,
                    ):
                        penalty_relaxation_factor = 0.2
                        bias_error_penalty *= penalty_relaxation_factor

                    bias_error_penalties.append(bias_error_penalty)

            total_score = sum(bias_error_penalties)

            return (total_score,), comparison, temp_output_dir

        def abs_error_within_threshold(
            fuel_type: str, abs_error: float, elec_threshold: float, fuel_threshold: float
        ) -> bool:
            if fuel_type == "electricity":
                return abs(abs_error) <= elec_threshold
            else:
                return abs(abs_error) <= fuel_threshold

        def create_measure_input_file(arguments: dict, output_file_path: str):
            data = {
                "run_directory": str(Path(arguments["save_file_path"]).parent),
                "measure_paths": [str(Path(__file__).resolve().parent.parent / "measures")],
                "steps": [{"measure_dir_name": "ModifyXML", "arguments": arguments}],
            }
            Path(output_file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        def diversity(pop):
            return len({tuple(ind) for ind in pop}) / len(pop)

        toolbox = base.Toolbox()
        toolbox.register("attr_misc_load_pct_change", random.choice, misc_load_pct_choices)
        toolbox.register("attr_heating_setpoint_offset", random.choice, heating_setpoint_choices)
        toolbox.register("attr_cooling_setpoint_offset", random.choice, cooling_setpoint_choices)
        toolbox.register("attr_air_leakage_pct_change", random.choice, air_leakage_pct_choices)
        toolbox.register("attr_heating_efficiency_pct_change", random.choice, hvac_eff_pct_choices)
        toolbox.register("attr_cooling_efficiency_pct_change", random.choice, hvac_eff_pct_choices)
        toolbox.register("attr_roof_r_value_pct_change", random.choice, roof_r_value_pct_choices)
        toolbox.register(
            "attr_ceiling_r_value_pct_change", random.choice, ceiling_r_value_pct_choices
        )
        toolbox.register(
            "attr_above_ground_walls_r_value_pct_change",
            random.choice,
            above_ground_walls_r_value_pct_choices,
        )
        toolbox.register(
            "attr_below_ground_walls_r_value_pct_change",
            random.choice,
            below_ground_walls_r_value_pct_choices,
        )
        toolbox.register("attr_slab_r_value_pct_change", random.choice, slab_r_value_pct_choices)
        toolbox.register("attr_floor_r_value_pct_change", random.choice, floor_r_value_pct_choices)
        toolbox.register(
            "attr_water_heater_efficiency_pct_change",
            random.choice,
            water_heater_efficiency_pct_choices,
        )
        toolbox.register(
            "attr_water_fixtures_usage_pct_change", random.choice, water_fixtures_usage_pct_choices
        )
        toolbox.register(
            "attr_window_u_factor_pct_change", random.choice, window_u_factor_pct_choices
        )
        toolbox.register("attr_window_shgc_pct_change", random.choice, window_shgc_pct_choices)
        toolbox.register(
            "attr_appliance_usage_pct_change", random.choice, appliance_usage_pct_choices
        )
        toolbox.register("attr_lighting_load_pct_change", random.choice, lighting_load_pct_choices)
        toolbox.register(
            "individual",
            tools.initRepeat,
            creator.Individual,
            (
                toolbox.attr_misc_load_pct_change,
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
                toolbox.attr_water_heater_efficiency_pct_change,
                toolbox.attr_water_fixtures_usage_pct_change,
                toolbox.attr_window_u_factor_pct_change,
                toolbox.attr_window_shgc_pct_change,
                toolbox.attr_appliance_usage_pct_change,
                toolbox.attr_lighting_load_pct_change,
            ),
            n=18,
        )

        def generate_random_individual():
            return creator.Individual(
                [
                    random.choice(misc_load_pct_choices),
                    random.choice(heating_setpoint_choices),
                    random.choice(cooling_setpoint_choices),
                    random.choice(air_leakage_pct_choices),
                    random.choice(hvac_eff_pct_choices),
                    random.choice(hvac_eff_pct_choices),
                    random.choice(roof_r_value_pct_choices),
                    random.choice(ceiling_r_value_pct_choices),
                    random.choice(above_ground_walls_r_value_pct_choices),
                    random.choice(below_ground_walls_r_value_pct_choices),
                    random.choice(slab_r_value_pct_choices),
                    random.choice(floor_r_value_pct_choices),
                    random.choice(water_heater_efficiency_pct_choices),
                    random.choice(water_fixtures_usage_pct_choices),
                    random.choice(window_u_factor_pct_choices),
                    random.choice(window_shgc_pct_choices),
                    random.choice(appliance_usage_pct_choices),
                    random.choice(lighting_load_pct_choices),
                ]
            )

        toolbox.register("individual", generate_random_individual)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("evaluate", evaluate)
        toolbox.register("mate", tools.cxUniform, indpb=cxpb)

        # Define parameter-to-choices mapping for mutation
        param_choices_map = {
            0: misc_load_pct_choices,
            1: heating_setpoint_choices,
            2: cooling_setpoint_choices,
            3: air_leakage_pct_choices,
            4: hvac_eff_pct_choices,
            5: hvac_eff_pct_choices,
            6: roof_r_value_pct_choices,
            7: ceiling_r_value_pct_choices,
            8: above_ground_walls_r_value_pct_choices,
            9: below_ground_walls_r_value_pct_choices,
            10: slab_r_value_pct_choices,
            11: floor_r_value_pct_choices,
            12: water_heater_efficiency_pct_choices,
            13: water_fixtures_usage_pct_choices,
            14: window_u_factor_pct_choices,
            15: window_shgc_pct_choices,
            16: appliance_usage_pct_choices,
            17: lighting_load_pct_choices,
        }

        worst_end_uses_by_gen = []

        end_use_param_map = {
            "electricity_heating": [1, 3, 4, 6, 7, 8, 10, 14, 15],
            "electricity_cooling": [2, 3, 5, 6, 7, 8, 10, 14, 15],
            "electricity_baseload": [0, 16, 17],
            "natural_gas_heating": [1, 3, 4, 6, 7, 8, 10, 14, 15],
            "natural_gas_baseload": [12, 13],
        }

        def get_worst_bias_end_use(comparison):
            max_bias = -float("inf")
            worst_end_use_key = None
            for fuel_type, metrics in comparison.items():
                for end_use, bias in metrics["Bias Error"].items():
                    abs_bias = abs(bias)
                    key = f"{fuel_type}_{end_use}"
                    if abs_bias > max_bias:
                        max_bias = abs_bias
                        worst_end_use_key = key
            return worst_end_use_key

        def adaptive_mutation(individual):
            mutation_indices = set()

            if worst_end_uses_by_gen:
                worst_end_use = worst_end_uses_by_gen[-1]
                impacted_indices = end_use_param_map.get(worst_end_use, [])
                if impacted_indices:
                    mutation_indices.update(
                        random.sample(impacted_indices, min(len(impacted_indices), 2))
                    )

            while len(mutation_indices) < random.randint(3, 6):
                mutation_indices.add(random.randint(0, len(individual) - 1))

            for i in mutation_indices:
                current_val = individual[i]
                choices = [val for val in param_choices_map[i] if val != current_val]
                if choices:
                    individual[i] = random.choice(choices)
            return (individual,)

        toolbox.register("mutate", adaptive_mutation)
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
                for fuel_type, bias_error in metrics["Bias Error"].items():
                    key = f"{end_use}_{fuel_type}"
                    best_bias_series.setdefault(key, []).append(bias_error)
                for fuel_type, abs_error in metrics["Absolute Error"].items():
                    key = f"{end_use}_{fuel_type}"
                    best_abs_series.setdefault(key, []).append(abs_error)

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
                offspring = algorithms.varAnd(pop, toolbox, cxpb=cxpb, mutpb=mutpb)

                # Evaluate offspring
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
                for ind, (fit, comp, temp_dir) in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit
                    ind.comparison = comp
                    ind.temp_output_dir = temp_dir
                    all_temp_dirs.add(temp_dir)

                # Select next generation (excluding elites), then add elites
                if invalid_ind:
                    worst_key = get_worst_bias_end_use(invalid_ind[0].comparison)
                    worst_end_uses_by_gen.append(worst_key)

                pop = toolbox.select(offspring, population_size - len(elite))
                pop.extend(elite)

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

                # Early termination conditions
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

                if meets_termination_criteria(best_comp):
                    print(f"Early stopping: termination criteria met at generation {gen}")
                    record["terminated_early"] = True
                    break

        best_individual = hall_of_fame[0]

        # Cleanup
        for temp_dir in all_temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return best_individual, pop, logbook, best_bias_series, best_abs_series
