from collections.abc import Sequence
from typing import Callable
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


def three_parameter_cooling(
    x: Sequence[float],
    b1: float | np.floating,
    b2: float | np.floating,
    b3: float | np.floating,
) -> np.array:
    x_arr = np.array(x)
    return b1 + b2 * np.maximum(x_arr - b3, 0)


def three_parameter_heating(
    x: Sequence[float],
    b1: float | np.floating,
    b2: float | np.floating,
    b3: float | np.floating,
) -> np.array:
    x_arr = np.array(x)
    return b1 + b2 * np.minimum(x_arr - b3, 0)


def five_parameter(
    x: Sequence[float],
    b1: float | np.floating,
    b2: float | np.floating,
    b3: float | np.floating,
    b4: float | np.floating,
    b5: float | np.floating,
):
    x_arr = np.array(x)
    return b1 + b2 * np.minimum(x_arr - b4, 0) + b3 * np.maximum(x_arr - b5, 0)


def fit_model(func: Callable, bills_temps: pd.DataFrame) -> np.array:
    initial_guesses = [1.0, 1.0, 60.0]  # FIXME: make more general
    popt, pcov = curve_fit(
        func,
        bills_temps["avg_temp"].values,
        bills_temps["daily_consumption"].values,
        p0=initial_guesses,
    )
    return popt, pcov
