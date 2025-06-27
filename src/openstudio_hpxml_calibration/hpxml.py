import functools
import os
import re
from enum import Enum
from pathlib import Path

import pandas as pd
from lxml import etree, isoschematron, objectify
from pvlib.iotools import read_epw

from openstudio_hpxml_calibration import OS_HPXML_PATH


class FuelType(Enum):
    ELECTRICITY = "electricity"
    RENEWABLE_ELECTRICITY = "renewable electricity"
    NATURAL_GAS = "natural gas"
    RENEWABLE_NATURAL_GAS = "renewable natural gas"
    FUEL_OIL = "fuel oil"
    FUEL_OIL_1 = "fuel oil 1"
    FUEL_OIL_2 = "fuel oil 2"
    FUEL_OIL_4 = "fuel oil 4"
    FUEL_OIL_5_6 = "fuel oil 5/6"
    DISTRICT_STEAM = "district steam"
    DISTRICT_HOT_WATER = "district hot water"
    DISTRICT_CHILLED_WATER = "district chilled water"
    SOLAR_HOT_WATER = "solar hot water"
    PROPANE = "propane"
    KEROSENE = "kerosene"
    DIESEL = "diesel"
    COAL = "coal"
    ANTHRACITE_COAL = "anthracite coal"
    BITUMINOUS_COAL = "bituminous coal"
    COKE = "coke"
    WOOD = "wood"
    WOOD_PELLETS = "wood pellets"
    COMBINATION = "combination"
    OTHER = "other"


class EnergyUnitType(Enum):
    CMH = "cmh"
    CCF = "ccf"
    KCF = "kcf"
    MCF = "Mcf"
    CFH = "cfh"
    KWH = "kWh"
    MWH = "MWh"
    BTU = "Btu"
    KBTU = "kBtu"
    MBTU = "MBtu"
    THERMS = "therms"
    LBS = "lbs"
    KLBS = "kLbs"
    MLBS = "MLbs"
    TONNES = "tonnes"
    CORDS = "cords"
    GAL = "gal"
    KGAL = "kgal"
    TON_HOURS = "ton hours"


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
        self.ns = {"h": self.root.nsmap.get("h", self.root.nsmap.get(None))}

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

    def get_consumption(self, building_id: str | None = None) -> objectify.ObjectifiedElement:
        """Get the Consumption element for a building

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str | None, optional
        :return: Consumption element
        :rtype: objectify.ObjectifiedElement
        """
        if building_id is None:
            return self.xpath("h:Consumption[1]")[0]
        return self.xpath(
            "h:Consumption[h:BuildingID/@idref=$building_id]", building_id=building_id
        )[0]

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
            zipcode = str(building.Site.Address.ZipCode)
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

    def get_lat_lon(self, building_id: str | None = None) -> tuple[float, float]:
        """Get latitude, longitude from hpxml file

        :param hpxml: _description_
        :type hpxml: HpxmlDoc
        :param building_id: Optional building_id of the building you want to get location for.
        :type building_id: str | None
        :return: _description_
        :rtype: tuple[float, float]
        """
        building = self.get_building(building_id)
        try:
            # Option 1: Get directly from HPXML
            geolocation = building.Site.GeoLocation
            lat = float(geolocation.Latitude)
            lon = float(geolocation.Longitude)
        except AttributeError:
            _, epw_metadata = self.get_epw_data(building_id)
            lat = epw_metadata["latitude"]
            lon = epw_metadata["longitude"]

        return lat, lon
