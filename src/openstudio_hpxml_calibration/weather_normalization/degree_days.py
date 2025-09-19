from collections import namedtuple

import pandas as pd

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import HpxmlDoc
from openstudio_hpxml_calibration.units import convert_units


def calc_daily_dbs(hpxml: HpxmlDoc) -> namedtuple:
    """
    Calculate daily average dry bulb temperatures from EPW weather data.

    This function computes daily average dry bulb temperatures in both Celsius and Fahrenheit
    from the EPW weather data contained in the provided HPXML document.

    :param hpxml: HPXML document object containing weather data.
    :type hpxml: HpxmlDoc
    :return: Named tuple with fields 'c' (Celsius) and 'f' (Fahrenheit), each as a pandas Series.
    :rtype: namedtuple
    """
    DailyTemps = namedtuple("DailyTemps", ["c", "f"])
    epw, _ = hpxml.get_epw_data(coerce_year=2007)
    epw_daily_avg_temp_c = epw["temp_air"].groupby(pd.Grouper(freq="D")).mean()
    epw_daily_avg_temp_f = convert_units(epw_daily_avg_temp_c, "c", "f")
    return DailyTemps(c=epw_daily_avg_temp_c, f=epw_daily_avg_temp_f)


def calc_degree_days(daily_dbs: pd.Series, base_temp_f: float, is_heating: bool) -> float:
    """
    Calculate degree days from daily temperature data.

    This function computes the total heating or cooling degree days for a given base temperature
    using daily average dry bulb temperatures.

    :param daily_dbs: Series of daily average dry bulb temperatures (°F).
    :type daily_dbs: pd.Series
    :param base_temp_f: Base temperature in Fahrenheit for degree day calculation.
    :type base_temp_f: float
    :param is_heating: If True, calculates heating degree days; if False, cooling degree days.
    :type is_heating: bool
    :return: Total degree days for the specified base temperature and mode.
    :rtype: float
    """

    deg_days = []
    for temp in daily_dbs:
        if is_heating and temp < base_temp_f:
            deg_days.append(base_temp_f - temp)
        elif not is_heating and temp > base_temp_f:
            deg_days.append(temp - base_temp_f)

    if len(deg_days) == 0:
        return 0.0

    deg_days_sum = round(sum(deg_days), 2)
    return deg_days_sum


def calc_heat_cool_degree_days(dailydbs: pd.Series) -> dict:
    """
    Calculate heating and cooling degree days from daily temperature data.

    This function returns a dictionary containing heating and cooling degree days (HDD65F, CDD65F)
    for the provided daily average dry bulb temperatures.

    :param dailydbs: Series of daily average dry bulb temperatures (°F).
    :type dailydbs: pd.Series
    :return: Dictionary with keys 'HDD65F' and 'CDD65F' and their respective degree day values.
    :rtype: dict
    """
    degree_days = {}
    degree_days["HDD65F"] = calc_degree_days(dailydbs, 65, True)
    # degree_days["HDD50F"] = calc_degree_days(dailydbs, 50, True)
    degree_days["CDD65F"] = calc_degree_days(dailydbs, 65, False)
    # degree_days["CDD50F"] = calc_degree_days(dailydbs, 50, False)
    return degree_days


def calculate_annual_degree_days(hpxml: HpxmlDoc) -> tuple[dict, dict]:
    """
    Calculate annual heating and cooling degree days for each fuel type.

    This function computes the total heating degree days (HDD) and cooling degree days (CDD)
    for the actual period and the TMY period, for each fuel type present in the HPXML document.

    :param hpxml: HPXML document object containing weather and fuel information.
    :type hpxml: HpxmlDoc
    :return: Tuple containing dictionaries of total period TMY degree days and actual degree days by fuel type.
    :rtype: tuple[dict, dict]
    """
    tmy_dry_bulb_temps_f = calc_daily_dbs(hpxml).f
    bills_by_fuel_type, _, _ = ud.get_bills_from_hpxml(hpxml)
    lat, lon = hpxml.get_lat_lon()
    bill_tmy_degree_days = {}
    total_period_actual_dd = {}

    # Use day-of-year because TMY data contains multiple years
    tmy_temp_index_doy = tmy_dry_bulb_temps_f.index.dayofyear

    for fuel_type, bills in bills_by_fuel_type.items():
        # format fuel type for dictionary keys
        fuel_type_name = fuel_type.name.lower().replace("_", " ")
        # Get degree days of actual weather during bill periods
        _, actual_temp_f = ud.join_bills_weather(bills, lat, lon)
        daily_actual_temps = actual_temp_f.resample("D").mean()
        actual_degree_days = calc_heat_cool_degree_days(daily_actual_temps)
        actual_degree_days = {k: round(v) for k, v in actual_degree_days.items()}
        total_period_actual_dd[fuel_type_name] = actual_degree_days

        # Get degree days of TMY weather
        bill_results = []
        for _, row in bills.iterrows():
            start_doy = row["start_day_of_year"]
            end_doy = row["end_day_of_year"]

            # Handle bills that wrap around the end of the year
            if start_doy <= end_doy:
                mask = (tmy_temp_index_doy >= start_doy) & (tmy_temp_index_doy <= end_doy)
            else:
                mask = (tmy_temp_index_doy >= start_doy) | (tmy_temp_index_doy <= end_doy)

            # Select the dry bulb temperatures for the bill period
            bill_dry_bulbs_tmy = tmy_dry_bulb_temps_f[mask]
            tmy_degree_days = calc_heat_cool_degree_days(bill_dry_bulbs_tmy)
            bill_results.append(
                {
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    **tmy_degree_days,
                }
            )
        bill_tmy_degree_days[fuel_type_name] = bill_results

    total_period_tmy_dd = {}
    for fuel, bill_list in bill_tmy_degree_days.items():
        hdd_total = round(sum(bill.get("HDD65F", 0) for bill in bill_list))
        cdd_total = round(sum(bill.get("CDD65F", 0) for bill in bill_list))
        total_period_tmy_dd[fuel] = {"HDD65F": hdd_total, "CDD65F": cdd_total}

    return total_period_tmy_dd, total_period_actual_dd


def _get_degree_days_for_period(weather_data, start_date, end_date):
    """
    Get degree days for a specified period from weather data.

    This function extracts the heating and cooling degree days between the given start and end dates.

    :param weather_data: Weather data containing degree days information.
    :type weather_data: pd.DataFrame
    :param start_date: Start date of the period.
    :type start_date: datetime
    :param end_date: End date of the period.
    :type end_date: datetime
    :return: Dictionary with HDD and CDD values for the period.
    :rtype: dict
    """
    period_data = weather_data[
        (weather_data["date"] >= start_date) & (weather_data["date"] <= end_date)
    ]
    hdd = period_data["HDD65F"].sum()
    cdd = period_data["CDD65F"].sum()
    return {"HDD65F": hdd, "CDD65F": cdd}
