import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, curve_fit, minimize

from openstudio_hpxml_calibration.hpxml import FuelType


class UtilityBillRegressionModel:
    """Utility Bill Regression Model Base Class

    Implements a utility bill regression given the ``bills_temps`` dataframe.

    :raises NotImplementedError: When it is called on the base class.
    """

    MODEL_NAME: str = "Base Model"

    def __init__(self):
        self.parameters = None
        self.pcov = None
        self.INITIAL_GUESSES = []
        self.BOUNDS = None
        self.xscale = None

    @property
    def n_parameters(self) -> int:
        return len(self.INITIAL_GUESSES)

    def fit(self, bills_temps: pd.DataFrame) -> None:
        """Fit the regression model to the provided billing and temperature data.

        This method estimates the model parameters that best fit the given data
        using non-linear curve fitting.

        :param bills_temps: A dataframe containing billing and temperature data.
        :type bills_temps: pd.DataFrame
        """
        popt, pcov = curve_fit(
            self.func,
            bills_temps["avg_temp"].to_numpy(),
            bills_temps["daily_consumption"].to_numpy(),
            p0=self.INITIAL_GUESSES,
            bounds=self.BOUNDS,
            method="trf",
            x_scale=self.XSCALE,
        )
        self.parameters = popt
        self.pcov = pcov
        self.cvrmse = self.calc_cvrmse(bills_temps)

    def __call__(self, temperatures: np.ndarray) -> np.ndarray:
        """Given an array of temperatures [degF], return the predicted energy use.

        This makes it so that an instance of this class can be called like a function.

        :param temperatures: An array of daily temperatures in degF.
        :type temperatures: np.ndarray
        :return: An array of daily energy use, in the units the model was trained on.
        :rtype: np.ndarray
        """
        return self.func(temperatures, *self.parameters)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
        """Predict the disaggregated energy use for a given array of temperatures.

        :param temperatures: An array of daily temperatures in degF.
        :type temperatures: np.ndarray
        :return: A dataframe with "baseline", "heating", and "cooling" columns.
        :rtype: np.ndarray
        """
        raise NotImplementedError

    def func(self, x: Sequence[float] | np.ndarray, *args: list[float | np.floating]) -> np.ndarray:
        """Model function to be implemented by subclasses.

        :param x: Independent variable, typically temperature.
        :type x: Sequence[float] | np.ndarray
        :param args: Model parameters.
        :type args: list[float | np.floating]
        :return: Dependent variable, typically energy consumption.
        :rtype: np.ndarray
        """
        raise NotImplementedError

    def calc_cvrmse(self, bills_temps: pd.DataFrame) -> float:
        """Calculate the CVRMSE for the model and the bills_temps dataframe.

        :param bills_temps: A dataframe with bills and temperatures
        :type bills_temps: pd.DataFrame
        :return: Calculated CVRMSE
        :rtype: float
        """
        y = bills_temps["daily_consumption"].to_numpy()
        y_hat = self(bills_temps["avg_temp"].to_numpy())
        return np.sqrt(np.sum((y - y_hat) ** 2) / (y.shape[0] - self.n_parameters)) / y.mean()


def estimate_initial_guesses_3param(model_type: str, bills_temps: pd.DataFrame) -> list[float]:
    """Estimate initial guesses for the parameters of the 3-parameter model.

    :param model_type: Type of the model, either "cooling" or "heating".
    :type model_type: str
    :param bills_temps: A dataframe with bills and temperatures
    :type bills_temps: pd.DataFrame
    :return: List of initial guesses for the model parameters.
    :rtype: list[float]
    :raises ValueError: If the model type is unknown.
    """
    temps = bills_temps["avg_temp"].to_numpy()
    usage = bills_temps["daily_consumption"].to_numpy()
    # Estimate baseload by taking the 10th percentile of usage data
    b1 = np.percentile(usage, 10)  # TODO: There might be a better way to estimate baseload

    if model_type == "cooling":
        b3 = 65  # TODO: There might be a better way to estimate balance temperature
        slope = (np.max(usage) - b1) / (np.max(temps) - b3 + 1e-6)
        b2 = max(slope, 1.0)

        return [b1, b2, b3]

    elif model_type == "heating":
        b3 = 65  # TODO: There might be a better way to estimate balance temperature
        slope = (np.max(usage) - b1) / (b3 - np.min(temps) + 1e-6)
        b2 = -abs(slope)

        return [b1, b2, b3]

    else:
        raise ValueError("Unknown model type")


