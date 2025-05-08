import json
import logging
from pathlib import Path

import pandas as pd

from openstudio_hpxml_calibration.hpxml import FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units
from openstudio_hpxml_calibration.weather_normalization.inverse_model import InverseModel

_log = logging.getLogger(__name__)


class Calibrate:
    def __init__(self, original_hpxml_filepath: Path):
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())
        self.inv_model = InverseModel(self.hpxml)

    def get_normalized_consumption_per_bill(self) -> dict[FuelType, list[float]]:
        """
        Get the normalized consumption for the building.

        Returns:
            dict: A dictionary containing the normalized daily consumption for each fuel type, in kbtu.
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
                    subset = epw_daily.iloc[start:end].sum()
                else:
                    # handle bills that wrap around the end of the year
                    part1 = epw_daily.iloc[start:].sum()
                    part2 = epw_daily.iloc[0:end].sum()
                    subset = pd.concat([part1, part2])
                    subset = subset[~subset.index.duplicated()]

                return subset

            epw_daily = convert_units(self.inv_model.predict_epw_daily(fuel_type), "btu", "kbtu")

            normalized_consumption[fuel_type.value] = pd.DataFrame(
                bills.apply(_calculate_wrapped_total, axis=1)
            )
            normalized_consumption[fuel_type.value]["start_date"] = bills["start_date"]
            normalized_consumption[fuel_type.value]["end_date"] = bills["end_date"]

        return normalized_consumption

    def get_model_results(self, daily_json_results_path: Path):
        """
        Retrieve annual energy usage from the HPXML model.

        Args:
            annual_json_results_path (Path): Path to the JSON file containing annual results from the HPXML model

        Returns:
            Tuple of heating, cooling, hot water, lighting, and other energy usage in MBtu
        """

        daily_results = json.loads(daily_json_results_path.read_text())

        model_output = {}
        for fuel_type, bills in self.inv_model.bills_by_fuel_type.items():
            bill_dates = list(zip(bills["start_day_of_year"], bills["end_day_of_year"]))
            model_output[fuel_type.value] = {}
            for bill in bill_dates:
                for end_use, consumption_list in daily_results["End Use"].items():
                    if "Heating" in end_use:
                        if f"{bill}_heating_energy" in model_output[fuel_type.value]:
                            model_output[fuel_type.value][f"{bill}_heating_energy"] += sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                        else:
                            model_output[fuel_type.value][f"{bill}_heating_energy"] = sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                    elif "Cooling" in end_use:
                        if f"{bill}_cooling_energy" in model_output[fuel_type.value]:
                            model_output[fuel_type.value][f"{bill}_cooling_energy"] += sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                        else:
                            model_output[fuel_type.value][f"{bill}_cooling_energy"] = sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                    elif "Hot Water" in end_use:
                        if f"{bill}_hot_water_energy" in model_output[fuel_type.value]:
                            model_output[fuel_type.value][f"{bill}_hot_water_energy"] += sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                        else:
                            model_output[fuel_type.value][f"{bill}_hot_water_energy"] = sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                    elif "Lighting" in end_use:
                        if f"{bill}_lighting_energy" in model_output[fuel_type.value]:
                            model_output[fuel_type.value][f"{bill}_lighting_energy"] += sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                        else:
                            model_output[fuel_type.value][f"{bill}_lighting_energy"] = sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                    else:  # noqa: PLR5501
                        if f"{bill}_other_energy" in model_output[fuel_type.value]:
                            model_output[fuel_type.value][f"{bill}_other_energy"] += sum(
                                consumption_list[bill[0] : bill[1]]
                            )
                        else:
                            model_output[fuel_type.value][f"{bill}_other_energy"] = sum(
                                consumption_list[bill[0] : bill[1]]
                            )

        return model_output

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

    def read_value_from_hpxml(self, xpath):
        return self.original_hpxml.get_building().xpath(xpath)
