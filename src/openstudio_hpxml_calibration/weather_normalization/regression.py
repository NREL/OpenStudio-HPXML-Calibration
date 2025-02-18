from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, curve_fit


class UtilityBillRegressionModel:
    MODEL_NAME: str = "Base Model"
    INITIAL_GUESSES: list[float]
    BOUNDS: Bounds

    def __init__(self):
        self.parameters = np.array(self.INITIAL_GUESSES)

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
            method='dogbox'
        )
        self.parameters = popt
        self.pcov = pcov

    def __call__(self, temperatures: np.ndarray) -> np.ndarray:
        return self.func(temperatures, *self.parameters)

    def func(self, x: Sequence[float], *args: list[float | np.floating]) -> np.ndarray:
        raise NotImplementedError

    def calc_cvrmse(self, bills_temps: pd.DataFrame) -> float:
        y = bills_temps["daily_consumption"].to_numpy()
        y_hat = self(bills_temps["avg_temp"].to_numpy())
        return np.sqrt(np.sum((y - y_hat) ** 2) / (y.shape[0] - self.n_parameters)) / y.mean()


class ThreeParameterCooling(UtilityBillRegressionModel):
    MODEL_NAME = "3-parameter Cooling"
    INITIAL_GUESSES = [10.0, 5.0, 70.0]
    BOUNDS = Bounds(lb=[0.0, 0.0, 40.0], ub=np.inf)

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        x_arr = np.array(x)
        return b1 + b2 * np.maximum(x_arr - b3, 0)


class ThreeParameterHeating(UtilityBillRegressionModel):
    MODEL_NAME = "3-parameter Heating"
    INITIAL_GUESSES = [10.0, -1.0, 70.0]
    BOUNDS = Bounds(lb=[0.0, -np.inf, 20.0], ub=[np.inf, 0.0, 80.0])

    def func(
        self,
        x: Sequence[float],
        b1: float | np.floating,
        b2: float | np.floating,
        b3: float | np.floating,
    ) -> np.ndarray:
        x_arr = np.array(x)
        return b1 + b2 * np.minimum(x_arr - b3, 0)


class FiveParameter(UtilityBillRegressionModel):
    MODEL_NAME = "5-parameter"
    INITIAL_GUESSES = [10.0, -5.0, 5.0, 50.0, 70.0]
    BOUNDS = Bounds(lb=[0.0, -np.inf, 0.0, 20.0, 40.0], ub=[np.inf, 0.0, np.inf, 80.0, np.inf])

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


class Bpi2400ModelFitError(Exception):
    pass


def fit_model(bills_temps: pd.DataFrame, bpi2400=True) -> UtilityBillRegressionModel:
    models_to_try = [
        ThreeParameterCooling,
        ThreeParameterHeating,
        FiveParameter
    ]
    models = []
    for ModelClass in models_to_try:
        model = ModelClass()
        model.fit(bills_temps)
        models.append(model)
    best_model = min(models, key=lambda x: x.calc_cvrmse(bills_temps))
    if bpi2400 and (cvrmse := best_model.calc_cvrmse(bills_temps)) > 0.2:
        raise Bpi2400ModelFitError(f"CVRMSE = {cvrmse:0.1%}, which is greater than 20%")
    return best_model
