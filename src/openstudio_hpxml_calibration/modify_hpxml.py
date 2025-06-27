from pathlib import Path

import pandas as pd
from loguru import logger
from lxml import etree, objectify
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
    # Convert to datetimes, and include the final day of the bill period
    bills["StartDateTime"] = pd.to_datetime(bills["StartDateTime"])
    bills["EndDateTime"] = pd.to_datetime(bills["EndDateTime"]) + pd.Timedelta(days=1)
    bills["StartDateTime"] = bills["StartDateTime"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    bills["EndDateTime"] = bills["EndDateTime"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Set up xml objects to hold the bill data
    consumption_details = E.ConsumptionDetails()
    consumption_section = E.Consumption(
        E.BuildingID(idref=hpxml_object.get_first_building_id()),
        E.CustomerID(),
        consumption_details,
    )

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
            namespaces=NSMAP,
        )
        new_obj = objectify.fromstring(xml_str)

        unit = {"electricity": "kWh", "fuel oil": "gal", "natural gas": "therms"}.get(fuel)

        if unit is None:
            logger.error(f"Unsupported fuel type: {fuel}")

        consumption_type = E.ConsumptionType(E.Energy(E.FuelType(fuel), E.UnitofMeasure(unit)))
        new_obj.insert(0, consumption_type)
        new_obj.insert(0, E.UtilityID())
        consumption_details.append(new_obj)

    hpxml_object.root.append(consumption_section)
    et = etree.ElementTree(hpxml_object.root)
    et.write("model_with_consumption.xml", pretty_print=True)

    return hpxml_object
