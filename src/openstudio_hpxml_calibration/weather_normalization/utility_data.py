import datetime as dt
import os
import numpy as np
import pandas as pd
from lxml import objectify, etree


def parse_hpxml(filename: os.PathLike) -> etree._ElementTree:
    return objectify.parse(str(filename))


def get_bills_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]:
    local_standard_tz = dt.timezone(
        dt.timedelta(hours=int(hpxml_root.Building.Site.TimeZone.UTCOffset))
    )

    bills = {}
    bill_units = {}
    for cons_info in hpxml_root.Consumption.ConsumptionDetails.ConsumptionInfo:
        fuel_type = str(cons_info.ConsumptionType.Energy.FuelType)
        bill_units[fuel_type] = str(cons_info.ConsumptionType.Energy.UnitofMeasure)
        vals = []
        start_dates = []
        for el in cons_info.ConsumptionDetail:
            vals.append(float(el.Consumption))
            start_dates.append(str(el.StartDateTime))
            end_date = str(el.EndDateTime)
        start_dates.append(
            (pd.to_datetime(end_date) + pd.Timedelta(seconds=1)).isoformat()
        )
        vals.append(np.nan)
        start_dates = pd.to_datetime(start_dates)
        start_dates = start_dates.tz_localize(local_standard_tz)
        bills[fuel_type] = pd.DataFrame({"value": vals}, index=start_dates)

    return bills, bill_units, local_standard_tz


def get_lat_lon_from_hpxml(
    hpxml_root: objectify.ObjectifiedElement,
) -> tuple[float, float]:
    lat = float(hpxml_root.Building.Site.GeoLocation.Latitude)
    lon = float(hpxml_root.Building.Site.GeoLocation.Longitude)
    return lat, lon
