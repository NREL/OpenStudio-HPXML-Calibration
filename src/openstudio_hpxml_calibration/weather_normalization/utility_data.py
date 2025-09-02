import datetime as dt
import warnings

import eeweather
import numpy as np
import pandas as pd
import yaml
from lxml import objectify

from openstudio_hpxml_calibration.hpxml import EnergyUnitType, FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units


def read_yaml_file(config_path: str):
    with open(config_path) as file:
        return yaml.safe_load(file)


def get_datetime_subel(el: objectify.ObjectifiedElement, subel_name: str) -> pd.Timestamp | None:
    subel = getattr(el, subel_name, None)
    if subel is None:
        return subel
    else:
        return pd.to_datetime(str(subel))


def get_bills_from_hpxml(
    hpxml: HpxmlDoc, building_id: str | None = None
) -> tuple[dict[FuelType, pd.DataFrame], dict[FuelType, EnergyUnitType], dt.timezone]:
    """Get utility bills from an HPXML file.

    :param hpxml: The HPXML file
    :type hpxml: HpxmlDoc
    :param building_id: Optional building_id of the building you want to get bills for.
    :type building_id: str | None
    :return:
        * `bills_by_fuel_type`, a dictionary with fuel types as the keys and a
          dataframe as the values with columns `start_date`, `end_date`, and `consumption`
        * `bill_units`, a dictionary with a map of fuel type to units in the HPXML file.
        * `local_standard_tz`, the timezone (standard, no DST) of the location.
    :rtype: tuple[dict[FuelType, pd.DataFrame], dict[FuelType, EnergyUnitType], dt.timezone]
    """
    if building_id is None:
        building_id = hpxml.get_first_building_id()
    building = hpxml.get_building(building_id)
    try:
        utc_offset = int(building.Site.TimeZone.UTCOffset)
    except AttributeError:
        _, epw_metadata = hpxml.get_epw_data(building_id)
        utc_offset = epw_metadata["TZ"]

    local_standard_tz = dt.timezone(dt.timedelta(hours=utc_offset))

    bills_by_fuel_type = {}
    bill_units = {}

    consumptions = hpxml.xpath(
        "h:Consumption[h:BuildingID/@idref=$building_id]",
        building_id=building_id,
    )
    if not consumptions:
        raise ValueError(
            f"No matching Consumption/BuildingID/@idref equal to Building/BuildingID/@id={building_id} was found in HPXML."
        )
    for consumption in consumptions:
        cons_infos = consumption.xpath(
            "h:ConsumptionDetails/h:ConsumptionInfo", namespaces=hpxml.ns
        )
        for cons_info in cons_infos:
            fuel_type = FuelType(cons_info.ConsumptionType.Energy.FuelType)
            bill_units[fuel_type] = EnergyUnitType(cons_info.ConsumptionType.Energy.UnitofMeasure)
            rows = []
            for el in cons_info.ConsumptionDetail:
                rows.append(
                    [
                        get_datetime_subel(el, "StartDateTime"),
                        get_datetime_subel(el, "EndDateTime"),
                        float(el.Consumption),
                    ]
                )
            bills = pd.DataFrame.from_records(
                rows, columns=["start_date", "end_date", "consumption"]
            )
            if pd.isna(bills["end_date"]).all():
                bills["end_date"] = bills["start_date"].shift(-1)
            if pd.isna(bills["start_date"]).all():
                bills["start_date"] = bills["end_date"].shift(1)

            bills["start_day_of_year"] = bills["start_date"].dt.dayofyear
            # Subtract 1 from end day because the bill shows it at hour 00:00 of the end date
            bills["end_day_of_year"] = bills["end_date"].dt.dayofyear - 1

            bills["start_date"] = bills["start_date"].dt.tz_localize(local_standard_tz)
            bills["end_date"] = bills["end_date"].dt.tz_localize(local_standard_tz)
            bills_by_fuel_type[fuel_type] = bills

    return bills_by_fuel_type, bill_units, local_standard_tz


def join_bills_weather(bills_orig: pd.DataFrame, lat: float, lon: float, **kw) -> pd.DataFrame:
    """Join the bills dataframe with an average daily temperature

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
    rank_stations_kw = {"minimum_quality": "medium"}
    rank_stations_kw.update(kw)
    with warnings.catch_warnings():
        ranked_stations = eeweather.rank_stations(lat, lon, **rank_stations_kw)
        isd_station, _ = eeweather.select_station(
            ranked_stations, coverage_range=(start_date, end_date)
        )
        tempC, _ = isd_station.load_isd_hourly_temp_data(start_date, end_date)
    tempC = tempC.tz_convert(bills_orig["start_date"].dt.tz)
    tempF = convert_units(tempC, "c", "f")
    bills = bills_orig.copy()
    bills["n_days"] = (
        (bills_orig["end_date"] - bills_orig["start_date"]).dt.total_seconds() / 60 / 60 / 24
    )
    bills["daily_consumption"] = bills["consumption"] / bills["n_days"]

    bills = bills.replace([np.inf, -np.inf], np.nan).dropna().copy()

    bill_avg_temps = []
    for _, row in bills.iterrows():
        bill_temps = tempF[row["start_date"] : row["end_date"]]
        if bill_temps.empty:
            bill_avg_temps.append(None)
        else:
            bill_avg_temps.append(bill_temps.mean())
    bills["avg_temp"] = bill_avg_temps
    return bills, tempF
