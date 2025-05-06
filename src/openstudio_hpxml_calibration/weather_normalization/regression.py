import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, curve_fit


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


def estimate_initial_guesses(model_type: str, bills_temps: pd.DataFrame) -> list[float]:
    temps = bills_temps["avg_temp"].to_numpy()
    usage = bills_temps["daily_consumption"].to_numpy()
    # Estimate baseload by taking the 10th percentile of usage data
    b1 = np.percentile(usage, 10)  # TODO: There might be a better way to estimate baseload

    if model_type == "cooling":
        b3 = 65  # TODO: There might be a better way to estimate balance point
        slope = (np.max(usage) - b1) / (np.max(temps) - b3 + 1e-6)
        b2 = max(slope, 1.0)

        return [b1, b2, b3]

    elif model_type == "heating":
        b3 = 65  # TODO: There might be a better way to estimate balance point
        slope = (np.max(usage) - b1) / (b3 - np.min(temps) + 1e-6)
        b2 = -abs(slope)

        return [b1, b2, b3]

    else:
        raise ValueError("Unknown model type")


def estimate_initial_guesses_5param(bills_temps: pd.DataFrame) -> list[float]:
    temps = bills_temps["avg_temp"].to_numpy()
    usage = bills_temps["daily_consumption"].to_numpy()
    # Estimate baseload by taking the 10th percentile of usage data
    b1 = np.percentile(usage, 10)  # TODO: There might be a better way to estimate baseload

    # Heating slope (b2) and balance point (b4)
    cold_mask = temps < np.median(temps)
    cold_temps = temps[cold_mask]
    cold_usage = usage[cold_mask]
    b4 = 65  # TODO: There might be a better way to estimate balance point
    heating_slope = -abs((np.max(cold_usage) - b1) / (b4 - np.min(cold_temps) + 1e-6))
    b2 = heating_slope

    # Cooling slope (b3) and balance point (b5)
    hot_mask = temps > np.median(temps)
    hot_temps = temps[hot_mask]
    hot_usage = usage[hot_mask]
    b5 = 70  # TODO: There might be a better way to estimate balance point
    cooling_slope = max((np.max(hot_usage) - b1) / (np.max(hot_temps) - b5 + 1e-6), 1.0)
    b3 = cooling_slope

    return [b1, b2, b3, b4, b5]


class ThreeParameterCooling(UtilityBillRegressionModel):
    """3-parameter cooling model from ASHRAE Guideline 14"""

    MODEL_NAME = "3-parameter Cooling"

    def __init__(self):
        super().__init__()
        self.BOUNDS = Bounds(lb=[0.0, 0.0, 40.0], ub=[np.inf, np.inf, 90.0])
        self.XSCALE = np.array([5000.0, 1000.0, 1.0])
        self.INITIAL_GUESSES = []

    def fit(self, bills_temps: pd.DataFrame) -> None:
        self.INITIAL_GUESSES = estimate_initial_guesses("cooling", bills_temps)
        super().fit(bills_temps)

    def func(
        self,
        x: Sequence[float] | np.ndarray,
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        x_arr = np.array(x)
        return b1 + b2 * np.maximum(x_arr - b3, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
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
        self.BOUNDS = Bounds(lb=[0.0, -np.inf, 40.0], ub=[np.inf, 0.0, 90.0])
        self.XSCALE = np.array([5000.0, 1000.0, 1.0])
        self.INITIAL_GUESSES = []

    def fit(self, bills_temps: pd.DataFrame) -> None:
        self.INITIAL_GUESSES = estimate_initial_guesses("heating", bills_temps)
        super().fit(bills_temps)

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        x_arr = np.array(x)
        return b1 + b2 * np.minimum(x_arr - b3, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
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
        self.BOUNDS = Bounds(
            lb=[0.0, -np.inf, 0.0, 40.0, 40.0], ub=[np.inf, 0.0, np.inf, 90.0, 90.0]
        )
        self.XSCALE = np.array([5000.0, 1000.0, 1000.0, 1.0, 1.0])
        self.INITIAL_GUESSES = []

    def fit(self, bills_temps: pd.DataFrame) -> None:
        self.INITIAL_GUESSES = estimate_initial_guesses_5param(bills_temps)
        super().fit(bills_temps)

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
        b4: float | np.floating,
        b5: float | np.floating,
    ) -> np.ndarray:
        x_arr = np.array(x)
        return b1 + b2 * np.minimum(x_arr - b4, 0) + b3 * np.maximum(x_arr - b5, 0)

    def predict_disaggregated(self, temperatures: Sequence[float] | np.ndarray) -> pd.DataFrame:
        temperatures_arr = np.array(temperatures)
        b1, b2, b3, b4, b5 = self.parameters  # unpack the parameters
        heating = b2 * np.minimum(temperatures_arr - b4, 0)
        cooling = b3 * np.maximum(temperatures_arr - b5, 0)
        baseload = np.ones_like(temperatures_arr, dtype=float) * b1
        return pd.DataFrame({"baseload": baseload, "heating": heating, "cooling": cooling})


class Bpi2400ModelFitError(Exception):
    pass


def fit_model(bills_temps: pd.DataFrame, bpi2400=True) -> UtilityBillRegressionModel:
    """Fit a regression model to the utility bills

    The ``bills_data`` dataframe should be in the format returned by the
    ``utility_data.join_bills_weather`` function. At a minimum this should
    include the columns "daily_consumption" and "avg_temp" in degF. The index is
    ignored.

    :param bills_temps: dataframe of utility bills and temperatures.
    :type bills_temps: pd.DataFrame
    :param bpi2400: Use BPI-2400 criteria for model selection, defaults to True
    :type bpi2400: bool, optional
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
    best_model = min(models, key=lambda x: x.calc_cvrmse(bills_temps))
    if bpi2400 and (cvrmse := best_model.calc_cvrmse(bills_temps)) > 0.2:
        raise Bpi2400ModelFitError(f"CVRMSE = {cvrmse:0.1%}, which is greater than 20%")
    return best_model
