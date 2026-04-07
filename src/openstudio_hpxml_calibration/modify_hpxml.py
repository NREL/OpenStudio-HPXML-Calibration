from pathlib import Path

import pandas as pd
from lxml import objectify
from lxml.objectify import ElementMaker

from openstudio_hpxml_calibration.hpxml import HpxmlDoc


def set_consumption_on_hpxml(hpxml_object: HpxmlDoc, csv_bills_filepath: Path) -> HpxmlDoc:
    # Define HPXML namespace
    NS = hpxml_object.ns["h"]
    NSMAP = {None: NS}

    # Define the element maker with namespace
    E = ElementMaker(namespace=NS, nsmap=NSMAP)

    bills = pd.read_csv(csv_bills_filepath)

    # Datetime handling
    bills["StartDateTime"] = pd.to_datetime(bills["StartDateTime"], format="mixed")
    bills["EndDateTime"] = pd.to_datetime(bills["EndDateTime"], format="mixed") + pd.Timedelta(
        days=1
    )
    bills["StartDateTime"] = bills["StartDateTime"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    bills["EndDateTime"] = bills["EndDateTime"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Set up xml objects to hold the bill data
    consumption_details = E.ConsumptionDetails()
    consumption_section = E.Consumption(
        E.BuildingID(idref=hpxml_object.get_first_building_id()),
        E.CustomerID(),
        consumption_details,
    )

    # Separate bill data by fuel type, then remove fuel type info
    for fuel in bills["FuelType"].unique():
        consumption_df = bills.loc[bills["FuelType"] == fuel].drop(["FuelType"], axis=1)

        unit = consumption_df["UnitofMeasure"].iloc[0]
        narrower_df = consumption_df.drop(["UnitofMeasure"], axis=1)

        if unit is None:
            raise ValueError(f"Unsupported fuel type: {fuel}")

        xml_str = narrower_df.to_xml(
            root_name="ConsumptionInfo",
            row_name="ConsumptionDetail",
            index=False,
            xml_declaration=False,
            namespaces=NSMAP,
        )

        new_obj = objectify.fromstring(xml_str.encode())

        consumption_type = E.ConsumptionType(
            E.Energy(
                E.FuelType(fuel),
                E.UnitofMeasure(unit),
            )
        )

        new_obj.insert(0, consumption_type)
        new_obj.insert(0, E.UtilityID())
        consumption_details.append(new_obj)

    hpxml_object.root.append(consumption_section)

    return hpxml_object
