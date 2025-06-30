import marimo

__generated_with = "0.14.6"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    import pandas as pd
    from lxml import etree, objectify

    from openstudio_hpxml_calibration.calibrate import Calibrate
    from openstudio_hpxml_calibration.hpxml import HpxmlDoc

    return Calibrate, HpxmlDoc, Path, etree, objectify, pd


@app.cell
def _(Calibrate, base_house, consumption_data):
    cal = Calibrate(original_hpxml_filepath=base_house, csv_bills_filepath=consumption_data)
    # cal = Calibrate(original_hpxml_filepath=house21)
    return (cal,)


@app.cell
def _(cal):
    # dir(cal.hpxml)
    cal.hpxml.get_first_building_id()


@app.cell
def _(Path):
    Path(__file__).parent / "test_hpxmls/" / "real_homes" / "house21.xml"
    base_house = Path(__file__).parent / "src/OpenStudio-HPXML/workflow/sample_files/base.xml"
    consumption_data = Path(__file__).parent / "tests" / "data" / "test_bills.csv"
    return base_house, consumption_data


@app.cell
def _(HpxmlDoc, base_house, consumption_data, pd):
    hpxml = HpxmlDoc(base_house)
    bills = pd.read_csv(consumption_data)
    return bills, hpxml


@app.cell
def _(hpxml, objectify):
    consumption_section = objectify.E.Consumption(
        objectify.E.BuildingID(idref=hpxml.get_first_building_id()),
        objectify.E.CustomerID(),
        objectify.E.ConsumptionDetails,
    )
    # objectify.deannotate(consumption_section, cleanup_namespaces=True)
    return (consumption_section,)


@app.cell
def _(bills):
    # separate by fuel type, and remove fuel type info
    dfs_by_fuel = {}
    for f_type in bills["FuelType"].unique():
        fuel_data = bills.loc[bills["FuelType"] == f_type]
        dfs_by_fuel[f_type] = fuel_data.drop(["UnitofMeasure", "FuelType"], axis=1)
    return (dfs_by_fuel,)


@app.cell
def _(dfs_by_fuel):
    dfs_by_fuel["electricity"]


@app.cell
def _(consumption_section, dfs_by_fuel, objectify):
    for fuel, consumption_df in dfs_by_fuel.items():
        print(fuel)
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
                print("unknown fuel type!")
        unit_of_measure._setText(unit)

        consumption_section.ConsumptionDetails.append(new_obj)
        objectify.deannotate(consumption_section, cleanup_namespaces=True)


@app.cell
def _(dfs_by_fuel):
    xml_test_str = dfs_by_fuel["fuel oil"].to_xml(
        root_name="ConsumptionInfo",
        row_name="ConsumptionDetail",
        index=False,
        xml_declaration=False,
    )
    return (xml_test_str,)


@app.cell
def _():
    # print(etree.tostring(consumption_section, pretty_print=True).decode())
    return


@app.cell
def _(objectify, xml_test_str):
    objectify.fromstring(xml_test_str)


@app.cell
def _():
    # consumption_type = objectify.SubElement(test_obj, "ConsumptionType")
    # energy = objectify.SubElement(consumption_type, "Energy")
    # fuel_type = objectify.SubElement(energy, "FuelType")
    # fuel_type._setText("cowabunga")
    # unit_of_measure = objectify.SubElement(energy, "UnitofMeasure")
    # unit_of_measure._setText("pizzas")
    return


@app.cell
def _():
    # consumption_section.ConsumptionDetails.append(new_obj)
    # objectify.deannotate(consumption_section, cleanup_namespaces=True)
    return


@app.cell
def _():
    # print(etree.tostring(test_obj, pretty_print=True).decode())
    return


@app.cell
def _(consumption_section, etree, hpxml):
    hpxml.root.append(consumption_section)
    # hpxml.ConsumptionDetails.append(new_obj)
    # Remove xml meta tags, leaving only the xml objects
    # objectify.deannotate(hpxml.root, cleanup_namespaces=True)
    print(etree.tostring(hpxml.root, pretty_print=True).decode())


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
