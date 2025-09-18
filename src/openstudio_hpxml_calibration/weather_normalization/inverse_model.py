import pandas as pd

import openstudio_hpxml_calibration.weather_normalization.utility_data as ud
from openstudio_hpxml_calibration.hpxml import EnergyUnitType, FuelType, HpxmlDoc
from openstudio_hpxml_calibration.units import convert_hpxml_energy_units
from openstudio_hpxml_calibration.weather_normalization.regression import (
    UtilityBillRegressionModel,
    fit_model,
)


class InverseModel:
    def __init__(self, hpxml: HpxmlDoc, user_config: dict, building_id: str | None = None):
        """
        Initialize the InverseModel for weather normalization.

        Sets up regression models and bill data for each fuel type based on the HPXML document.

        :param hpxml: HPXML document object.
        :type hpxml: HpxmlDoc
        :param user_config: Optional user configuration dictionary.
        :type user_config: dict, optional
        """
        self.user_config = user_config
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
        """
        Retrieve or fit the regression model for a given fuel type.

        This method returns the regression model for the specified fuel type, fitting it if necessary
        using the bill and weather data from the HPXML document.

        :param fuel_type: The fuel type for which to retrieve or fit the regression model.
        :type fuel_type: FuelType
        :return: The fitted regression model for the specified fuel type.
        :rtype: UtilityBillRegressionModel
        """
        try:
            return self.regression_models[fuel_type]
        except KeyError:
            bills_weather = self.bills_weather_by_fuel_type_in_btu[fuel_type]
            fuel_types = self.hpxml.get_fuel_types()
            conditioning_fuels = fuel_types["heating"] | fuel_types["cooling"]
            model = fit_model(
                bills_weather,
                cvrmse_requirement=self.user_config["acceptance_criteria"][
                    "bill_regression_max_cvrmse"
                ],
                conditioning_fuels=conditioning_fuels,
                fuel_type=fuel_type,
            )
            self.regression_models[fuel_type] = model
            return model

    def predict_epw_daily(self, fuel_type: FuelType) -> pd.Series:
        """
        Predict daily energy consumption using the regression model for a given fuel type.

        Uses the fitted regression model to estimate daily consumption for each day in the EPW weather file.

        :param fuel_type: The fuel type for which to predict daily consumption.
        :type fuel_type: FuelType
        :return: Array of predicted daily consumption values.
        :rtype: np.ndarray
        """
        model = self.get_model(fuel_type)
        epw, _ = self.hpxml.get_epw_data(coerce_year=2007)
        epw_daily_avg_temp = epw["temp_air"].groupby(pd.Grouper(freq="D")).mean() * 1.8 + 32
        daily_predicted_fuel_use = model.predict_disaggregated(epw_daily_avg_temp.to_numpy())
        return daily_predicted_fuel_use
