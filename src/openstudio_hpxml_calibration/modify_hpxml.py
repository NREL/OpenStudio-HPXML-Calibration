from pathlib import Path

import pandas as pd
from loguru import logger
from lxml import objectify
from lxml.builder import ElementMaker

from openstudio_hpxml_calibration.hpxml import HpxmlDoc

# Define HPXML namespace
NS = "http://hpxmlonline.com/2023/09"
NSMAP = {None: NS}

# Define the element maker with namespace
E = ElementMaker(namespace=NS, nsmap=NSMAP)


def set_consumption_on_hpxml(hpxml_object: HpxmlDoc, csv_bills_filepath: Path) -> HpxmlDoc:
    """Add bills from csv to hpxml object"""

    bills = pd.read_csv(csv_bills_filepath)

    # Set up xml objects to hold the bill data
    # consumption_section = E.Consumption(
    #     E.BuildingID(idref=hpxml_object.get_first_building_id()),
    #     E.CustomerID(),
    #     E.ConsumptionDetails(),
    # )
    consumption_section = objectify.SubElement(hpxml_object.root, "Consumption", nsmap=NSMAP)
    objectify.SubElement(
        consumption_section, "BuildingID", idref=hpxml_object.get_first_building_id()
    )
    objectify.SubElement(consumption_section, "CustomerID")
    consumption_details = objectify.SubElement(consumption_section, "ConsumptionDetails")

    # separate bill data by fuel type, then remove fuel type info
    dfs_by_fuel = {}
    for f_type in bills["FuelType"].unique():
        fuel_data = bills.loc[bills["FuelType"] == f_type]
        dfs_by_fuel[f_type] = fuel_data.drop(["UnitofMeasure", "FuelType"], axis=1)

    # Turn the dfs of bills into xml objects that match hpxml schema
    for fuel, consumption_df in dfs_by_fuel.items():
        logger.debug(f"{fuel=}")
        xml_str = consumption_df.to_xml(
            root_name="ConsumptionInfo",
            row_name="ConsumptionDetail",
            index=False,
            xml_declaration=False,
        )
        new_obj = objectify.fromstring(xml_str)
        consumption_type = objectify.SubElement(new_obj, "ConsumptionType")
        energy = objectify.SubElement(consumption_type, "Energy")
        fuel_type = objectify.SubElement(energy, "FuelType")
        fuel_type._setText(fuel)
        unit_of_measure = objectify.SubElement(energy, "UnitofMeasure")
        match fuel:
            case "electricity":
                unit = "kWh"
            case "fuel oil":
                unit = "gal"
            case "natural gas":
                unit = "therms"
            case _:
                logger.error(f"unknown fuel type: {fuel}!")
        unit_of_measure._setText(unit)

        consumption_details.append(new_obj)

    hpxml_object.root.append(consumption_section)
    return hpxml_object
