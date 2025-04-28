import logging
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from .hpxml import HpxmlDoc
from .utils import OS_HPXML_PATH, convert_c_to_f
from .weather_normalization import regression as reg
from .weather_normalization import utility_data as ud

_log = logging.getLogger(__name__)


class Calibrate:
    def __init__(self, original_hpxml_filepath: Path):
        self.hpxml = HpxmlDoc(Path(original_hpxml_filepath).resolve())
        self.epw_data, self.epw_metadata = self.hpxml.get_epw_data()

    def normalize_bills(self) -> dict:
        lat, lon = ud.get_lat_lon_from_hpxml(self.hpxml)
        bills_by_fuel_type, bill_units, tz = ud.get_bills_from_hpxml(self.hpxml)

        # generate models and compare weather files
        normalized_usage = {}
        for fuel_type, bills in bills_by_fuel_type.items():
            # Rudimentary check for delivered fuels
            if bills.shape[0] < 10:
                continue

            bills["days_in_bill"] = (bills["end_date"] - bills["start_date"]).dt.days

            # calculate mean temp of tmy data between bill dates
            def calculate_wrapped_mean(row):
                start = row["start_hour"]
                end = row["end_hour"]

                if start <= end:
                    subset = self.epw_data.iloc[start : end + 1]  # +1 to include end_hour
                else:
                    # handle bills that wrap around the end of the year
                    part1 = self.epw_data.iloc[start:]
                    part2 = self.epw_data.iloc[0 : end + 1]
                    subset = pd.concat([part1, part2])

                return subset["temp_air"].mean()

            bills["mean_temp_air_tmy"] = bills.apply(calculate_wrapped_mean, axis=1)

            bills["mean_temp_air_tmy_fahrenheit"] = convert_c_to_f(
                bills["mean_temp_air_tmy"]
            ).round(2)
            bills_temps = ud.join_bills_weather(bills, lat, lon)
            model = reg.fit_model(bills_temps, bpi2400=False)
            temps_range = np.linspace(bills_temps["avg_temp"].min(), bills_temps["avg_temp"].max())
            model(temps_range)
            model.calc_cvrmse(bills_temps)
            daily_baseload = model.parameters[0]
            if len(model.parameters) == 3:
                slope = model.parameters[1]
                if slope < 0:
                    low_temp_inflection_point = model.parameters[2]
                    high_temp_inflection_point = None
                elif slope > 0:
                    high_temp_inflection_point = model.parameters[2]
                    low_temp_inflection_point = None
                else:
                    _log.warning(
                        "Slope is zero, meaning utility data does not appear to be related to temperature."
                    )
            elif len(model.parameters) == 5:
                # low_slope = model.parameters[1]
                # high_slope = model.parameters[2]
                low_temp_inflection_point = model.parameters[3]
                high_temp_inflection_point = model.parameters[4]

            normalized_temps_range = bills["mean_temp_air_tmy_fahrenheit"].to_numpy()
            normalized_daily_consumption_pred = model(normalized_temps_range)
            normalized_heating_usage, normalized_cooling_usage = self.calculate_normalized_loads(
                daily_baseload,
                normalized_daily_consumption_pred,
                bills["mean_temp_air_tmy_fahrenheit"],
                low_temp_inflection_point,
                high_temp_inflection_point,
            )
            normalized_heating_usage_monthly = (
                normalized_heating_usage * bills["days_in_bill"].to_numpy()
            )
            normalized_cooling_usage_monthly = (
                normalized_cooling_usage * bills["days_in_bill"].to_numpy()
            )

            normalized_usage[fuel_type] = (
                normalized_heating_usage_monthly,
                normalized_cooling_usage_monthly,
            )

        return normalized_usage

        # TODO: read from user's output file
        # annual_json_results_path = (
        #     Path(__file__).parent.parent.parent / "tests" / "run" / "results_annual.json"
        # )

        # self.annual_results = json.loads(annual_json_results_path.read_text())
        # heating_energy, cooling_energy, hot_water_energy, lighting_energy, other_energy = (
        #     self.parse_hpxml_output()
        # )
        # modify_xml_measure()
        # self.parse_hpxml_output()

        # # Percent Difference
        # # |Value1 - Value2| [abs diff of values] / (Value1 + Value2) / 2 [mean of the two values]
        # high_elec_difference = electricity_usages.max() - highest_modeled_elec_usage
        # mean_high_elec_value = mean(electricity_usages.max(), highest_modeled_elec_usage)
        # low_elec_difference = electricity_usages.min() - lowest_modeled_elec_usage
        # mean_low_elec_value = mean(electricity_usages.min(), lowest_modeled_elec_usage)
        # high_gas_difference = gas_usages.max() - highest_modeled_gas_usage
        # mean_high_gas_value = mean(gas_usages.max(), highest_modeled_gas_usage)
        # low_gas_difference = gas_usages.min() - lowest_modeled_gas_usage
        # mean_low_gas_value = mean(gas_usages.min(), lowest_modeled_gas_usage)

        # # Calibrate if highest measured usage is more than 25% different from highest modeled usage
        # if (
        #     abs(high_elec_difference) / mean_high_elec_value > 0.25
        #     or abs(high_gas_difference) / mean_high_gas_value > 0.25
        #     or abs(low_elec_difference) / mean_low_elec_value > 0.25
        #     or abs(low_gas_difference) / mean_low_gas_value > 0.25
        # ):
        #     self.calibrate(self.osw_file)

    def calculate_normalized_loads(
        self,
        baseload,
        predictions,
        mean_tmy_temp,
        low_inflection_point=None,
        high_inflection_point=None,
    ):
        """
        Calculate heating/cooling loads with optional single inflection point support.

        Args:
            baseload: Base energy load (float)
            predictions: List of 12 monthly predicted loads
            mean_tmy_temp: Pandas Series of 12 monthly mean temperatures
            low_inflection_point: Optional heating threshold
            high_inflection_point: Optional cooling threshold

        Returns:
            Tuple of (heating_loads, cooling_loads) as numpy arrays
        """
        predictions = np.array(predictions)
        temps = mean_tmy_temp.to_numpy()

        heating_mask = np.full_like(temps, False, dtype=bool)
        cooling_mask = np.full_like(temps, False, dtype=bool)

        if low_inflection_point is not None:
            heating_mask = temps < low_inflection_point
        if high_inflection_point is not None:
            cooling_mask = temps > high_inflection_point

        heating_loads = np.where(heating_mask, predictions - baseload, 0)
        cooling_loads = np.where(cooling_mask, predictions - baseload, 0)

        return heating_loads, cooling_loads

    def parse_hpxml_output(self):
        # mismatch number of values to unpack to force a test error temporarily
        heating_energy, cooling_energy, hot_water_energy, lighting_energy, other_energy = (
            0,
            0,
            0,
            0,
            0,
        )
        for end_use, mbtu in self.annual_results["End Use"].items():
            if "Heating" in end_use:
                heating_energy += mbtu
            elif "Cooling" in end_use:
                cooling_energy += mbtu
            elif "Hot Water" in end_use:
                hot_water_energy += mbtu
            elif "Lighting" in end_use:
                lighting_energy += mbtu
            else:
                other_energy += mbtu

        return heating_energy, cooling_energy, hot_water_energy, lighting_energy, other_energy

    def run_simulation(self):
        run_simulation_command = [
            "openstudio",
            str(OS_HPXML_PATH / "workflow" / "run_simulation.rb"),
            "--xml",
            self.original_hpxml.file_path,
        ]

        subprocess.run(
            run_simulation_command,
            capture_output=True,
            check=True,
        )

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
