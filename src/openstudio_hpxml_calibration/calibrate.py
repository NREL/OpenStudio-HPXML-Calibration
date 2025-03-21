import logging
import subprocess
from pathlib import Path
from statistics import mean

from .hpxml import HpxmlDoc
from .utils import OS_HPXML_PATH

_log = logging.getLogger(__name__)


class Calibrate:
    def __init__(self, hp_xml: HpxmlDoc, osw_file: Path):
        self.hp_xml = hp_xml
        self.osw_file = osw_file.resolve()

        # Read these values from the utility data (either in the HPXML or user-provided csv)
        self.run_simulation()
        # Read monthly energy usages from simulation output
        lowest_modeled_elec_usage = 500
        highest_modeled_elec_usage = 1500
        highest_modeled_gas_usage = 300
        lowest_modeled_gas_usage = 10

        # Read measured utility usage from HPXML
        if self.hp_xml.get_building().Consumption:
            _log.info("Reading utility bills from HPXML")
            for bill in self.hp_xml.get_building().Consumption.ConsumptionDetails:
                if bill.ConsumptionInfo.ConsumptionType.Energy.FuelType == "electricity":
                    electricity_usages = [usage.Consumption for usage in bill.ConsumptionDetail]
                if bill.ConsumptionInfo.ConsumptionType.Energy.FuelType == "natural gas":
                    gas_usages = [usage.Consumption for usage in bill.ConsumptionDetail]
        else:
            # Read measured utility usage from user-provided csv
            print("Utility bills must be provided in the HPXML file")

        # Percent Difference
        # |Value1 - Value2| [abs diff of values] / (Value1 + Value2) / 2 [mean of the two values]
        high_elec_difference = electricity_usages.max() - highest_modeled_elec_usage
        mean_high_elec_value = mean(electricity_usages.max(), highest_modeled_elec_usage)
        low_elec_difference = electricity_usages.min() - lowest_modeled_elec_usage
        mean_low_elec_value = mean(electricity_usages.min(), lowest_modeled_elec_usage)
        high_gas_difference = gas_usages.max() - highest_modeled_gas_usage
        mean_high_gas_value = mean(gas_usages.max(), highest_modeled_gas_usage)
        low_gas_difference = gas_usages.min() - lowest_modeled_gas_usage
        mean_low_gas_value = mean(gas_usages.min(), lowest_modeled_gas_usage)

        # Calibrate if highest measured usage is more than 25% different from highest modeled usage
        if (
            abs(high_elec_difference) / mean_high_elec_value > 0.25
            or abs(high_gas_difference) / mean_high_gas_value > 0.25
            or abs(low_elec_difference) / mean_low_elec_value > 0.25
            or abs(low_gas_difference) / mean_low_gas_value > 0.25
        ):
            self.calibrate(self.osw_file)

    def run_simulation(self):
        run_simulation_command = [
            "openstudio",
            str(OS_HPXML_PATH / "workflow" / "run_simulation.rb"),
            "--xml",
            self.hp_xml.file_path,
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
        return self.hp_xml.get_building().xpath(xpath)
