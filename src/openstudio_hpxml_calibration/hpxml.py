import os
import pathlib
import re

from lxml import etree, isoschematron, objectify


class HpxmlDoc:
    def __init__(
        self, filename: os.PathLike, validate_schema: bool = True, validate_schematron: bool = True
    ):
        self.file_path = pathlib.Path(filename).resolve()
        self.tree = objectify.parse(str(filename))
        self.root = self.tree.getroot()

        if validate_schema:
            hpxml_schema_filename = (
                pathlib.Path(__file__).resolve().parent.parent
                / "OpenStudio-HPXML"
                / "HPXMLtoOpenStudio"
                / "resources"
                / "hpxml_schema"
                / "HPXML.xsd"
            )
            schema_doc = etree.parse(str(hpxml_schema_filename))
            schema = etree.XMLSchema(schema_doc)
            schema.assertValid(self.tree)

        if validate_schematron:
            hpxml_schematron_filename = (
                pathlib.Path(__file__).resolve().parent.parent
                / "OpenStudio-HPXML"
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
