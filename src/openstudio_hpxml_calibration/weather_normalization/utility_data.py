import datetime as dt
import os

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


def get_bills_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]:
    local_standard_tz = dt.timezone(
        dt.timedelta(hours=int(hpxml_root.Building.Site.TimeZone.UTCOffset))
    )

    bills_by_fuel_type = {}
    bill_units = {}
    for cons_info in hpxml_root.Consumption.ConsumptionDetails.ConsumptionInfo:
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
        bills_by_fuel_type[fuel_type] = bills

    return bills_by_fuel_type, bill_units, local_standard_tz


def get_lat_lon_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement,
) -> tuple[float, float]:
    lat = float(hpxml_root.Building.Site.GeoLocation.Latitude)
    lon = float(hpxml_root.Building.Site.GeoLocation.Longitude)
    return lat, lon


def join_bills_weather(bills: pd.DataFrame, lat: float, lon: float, **kw):
    bills["start_date"].min()
    bills["end_date"].min()
    ranked_stations = eeweather.rank_stations(lat, lon, **kw)
    isd_station, isd_warnings = eeweather.select_station(ranked_stations)
