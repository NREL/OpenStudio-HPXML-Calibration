import functools
import os
import re
from contextlib import suppress
from pathlib import Path

import pandas as pd
from lxml import etree, isoschematron, objectify
from pvlib.iotools import read_epw

from openstudio_hpxml_calibration import OS_HPXML_PATH


class HpxmlDoc:
    """
    A class representing an HPXML document.

    Attributes can be accessed using the lxml.objectify syntax. i.e.
    hpxml = HpxmlDoc("filename.xml")
    hpxml.Building.Site.Address

    There are a number of helper functions to get other important information.
    """

    def __init__(
        self, filename: os.PathLike, validate_schema: bool = True, validate_schematron: bool = True
    ):
        """Create an HpxmlDoc object

        :param filename: Path to file to parse
        :type filename: os.PathLike
        :param validate_schema: Validate against the HPXML schema, defaults to True
        :type validate_schema: bool, optional
        :param validate_schematron: Validate against EPvalidator.xml schematron, defaults to True
        :type validate_schematron: bool, optional
        """
        self.file_path = Path(filename).resolve()
        self.tree = objectify.parse(str(filename))
        self.root = self.tree.getroot()

        if validate_schema:
            hpxml_schema_filename = (
                OS_HPXML_PATH / "HPXMLtoOpenStudio" / "resources" / "hpxml_schema" / "HPXML.xsd"
            )
            schema_doc = etree.parse(str(hpxml_schema_filename))
            schema = etree.XMLSchema(schema_doc)
            schema.assertValid(self.tree)

        if validate_schematron:
            hpxml_schematron_filename = (
                OS_HPXML_PATH
                / "HPXMLtoOpenStudio"
                / "resources"
                / "hpxml_schematron"
                / "EPvalidator.xml"
            )
            schematron_doc = etree.parse(str(hpxml_schematron_filename))
            schematron = isoschematron.Schematron(schematron_doc)
            schematron.assertValid(self.tree)

    def __getattr__(self, name: str):
        return getattr(self.root, name)

    def xpath(
        self, xpath_expr: str, el: objectify.ObjectifiedElement | None = None, **kw
    ) -> list[objectify.ObjectifiedElement]:
        """Run an xpath query on the file

        The h: namespace is the default HPXML namespace. No namespaces need to
        be passed into the function.

        ``hpxml.xpath("//h:Wall")``

        :param xpath_expr: Xpath expression to evaluate
        :type xpath_expr: str
        :param el: Optional element from which to evaluate the xpath, if omitted
            will use the root HPXML element.
        :type el: objectify.ObjectifiedElement | None, optional
        :return: A list of elements that match the xpath expression.
        :rtype: list[objectify.ObjectifiedElement]
        """
        if el is None:
            el = self.root
        ns = re.match(r"\{(.+)\}", el.tag).group(1)
        return el.xpath(xpath_expr, namespaces={"h": ns}, **kw)

    def get_first_building_id(self) -> str:
        """Get the id of the first Building element in the file."""
        return self.xpath("h:Building[1]/h:BuildingID/@id", smart_strings=False)[0]

    def get_building(self, building_id: str | None = None) -> objectify.ObjectifiedElement:
        """Get a building element

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str | None, optional
        :return: Building element
        :rtype: objectify.ObjectifiedElement
        """
        if building_id is None:
            return self.xpath("h:Building[1]")[0]
        else:
            return self.xpath("h:Building[h:BuildingID/@id=$building_id]", building_id=building_id)[
                0
            ]

    def get_fuel_types(self, building_id: str | None = None) -> tuple[list[str], list[str]]:
        """Get fuel types providing heating or cooling

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str
        :return: lists of fuel types provide heating and cooling
        :rtype: tuple[list[str], list[str]]
        """
        fuel_provides_heating = set()
        fuel_provides_cooling = set()

        building = self.get_building(building_id)
        heating_fuels = []
        heatpump_fuels = []
        cooling_fuels = []
        with suppress(AttributeError):
            heating_fuels.append(
                building.BuildingDetails.Systems.HVAC.HVACPlant.HeatingSystem.HeatingSystemFuel.text
            )  # TODO: Can it handle a case where there are multiple heating systems?
            heatpump_fuels.append(
                building.BuildingDetails.Systems.HVAC.HVACPlant.HeatPump.HeatPumpFuel.text
            )
            heatpump_fuels.append(
                building.BuildingDetails.Systems.HVAC.HVACPlant.HeatPump.BackupSystemFuel.text
            )  # TODO: Need to capture fuel used for integrated AC?
            cooling_fuels.append(
                building.BuildingDetails.Systems.HVAC.HVACPlant.CoolingSystem.CoolingSystemFuel.text
            )

        for heating_fuel in heating_fuels:
            fuel_provides_heating.add(heating_fuel.strip())
        for heatpump_fuel in heatpump_fuels:
            fuel_provides_heating.add(heatpump_fuel.strip())
        for cooling_fuel in cooling_fuels:
            fuel_provides_cooling.add(cooling_fuel.strip())

        return list(fuel_provides_heating), list(fuel_provides_cooling)

    @functools.cache
    def get_epw_path(self, building_id: str | None = None) -> Path:
        """Get the filesystem path to the EPW file.

        Uses the same logic as OpenStudio-HPXML

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str | None, optional
        :raises FileNotFoundError: Raises this error if the epw file doesn't exist
        :return: path to epw file
        :rtype: Path
        """
        building = self.get_building(building_id)
        try:
            epw_file = str(
                building.BuildingDetails.ClimateandRiskZones.WeatherStation.extension.EPWFilePath
            )
        except AttributeError:
            zipcode = str(building.Site.Address.ZipCode).zfill(5)
            zipcode_lookup_filename = (
                OS_HPXML_PATH / "HPXMLtoOpenStudio/resources/data/zipcode_weather_stations.csv"
            )
            zipcodes = pd.read_csv(
                zipcode_lookup_filename,
                usecols=["zipcode", "station_filename"],
                index_col="zipcode",
                dtype={"zipcode": str},
            )
            epw_file = zipcodes.loc[zipcode, "station_filename"]

        epw_path = Path(epw_file)
        if not epw_path.is_absolute():
            possible_parent_paths = [self.file_path.parent, OS_HPXML_PATH / "weather"]
            for parent_path in possible_parent_paths:
                epw_path = parent_path / Path(epw_file)
                if epw_path.exists():
                    break
        if not epw_path.exists():
            raise FileNotFoundError(str(epw_path))

        return epw_path

    @functools.cache
    def get_epw_data(self, building_id: str | None = None, **kw) -> tuple[pd.DataFrame, dict]:
        """Get the epw data as a dataframe

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str | None, optional
        :return: Dataframe of epw and a dict of epw metadata
        :rtype: tuple[pd.DataFrame, dict]
        """
        return read_epw(self.get_epw_path(building_id), **kw)
