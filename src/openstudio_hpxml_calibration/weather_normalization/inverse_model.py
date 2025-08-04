import pandas as pd

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import EnergyUnitType, FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_hpxml_energy_units
from openstudio_hpxml_calibration.weather_normalization.regression import (
    UtilityBillRegressionModel,
    fit_model,
)


class InverseModel:
    def __init__(self, hpxml: HpxmlDoc, building_id: str | None = None):
        self.hpxml = hpxml
        self.building_id = building_id
        self.bills_by_fuel_type, self.bill_units, self.tz = ud.get_bills_from_hpxml(
            hpxml, building_id
        )
        self.bills_weather_by_fuel_type_in_btu = {}
        self.lat_lon = hpxml.get_lat_lon()
        self.regression_models: dict[FuelType, UtilityBillRegressionModel] = {}
        for fuel_type, bills in self.bills_by_fuel_type.items():
            bills_weather, _ = ud.join_bills_weather(bills, *self.lat_lon)
            for col in ["consumption", "daily_consumption"]:
                bills_weather[col] = convert_hpxml_energy_units(
                    bills_weather[col],
                    self.bill_units[fuel_type],
                    EnergyUnitType.BTU,
                    fuel_type,
                )
            self.bills_weather_by_fuel_type_in_btu[fuel_type] = bills_weather

    def get_model(self, fuel_type: FuelType) -> UtilityBillRegressionModel:
        try:
            return self.regression_models[fuel_type]
        except KeyError:
            # TODO: Determine sufficiency for bill coverage
            bills_weather = self.bills_weather_by_fuel_type_in_btu[fuel_type]
            model = fit_model(bills_weather, bpi2400=False)  # FIXME: model fit criteria
            self.regression_models[fuel_type] = model
            return model

    def predict_epw_daily(self, fuel_type: FuelType) -> pd.Series:
        """
        Predict the annual energy consumption for a given fuel type using the regression model.

        :param fuel_type: The fuel type to predict for.
        :type fuel_type: FuelType
        :return: The predicted annual energy consumption in BTU for baseload, heating, and cooling.
        :rtype: pd.Series
        """
        model = self.get_model(fuel_type)
        epw, _ = self.hpxml.get_epw_data(coerce_year=2007)
        epw_daily_avg_temp = epw["temp_air"].groupby(pd.Grouper(freq="D")).mean() * 1.8 + 32
        daily_predicted_fuel_use = model.predict_disaggregated(epw_daily_avg_temp.to_numpy())
        return daily_predicted_fuel_use