def estimate_initial_guesses_5param(bills_temps: pd.DataFrame) -> list[float]:
    """Estimate initial guesses for the parameters of the 5-parameter model.

    :param bills_temps: A dataframe with bills and temperatures
    :type bills_temps: pd.DataFrame
    :return: List of initial guesses for the model parameters.
    :rtype: list[float]
    """
    temps = bills_temps["avg_temp"].to_numpy()
    usage = bills_temps["daily_consumption"].to_numpy()
    # Estimate baseload by taking the 10th percentile of usage data
    b1 = np.percentile(usage, 10)  # TODO: There might be a better way to estimate baseload

    # Heating slope (b2) and balance temperature (b4)
    select_cold_temps = temps <= np.median(temps)
    cold_temps = temps[select_cold_temps]
    cold_usage = usage[select_cold_temps]
    b4 = 55  # TODO: There might be a better way to estimate balance point
    heating_slope = -abs((np.max(cold_usage) - b1) / (b4 - np.min(cold_temps) + 1e-6))
    b2 = heating_slope

    # Cooling slope (b3) and balance temperature
    select_hot_temps = temps >= np.median(temps)
    hot_temps = temps[select_hot_temps]
    hot_usage = usage[select_hot_temps]
    b5 = 65  # TODO: There might be a better way to estimate balance point
    cooling_slope = max((np.max(hot_usage) - b1) / (np.max(hot_temps) - b5 + 1e-6), 1.0)
    b3 = cooling_slope

    return [b1, b2, b3, b4, b5]


def estimate_bounds_3param(model_type: str, bills_temps: pd.DataFrame) -> Bounds:
    """Estimate the bounds for the parameters of the 3-parameter model.

    :param model_type: Type of the model, either "cooling" or "heating".
    :type model_type: str
    :param bills_temps: A dataframe with bills and temperatures
    :type bills_temps: pd.DataFrame
    :return: Bounds object with lower and upper bounds for the model parameters.
    :rtype: Bounds
    :raises ValueError: If the model type is unknown.
    """
    usage = bills_temps["daily_consumption"].to_numpy()
    baseload_lb = np.min(usage)

    # TODO: Improve slope bounds
    if model_type == "heating":
        return Bounds(lb=[baseload_lb, -np.inf, 30.0], ub=[np.inf, 0.0, 75.0])
    elif model_type == "cooling":
        return Bounds(lb=[baseload_lb, 0.0, 30.0], ub=[np.inf, np.inf, 75.0])
    else:
        raise ValueError("Unknown model type")


def estimate_bounds_5param(bills_temps: pd.DataFrame) -> Bounds:
    """Estimate the bounds for the parameters of the 5-parameter model.

    :param bills_temps: A dataframe with bills and temperatures
    :type bills_temps: pd.DataFrame
    :return: Bounds object with lower and upper bounds for the model parameters.
    :rtype: Bounds
    """
    usage = bills_temps["daily_consumption"].to_numpy()
    baseload_lb = np.min(usage)

    # TODO: Improve slope bounds
    return Bounds(
        lb=[baseload_lb, -np.inf, 0.0, 30.0, 30.0],
        ub=[np.inf, 0.0, np.inf, 75.0, 75.0],
    )


