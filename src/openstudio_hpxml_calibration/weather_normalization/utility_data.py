import datetime as dt
from pathlib import Path

import eeweather
import pandas as pd
from lxml import objectify
from pvlib.iotools import read_epw

from openstudio_hpxml_calibration.hpxml import HpxmlDoc


def get_datetime_subel(el: objectify.ObjectifiedElement, subel_name: str) -> pd.Timestamp | None:
    subel = getattr(el, subel_name, None)
    if subel is None:
        return subel
    else:
        return pd.to_datetime(str(subel))


def get_bills_from_hpxml(
    hpxml: HpxmlDoc, building_id: str | None = None
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]:
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
    :rtype: tuple[dict[str, pd.DataFrame], dict[str, str], dt.timezone]
    """
    if building_id is None:
        building_id = hpxml.get_first_building_id()
    local_standard_tz = dt.timezone(dt.timedelta(hours=int(hpxml.Building.Site.TimeZone.UTCOffset)))

    bills_by_fuel_type = {}
    bill_units = {}
    for cons_info in hpxml.xpath(
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


def get_lat_lon_from_hpxml(hpxml: HpxmlDoc, building_id: str | None = None) -> tuple[float, float]:
    """Get latitude, longitude from hpxml file

    :param hpxml: _description_
    :type hpxml: HpxmlDoc
    :param building_id: Optional building_id of the building you want to get location for.
    :type building_id: str | None
    :return: _description_
    :rtype: tuple[float, float]
    """
    os_hpxml_path = Path(__file__).resolve().parent.parent.parent / "OpenStudio-HPXML"
    building = hpxml.get_building(building_id)
    try:
        # Option 1: Get directly from HPXML
        geolocation = building.Site.GeoLocation
        lat = float(geolocation.Latitude)
        lon = float(geolocation.Longitude)
    except AttributeError:
        try:
            # Option 2: Get location from EPW file header
            epw_file = str(
                building.BuildingDetails.ClimateandRiskZones.WeatherStation.extension.EPWFilePath
            )
        except AttributeError:
            # Option 3: Get location from zipcode
            zipcode = str(building.Site.Address.ZipCode)
            zipcode_lookup_filename = (
                os_hpxml_path / "HPXMLtoOpenStudio/resources/data/zipcode_weather_stations.csv"
            )
            zipcodes = pd.read_csv(
                zipcode_lookup_filename,
                usecols=["zipcode", "zipcode_latitude", "zipcode_longitude"],
                index_col="zipcode",
                dtype={"zipcode": str},
            )
            lat = zipcodes.loc[zipcode, "zipcode_latitude"]
            lon = zipcodes.loc[zipcode, "zipcode_longitude"]
        else:
            # Option 2, continued
            epw_path = Path(epw_file)
            if not epw_path.is_absolute():
                possible_parent_paths = [hpxml.file_path.parent, os_hpxml_path / "weather"]
                for parent_path in possible_parent_paths:
                    epw_path = parent_path / Path(epw_file)
                    if epw_path.exists():
                        break
            if not epw_path.exists():
                raise FileNotFoundError(str(epw_path))
            _, epw_metadata = read_epw(epw_path)
            lat = epw_metadata["latitude"]
            lon = epw_metadata["longitude"]

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
    rank_stations_kw = {"minimum_quality": "medium"}
    rank_stations_kw.update(kw)
    ranked_stations = eeweather.rank_stations(lat, lon, **rank_stations_kw)
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
