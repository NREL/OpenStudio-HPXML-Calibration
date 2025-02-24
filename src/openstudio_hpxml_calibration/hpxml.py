import functools
import os
import re
from pathlib import Path

import pandas as pd
from lxml import etree, isoschematron, objectify
from pvlib.iotools import read_epw

from openstudio_hpxml_calibration import OS_HPXML_PATH


class HpxmlDoc:
    def __init__(
        self, filename: os.PathLike, validate_schema: bool = True, validate_schematron: bool = True
    ):
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
        if el is None:
            el = self.root
        ns = re.match(r"\{(.+)\}", el.tag).group(1)
        return el.xpath(xpath_expr, namespaces={"h": ns}, **kw)

    def get_first_building_id(self) -> str:
        return self.xpath("h:Building[1]/h:BuildingID/@id", smart_strings=False)[0]

    def get_building(self, building_id: str | None = None) -> objectify.ObjectifiedElement:
        if building_id is None:
            return self.xpath("h:Building[1]")[0]
        else:
            return self.xpath("h:Building[h:BuildingID/@id=$building_id]", building_id=building_id)[
                0
            ]

    @functools.cache
    def get_epw_path(self, building_id: str | None = None) -> Path:
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
        return read_epw(self.get_epw_path(building_id), **kw)