class ThreeParameterCooling(UtilityBillRegressionModel):
    """3-parameter cooling model from ASHRAE Guideline 14"""

    MODEL_NAME = "3-parameter Cooling"

    def __init__(self):
        super().__init__()

    def fit(self, bills_temps: pd.DataFrame) -> None:
        """Fit the regression model to the cooling billing and temperature data.

        :param bills_temps: A dataframe containing cooling billing and temperature data.
        :type bills_temps: pd.DataFrame
        """
        self.INITIAL_GUESSES = estimate_initial_guesses_3param("cooling", bills_temps)
        self.BOUNDS = estimate_bounds_3param("cooling", bills_temps)
        self.XSCALE = np.array([5000.0, 1000.0, 1.0])
        super().fit(bills_temps)

    def func(
        self,
        x: Sequence[float] | np.ndarray,
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        """Model function for the 3-parameter cooling model.

        :param x: Independent variable, typically temperature.
        :type x: Sequence[float] | np.ndarray
        :param b1: Baseload consumption.
        :type b1: float
        :param b2: Cooling slope.
        :type b2: float
        :param b3: Balance temperature.
        :type b3: float
        :return: Dependent variable, typically energy consumption.
        :rtype: np.ndarray
        """
        x_arr = np.array(x)
        return b1 + b2 * np.maximum(x_arr - b3, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
        """Predict the disaggregated energy use for a given array of temperatures.

        :param temperatures: An array of daily temperatures in degF.
        :type temperatures: np.ndarray
        :return: A dataframe with "baseline", "heating", and "cooling" columns.
        :rtype: np.ndarray
        """
        temperatures_arr = np.array(temperatures)
        b1, b2, b3 = self.parameters  # unpack the parameters
        heating = np.zeros_like(temperatures_arr, dtype=float)
        cooling = b2 * np.maximum(temperatures_arr - b3, 0)
        baseload = np.ones_like(temperatures_arr, dtype=float) * b1
        return pd.DataFrame({"baseload": baseload, "heating": heating, "cooling": cooling})


class ThreeParameterHeating(UtilityBillRegressionModel):
    """3-parameter heating model from ASHRAE Guideline 14"""

    MODEL_NAME = "3-parameter Heating"

    def __init__(self):
        super().__init__()

    def fit(self, bills_temps: pd.DataFrame) -> None:
        """Fit the regression model to the heating billing and temperature data.

        :param bills_temps: A dataframe containing heating billing and temperature data.
        :type bills_temps: pd.DataFrame
        """
        self.INITIAL_GUESSES = estimate_initial_guesses_3param("heating", bills_temps)
        self.BOUNDS = estimate_bounds_3param("heating", bills_temps)
        self.XSCALE = np.array([5000.0, 1000.0, 1.0])
        super().fit(bills_temps)

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        """Model function for the 3-parameter heating model.

        :param x: Independent variable, typically temperature.
        :type x: Sequence[float] | np.ndarray
        :param b1: Baseload consumption.
        :type b1: float
        :param b2: Heating slope.
        :type b2: float
        :param b3: Balance temperature.
        :type b3: float
        :return: Dependent variable, typically energy consumption.
        :rtype: np.ndarray
        """
        x_arr = np.array(x)
        return b1 + b2 * np.minimum(x_arr - b3, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
        """Predict the disaggregated energy use for a given array of temperatures.

        :param temperatures: An array of daily temperatures in degF.
        :type temperatures: np.ndarray
        :return: A dataframe with "baseline", "heating", and "cooling" columns.
        :rtype: np.ndarray
        """
        temperatures_arr = np.array(temperatures)
        b1, b2, b3 = self.parameters  # unpack the parameters
        heating = b2 * np.minimum(temperatures_arr - b3, 0)
        cooling = np.zeros_like(temperatures_arr, dtype=float)
        baseload = np.ones_like(temperatures_arr, dtype=float) * b1
        return pd.DataFrame({"baseload": baseload, "heating": heating, "cooling": cooling})


class FiveParameter(UtilityBillRegressionModel):
    """5-parameter heating and cooling model from ASHRAE Guideline 14"""

    MODEL_NAME = "5-parameter"

    def __init__(self):
        super().__init__()

    def fit(self, bills_temps: pd.DataFrame) -> None:
        """Fit the regression model to the heating and cooling billing and temperature data.

        :param bills_temps: A dataframe containing heating and cooling billing and temperature data.
        :type bills_temps: pd.DataFrame
        """
        self.INITIAL_GUESSES = estimate_initial_guesses_5param(bills_temps)
        self.BOUNDS = estimate_bounds_5param(bills_temps)
        self.XSCALE = np.array([5000.0, 1000.0, 1000.0, 1.0, 1.0])

        x = bills_temps["avg_temp"].to_numpy()
        y = bills_temps["daily_consumption"].to_numpy()

        def objective(params):
            return np.sum((self.func(x, *params) - y) ** 2)

        # Constrain the heating and cooling balance temps to differ by more than 5
        # constraints = {
        #     "type": "ineq",
        #     "fun": lambda params: params[4] - params[3] - 5,
        # }

        bounds = list(zip(self.BOUNDS.lb, self.BOUNDS.ub))
        result = minimize(
            objective,
            self.INITIAL_GUESSES,
            method="trust-constr",  # trust-constr supports both bounds and constraints
            bounds=bounds,
            # constraints=constraints,
            options={
                "verbose": 0,
                "maxiter": 20000,
            },
        )
        if not result.success:
            raise RuntimeError(f"Optimization failed: {result.message}")

        self.parameters = result.x
        self.pcov = None  # scipy.optimize.minimize doesn't calculate it
        self.cvrmse = self.calc_cvrmse(bills_temps)

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
        b4: float | np.floating,
        b5: float | np.floating,
    ) -> np.ndarray:
        """Model function for the 5-parameter heating and cooling model.

        :param x: Independent variable, typically temperature.
        :type x: Sequence[float] | np.ndarray
        :param b1: Baseload consumption.
        :type b1: float
        :param b2: Heating slope.
        :type b2: float
        :param b3: Cooling slope.
        :type b3: float
        :param b4: Heating balance temperature.
        :type b4: float
        :param b5: Cooling balance temperature.
        :type b5: float
        :return: Dependent variable, typically energy consumption.
        :rtype: np.ndarray
        """
        x_arr = np.array(x)
        return b1 + b2 * np.minimum(x_arr - b4, 0) + b3 * np.maximum(x_arr - b5, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
        """Predict the disaggregated energy use for a given array of temperatures.

        :param temperatures: An array of daily temperatures in degF.
        :type temperatures: np.ndarray
        :return: A dataframe with "baseline", "heating", and "cooling" columns.
        :rtype: np.ndarray
        """
        temperatures_arr = np.array(temperatures)
        b1, b2, b3, b4, b5 = self.parameters  # unpack the parameters
        heating = b2 * np.minimum(temperatures_arr - b4, 0)
        cooling = b3 * np.maximum(temperatures_arr - b5, 0)
        baseload = np.ones_like(temperatures_arr, dtype=float) * b1
        return pd.DataFrame({"baseload": baseload, "heating": heating, "cooling": cooling})


class Bpi2400ModelFitError(Exception):
    """
    Exception raised when the BPI-2400 regression model fit fails.

    Used to indicate that the regression model could not be fit with sufficient accuracy.
    """


def fit_model(
    bills_temps: pd.DataFrame,
    cvrmse_requirement: float,
    conditioning_fuels: set,
    fuel_type: FuelType,
) -> UtilityBillRegressionModel:
    """Fit a regression model to the utility bills

    The ``bills_temps`` dataframe should be in the format returned by the
    ``utility_data.join_bills_weather`` function. At a minimum this should
    include the columns "daily_consumption" and "avg_temp" in degF. The index is
    ignored.

    :param bills_temps: dataframe of utility bills and temperatures.
    :type bills_temps: pd.DataFrame
    :param cvrmse_requirement: CVRMSE requirement for model selection.
    :type cvrmse_requirement: float
    :raises Bpi2400ModelFitError: Error thrown if model doesn't meet BPI-2400
        criteria
    :return: An instance of a model class, fit to your data.
    :rtype: UtilityBillRegressionModel
    """
    models_to_try = [ThreeParameterCooling, ThreeParameterHeating, FiveParameter]
    models = []
    for ModelClass in models_to_try:
        model = ModelClass()
        try:
            model.fit(bills_temps)
            models.append(model)
        except RuntimeError as ex:
            if (
                str(ex)
                == "Optimal parameters not found: The maximum number of function evaluations is exceeded."
            ):
                warnings.warn(f"Unable to fit {ModelClass.MODEL_NAME} to data.")
                continue
            else:
                raise
    best_model = min(models, key=lambda x: x.cvrmse)
    if fuel_type.value in conditioning_fuels and (cvrmse := best_model.cvrmse) > cvrmse_requirement:
        raise Bpi2400ModelFitError(
            f"CVRMSE = {cvrmse:0.1%} for {fuel_type.value}, which is greater than {cvrmse_requirement:0.1%}"
        )
    return best_model
