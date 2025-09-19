import functools
import os
import re
from datetime import datetime as dt
from datetime import timedelta
from enum import Enum
from pathlib import Path

import pandas as pd
from loguru import logger
from lxml import etree, isoschematron, objectify
from pvlib.iotools import read_epw

from openstudio_hpxml_calibration.utils import OS_HPXML_PATH


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
        :param validate_schematron: Validate against EPvalidator schematron, defaults to True
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
                / "EPvalidator.sch"
            )
            schematron_doc = etree.parse(str(hpxml_schematron_filename))
            schematron = isoschematron.Schematron(schematron_doc)
            schematron.assertValid(self.tree)

    def __getattr__(self, name: str):
        # This prevents infinite recursion in contexts involving logging or multiprocessing
        if name == "root":
            raise AttributeError("Avoid recursive getattr call on root")
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

    def get_fuel_types(self, building_id: str | None = None) -> tuple[str, set[str]]:
        """Get fuel types providing heating, cooling, water heating, clothes drying, and cooking

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str
        :return: fuel types for heating, cooling, water heaters, clothes dryers, and cooking
        :rtype: tuple[str, set[str]]
        """

        building = self.get_building(building_id)
        fuel_types = {
            "heating": set(),
            "cooling": set(),
            "water heater": set(),
            "clothes dryer": set(),
            "cooking": set(),
        }
        if (
            hasattr(building.BuildingDetails, "Systems")
            and hasattr(building.BuildingDetails.Systems, "HVAC")
            and hasattr(building.BuildingDetails.Systems.HVAC, "HVACPlant")
        ):
            for hvac_system in building.BuildingDetails.Systems.HVAC.HVACPlant:
                if hasattr(hvac_system, "HeatingSystem") and hasattr(
                    hvac_system.HeatingSystem, "HeatingSystemFuel"
                ):
                    fuel_types["heating"].add(
                        hvac_system.HeatingSystem.HeatingSystemFuel.text.strip()
                    )

                if hasattr(hvac_system, "CoolingSystem"):
                    if hasattr(hvac_system.CoolingSystem, "CoolingSystemFuel"):
                        fuel_types["cooling"].add(
                            hvac_system.CoolingSystem.CoolingSystemFuel.text.strip()
                        )
                    if hasattr(hvac_system.CoolingSystem, "IntegratedHeatingSystemFuel"):
                        fuel_types["heating"].add(
                            hvac_system.CoolingSystem.IntegratedHeatingSystemFuel.text.strip()
                        )

                if hasattr(hvac_system, "HeatPump"):
                    if hasattr(hvac_system.HeatPump, "HeatPumpFuel"):
                        fuel_types["heating"].add(hvac_system.HeatPump.HeatPumpFuel.text.strip())
                        fuel_types["cooling"].add(hvac_system.HeatPump.HeatPumpFuel.text.strip())
                    if hasattr(hvac_system.HeatPump, "BackupSystemFuel"):
                        fuel_types["heating"].add(
                            hvac_system.HeatPump.BackupSystemFuel.text.strip()
                        )

        if (
            hasattr(building.BuildingDetails, "Systems")
            and hasattr(building.BuildingDetails.Systems, "WaterHeating")
            and hasattr(building.BuildingDetails.Systems.WaterHeating, "WaterHeatingSystem")
        ):
            for water_heater in building.BuildingDetails.Systems.WaterHeating.WaterHeatingSystem:
                if hasattr(water_heater, "FuelType"):
                    fuel_types["water heater"].add(water_heater.FuelType.text.strip())
                elif hasattr(water_heater, "RelatedHVACSystem"):
                    # No need to retrieve, we already have the fuel type for the heating system
                    pass

        if hasattr(building.BuildingDetails, "Appliances") and hasattr(
            building.BuildingDetails.Appliances, "ClothesDryer"
        ):
            for clothes_dryer in building.BuildingDetails.Appliances.ClothesDryer:
                if hasattr(clothes_dryer, "FuelType"):
                    fuel_types["clothes dryer"].add(clothes_dryer.FuelType.text.strip())

        if hasattr(building.BuildingDetails, "Appliances") and hasattr(
            building.BuildingDetails.Appliances, "CookingRange"
        ):
            for cooking_range in building.BuildingDetails.Appliances.CookingRange:
                if hasattr(cooking_range, "FuelType"):
                    fuel_types["cooking"].add(cooking_range.FuelType.text.strip())

        return fuel_types

    def get_consumptions(
        self, building_id: str | None = None
    ) -> tuple[objectify.ObjectifiedElement, ...]:
        """Get all Consumption elements for a building

        :param building_id: The id of the Building to retrieve, gets first one if missing
        :type building_id: str | None, optional
        :return: Tuple of Consumption elements
        :rtype: tuple
        """
        if building_id is None:
            return tuple(self.xpath("h:Consumption"))
        return tuple(
            self.xpath("h:Consumption[h:BuildingID/@idref=$building_id]", building_id=building_id)
        )

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

    def get_lat_lon(self, building_id: str | None = None) -> tuple[float, float]:
        """Get latitude, longitude from hpxml file

        :param building_id: Optional building_id of the building you want to get location for.
        :type building_id: str | None
        :return: Latitude and longitude
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

    def hpxml_data_error_checking(self, config: dict) -> None:
        """Check for common HPXML errors

        :param config: Configuration dictionary, combination of default and user config
        :type config: dict

        :raises ValueError: If an error is found
        """
        now = dt.now()
        building = self.get_building()
        consumptions = self.get_consumptions()

        # Check that the building doesn't have PV
        try:
            building.BuildingDetails.Systems.Photovoltaics
            raise ValueError("PV is not supported with automated calibration at this time.")
        except AttributeError:
            pass

        # Helper: flatten all fuel entries across all consumption elements
        all_fuels = [
            (consumption_elem, fuel)
            for consumption_elem in consumptions
            for fuel in consumption_elem.ConsumptionDetails.ConsumptionInfo
        ]

        # Check that every fuel in every consumption element has a ConsumptionType.Energy element
        if not all(
            all(
                hasattr(fuel.ConsumptionType, "Energy")
                for fuel in consumption_elem.ConsumptionDetails.ConsumptionInfo
            )
            for consumption_elem in consumptions
        ):
            raise ValueError(
                "Every fuel in every Consumption section must have a valid ConsumptionType.Energy element."
            )

        # Check that at least one consumption element matches the building ID
        if not any(
            consumption_elem.BuildingID.attrib["idref"] == building.BuildingID.attrib["id"]
            for consumption_elem in consumptions
        ):
            raise ValueError("No Consumption section matches the Building ID in the HPXML file.")

        # Check that at least one fuel per fuel type has valid units
        def valid_unit(fuel):
            fuel_type = fuel.ConsumptionType.Energy.FuelType
            unit = fuel.ConsumptionType.Energy.UnitofMeasure
            match fuel_type:
                case FuelType.ELECTRICITY.value:
                    return unit in ("kWh", "MWh")
                case FuelType.NATURAL_GAS.value:
                    return unit in ("therms", "Btu", "kBtu", "MBtu", "ccf", "kcf", "Mcf")
                case FuelType.FUEL_OIL.value | FuelType.PROPANE.value:
                    return unit in ("gal", "Btu", "kBtu", "MBtu", "therms")
                case _:
                    return False

        for fuel_type in {
            getattr(fuel.ConsumptionType.Energy, "FuelType", None)
            for _, fuel in all_fuels
            if hasattr(fuel.ConsumptionType, "Energy")
        }:
            if fuel_type is None:
                continue
            if not any(
                getattr(fuel.ConsumptionType.Energy, "FuelType", None) == fuel_type
                and valid_unit(fuel)
                for _, fuel in all_fuels
            ):
                raise ValueError(
                    f"No valid unit found for fuel type '{fuel_type}' in any Consumption section."
                )

        # Check that for each fuel type, there is only one Consumption section
        fuel_type_to_consumption = {}
        for consumption_elem in consumptions:
            for fuel in consumption_elem.ConsumptionDetails.ConsumptionInfo:
                fuel_type = getattr(fuel.ConsumptionType.Energy, "FuelType", None)
                if fuel_type is None:
                    continue
                if fuel_type in fuel_type_to_consumption:
                    raise ValueError(
                        f"Multiple Consumption sections found for fuel type '{fuel_type}'. "
                        "Only one section per fuel type is allowed."
                    )
                fuel_type_to_consumption[fuel_type] = consumption_elem

        # Check that electricity consumption is present in at least one section
        if not any(
            getattr(fuel.ConsumptionType.Energy, "FuelType", None) == FuelType.ELECTRICITY.value
            for _, fuel in all_fuels
        ):
            raise ValueError(
                "Electricity consumption is required for calibration. "
                "Please provide electricity consumption data in the HPXML file."
            )

        # Check that for each fuel, all periods are consecutive, non-overlapping, and valid
        for _, fuel in all_fuels:
            details = getattr(fuel, "ConsumptionDetail", [])
            for i, detail in enumerate(details):
                try:
                    start_date = dt.strptime(str(detail.StartDateTime), "%Y-%m-%dT%H:%M:%S")
                except AttributeError:
                    raise ValueError(
                        f"Consumption detail {i} for {fuel.ConsumptionType.Energy.FuelType} is missing StartDateTime."
                    )
                try:
                    end_date = dt.strptime(str(detail.EndDateTime), "%Y-%m-%dT%H:%M:%S")
                except AttributeError:
                    raise ValueError(
                        f"Consumption detail {i} for {fuel.ConsumptionType.Energy.FuelType} is missing EndDateTime."
                    )
                if i > 0:
                    prev_detail = details[i - 1]
                    prev_end = dt.strptime(str(prev_detail.EndDateTime), "%Y-%m-%dT%H:%M:%S")
                    curr_start = dt.strptime(str(detail.StartDateTime), "%Y-%m-%dT%H:%M:%S")
                    if curr_start < prev_end:
                        raise ValueError(
                            f"Consumption details for {fuel.ConsumptionType.Energy.FuelType} overlap: "
                            f"{prev_detail.StartDateTime} - {prev_detail.EndDateTime} overlaps with "
                            f"{detail.StartDateTime} - {detail.EndDateTime}"
                        )
                    if (curr_start - prev_end) > timedelta(minutes=1):
                        raise ValueError(
                            f"Gap in consumption data for {fuel.ConsumptionType.Energy.FuelType}: "
                            f"Period between {prev_detail.EndDateTime} and {detail.StartDateTime} is not covered.\n"
                            "Are the bill periods consecutive?"
                        )

        # Check that all consumption values are above zero
        if not any(
            all(detail.Consumption > 0 for detail in getattr(fuel, "ConsumptionDetail", []))
            for _, fuel in all_fuels
        ):
            raise ValueError(
                "All Consumption values must be greater than zero for at least one fuel type."
            )

        # Check that no consumption is estimated (for now, fail if any are)
        for _, fuel in all_fuels:
            for detail in getattr(fuel, "ConsumptionDetail", []):
                reading_type = getattr(detail, "ReadingType", None)
                if reading_type and str(reading_type).lower() == "estimate":
                    raise ValueError(
                        f"Estimated consumption value for {fuel.ConsumptionType.Energy.FuelType} cannot be greater than zero for bill-period: {detail.StartDateTime}"
                    )

        # Check that each fuel type covers enough days and dates are valid
        min_days = config["utility_bill_criteria"]["min_days_of_consumption_data"]
        recent_bill_max_age_days = config["utility_bill_criteria"]["max_days_since_newest_bill"]

        def _parse_dt(val):
            return dt.strptime(str(val), "%Y-%m-%dT%H:%M:%S")

        def _fuel_period_ok(fuel):
            details = getattr(fuel, "ConsumptionDetail", [])
            if details is None or len(details) == 0:
                return False

            first_start = _parse_dt(details[0].StartDateTime)
            last_end = _parse_dt(details[-1].EndDateTime)

            # Total covered span must meet min_days
            if (last_end - first_start).days < min_days:
                logger.debug(
                    f"Found {(last_end - first_start).days} days of consumption data between {first_start} and {last_end}"
                )
                return False

            # Most recent bill must be within allowed age
            if (now - last_end).days > recent_bill_max_age_days:
                logger.debug(
                    f"Found {(now - last_end).days} days since most recent bill, {last_end}"
                )
                return False

            # No future dates
            for bill_info in details:
                if (
                    _parse_dt(bill_info.StartDateTime) > now
                    or _parse_dt(bill_info.EndDateTime) > now
                ):
                    logger.debug(
                        f"Found future date in bill info: {bill_info.StartDateTime} - {bill_info.EndDateTime}"
                    )
                    return False
            return True

        # Build mapping of fuel type -> list of fuel entries
        fuels_by_type: dict[str, list] = {}
        for _, fuel in all_fuels:
            if hasattr(fuel.ConsumptionType, "Energy"):
                ftype = getattr(fuel.ConsumptionType.Energy, "FuelType", None)
                if ftype is not None:
                    fuels_by_type.setdefault(ftype, []).append(fuel)

        for fuel_type, consumption_info in fuels_by_type.items():
            # Require at least one consumption section for this fuel type to satisfy criteria
            if not any(_fuel_period_ok(fuel) for fuel in consumption_info):
                raise ValueError(
                    f"Consumption dates for {fuel_type} must cover at least {min_days} days and the most recent bill must end within the past {recent_bill_max_age_days} days."
                )

        # Check that electricity bill periods are within configured min/max days
        longest_bill_period = config["utility_bill_criteria"]["max_electrical_bill_days"]
        shortest_bill_period = config["utility_bill_criteria"]["min_electrical_bill_days"]
        for _, fuel in all_fuels:
            if getattr(fuel.ConsumptionType.Energy, "FuelType", None) == FuelType.ELECTRICITY.value:
                for detail in getattr(fuel, "ConsumptionDetail", []):
                    start_date = dt.strptime(str(detail.StartDateTime), "%Y-%m-%dT%H:%M:%S")
                    end_date = dt.strptime(str(detail.EndDateTime), "%Y-%m-%dT%H:%M:%S")
                    period_days = (end_date - start_date).days
                    if period_days > longest_bill_period:
                        raise ValueError(
                            f"Electricity consumption bill period {start_date} - {end_date} cannot be longer than {longest_bill_period} days."
                        )
                    if period_days < shortest_bill_period:
                        raise ValueError(
                            f"Electricity consumption bill period {start_date} - {end_date} cannot be shorter than {shortest_bill_period} days."
                        )

        # Check that consumed fuel matches equipment fuel type (at least one section must match)
        def fuel_type_in_any(fuel_type):
            return any(
                getattr(fuel.ConsumptionType.Energy, "FuelType", None) == fuel_type
                for _, fuel in all_fuels
            )

        fuel_types = self.get_fuel_types()

        for component, fuels in fuel_types.items():
            for fuel in fuels:
                if not fuel_type_in_any(fuel):
                    raise ValueError(
                        f"HPXML consumption data missing for {component} fuel type ({fuel})."
                    )
