import datetime as dt
import os
import re

import eeweather
import pandas as pd
from lxml import etree, objectify


def parse_hpxml(filename: os.PathLike) -> etree._ElementTree:
    return objectify.parse(str(filename))


def get_datetime_subel(el: objectify.ObjectifiedElement, subel_name: str) -> pd.Timestamp | None:
    subel = getattr(el, subel_name, None)
    if subel is None:
        return subel
    else:
        return pd.to_datetime(str(subel))


def xpath(
    el: objectify.ObjectifiedElement, xpath_expr: str, **kw
) -> list[objectify.ObjectifiedElement]:
    ns = re.match(r"\{(.+)\}", el.tag).group(1)
    return el.xpath(xpath_expr, namespaces={"h": ns}, **kw)


def get_first_building_id(hpxml_root: objectify.ObjectifiedElement) -> str:
    return xpath(hpxml_root, "h:Building[1]/h:BuildingID/@id", smart_strings=False)[0]


def get_bills_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement, building_id: str | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]:
    """Get utility bills from an HPXML file.

    :param hpxml_root: The root element of the HPXML file
    :type hpxml_root: objectify.ObjectifiedElement
    :param building_id: Optional building_id of the building you want to get bills for.
    :type building_id: str | None
    :return:
        * `bills_by_fuel_type`, a dictionary with fuel types as the keys and a
          dataframe as the values with columns `start_date`, `end_date`, and `consumption`
        * `bill_units`, a dictionary with a map of fuel type to units in the HPXML file.
        * `local_standard_tz`, the timezone (standard, no DST) of the location.
    :rtype: tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]
    """
    if building_id is None:
        building_id = get_first_building_id(hpxml_root)
    local_standard_tz = dt.timezone(
        dt.timedelta(hours=int(hpxml_root.Building.Site.TimeZone.UTCOffset))
    )

    bills_by_fuel_type = {}
    bill_units = {}
    for cons_info in xpath(
        hpxml_root,
        "h:Consumption[h:BuildingID/@idref=$building_id]/h:ConsumptionDetails/h:ConsumptionInfo",
        building_id=building_id,
    ):
        fuel_type = str(cons_info.ConsumptionType.Energy.FuelType)
        bill_units[fuel_type] = str(cons_info.ConsumptionType.Energy.UnitofMeasure)
        rows = []
        for el in cons_info.ConsumptionDetail:
            rows.append(
                [
                    get_datetime_subel(el, "StartDateTime"),
                    get_datetime_subel(el, "EndDateTime"),
                    float(el.Consumption),
                ]
            )
        bills = pd.DataFrame.from_records(rows, columns=["start_date", "end_date", "consumption"])
        if pd.isna(bills["end_date"]).all():
            bills["end_date"] = bills["start_date"].shift(-1)
        if pd.isna(bills["start_date"]).all():
            bills["start_date"] = bills["end_date"].shift(1)
        bills["start_date"] = bills["start_date"].dt.tz_localize(local_standard_tz)
        bills["end_date"] = bills["end_date"].dt.tz_localize(local_standard_tz)
        bills_by_fuel_type[fuel_type] = bills

    return bills_by_fuel_type, bill_units, local_standard_tz


def get_lat_lon_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement, building_id: str | None = None
) -> tuple[float, float]:
    """Get latitude, longitude from hpxml file

    :param hpxml_root: _description_
    :type hpxml_root: objectify.ObjectifiedElement
    :param building_id: Optional building_id of the building you want to get location for.
    :type building_id: str | None
    :return: _description_
    :rtype: tuple[float, float]
    """
    if building_id is None:
        building_id = get_first_building_id(hpxml_root)
    geolocation = xpath(
        hpxml_root,
        "h:Building[h:BuildingID/@id=$building_id]/h:Site/h:GeoLocation",
        building_id=building_id,
    )[0]
    lat = float(geolocation.Latitude)
    lon = float(geolocation.Longitude)
    return lat, lon


def join_bills_weather(bills_orig: pd.DataFrame, lat: float, lon: float, **kw) -> pd.DataFrame:
    """Join the bills dataframe with an average daily temperatue

    :param bills_orig: Dataframe with columns `start_date`, `end_date`, and `consumption` representing each bill period.
    :type bills_orig: pd.DataFrame
    :param lat: latitude of building
    :type lat: float
    :param lon: longitude of building
    :type lon: float
    :return: An augmented bills dataframe with additional `daily_consumption`, `n_days`, and `avg_temp` columns.
    :rtype: pd.DataFrame
    """
    start_date = bills_orig["start_date"].min().tz_convert("UTC")
    end_date = bills_orig["end_date"].max().tz_convert("UTC")
    ranked_stations = eeweather.rank_stations(lat, lon, **kw)
    isd_station, _ = eeweather.select_station(ranked_stations)
    tempC, _ = isd_station.load_isd_hourly_temp_data(start_date, end_date)
    tempC = tempC.tz_convert(bills_orig["start_date"].dt.tz)
    tempF = tempC * 1.8 + 32

    bills = bills_orig.copy()
    bills["n_days"] = (
        (bills_orig["end_date"] - bills_orig["start_date"]).dt.total_seconds() / 60 / 60 / 24
    )
    bills["daily_consumption"] = bills["consumption"] / bills["n_days"]

    bill_avg_temps = []
    for _, row in bills.iterrows():
        bill_temps = tempF[row["start_date"] : row["end_date"]]
        if bill_temps.empty:
            bill_avg_temps.append(None)
        else:
            bill_avg_temps.append(bill_temps.mean())
    bills["avg_temp"] = bill_avg_temps
    return bills
