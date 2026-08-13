# `logbook.json` Output Documentation

The `logbook.json` file is a comprehensive diagnostic report generated after each calibration run. It archives weather-normalized utility targets, baseline simulation results, and the step-by-step progress of the Genetic Algorithm (GA). This file is the primary resource for **calibration diagnostics, debugging, and post-processing analysis.**

---

## Units and Conventions

Unless otherwise noted, all energy consumption values reported in `logbook.json` are expressed in MMBtu.

---

## 1. `weather_normalization_results`

This section contains the energy consumption targets derived from the weather-normalization of actual utility bills. These values serve as the targets for the calibration process.

```json
"weather_normalization_results": {
  "<fuel_type>": {
    "calibration_type": "detailed",
    "model_type": "5-parameter",
    "cvrmse": 0.062,
    "consumption": {
      "baseload": 6.88,
      "heating": 3.23,
      "cooling": 0.54
    }
  },
  "... (truncated for brevity)"
}
```

* `fuel_type`: Utility fuel type (e.g., electricity, natural gas)
* `calibration_type`: Type of weather normalization method (e.g., detailed)
* `model_type`: Regression model used (e.g., 5-parameter, 3-parameter heating, or 3-parameter cooling)
* `cvrmse`: Coefficient of Variation of Root Mean Square Error, indicating goodness-of-fit
* `consumption.baseload`: Non-weather-dependent usage
* `consumption.heating`: Heating-related consumption
* `consumption.cooling`: Cooling-related consumption

---

## 2. `existing_home_results`

Contains simulation outputs for the original uncalibrated home model. Values are annual consumption estimates from the initial simulation.

```json
"existing_home_results": {
  "existing_home_sim_results": {
    "electricity": {
      "cooling": 0.876,
      "baseload": 11.019
    },
    "natural gas": {
      "heating": 92.936,
      "baseload": 9.38
    },
    "... (truncated for brevity)"
  }
}
```

---

## 3. `calibration_success`

Indicates whether the calibration process met predefined acceptance criteria. Acceptance criteria thresholds are configurable through the `acceptance_criteria` section of the calibration configuration YAML file. If custom thresholds are not provided, the default values defined in `default_calibration_config.yaml` are used.

```json
"calibration_success": false
```

* `true`: Calibration met predefined acceptance criteria
* `false`: Calibration did not converge to acceptable error thresholds

---

## 4. `calibration_results`

Contains detailed results for each generation of the genetic algorithm.

```json
"calibration_results": [
  {
    "gen": 0,
    "... (truncated for brevity)"
  }
]
```

### 4.1 Genetic Algorithm Metrics

* `gen`: Generation index
* `nevals`: Number of individuals evaluated
* `min`: Best fitness score in generation
* `avg`: Average fitness score across the generation population

#### Fitness Score

The fitness score represents the overall calibration objective that the genetic algorithm minimizes.

It is computed by aggregating bias error and absolute error across all fuel types and end uses into a single scalar value.

Each error metric is first transformed using a logarithmic scaling function before being penalized and aggregated. This transformation reduces the influence of extreme error values and improves the stability of the optimization process. The use of a logarithmic transformation prevents any single large error (for a specific fuel type or end use) from dominating the overall fitness score.

Lower fitness values indicate better agreement between simulated results and weather-normalized consumption.

### 4.2 Error Metrics

Calibration error metrics are calculated for each end-use category (`baseload`, `heating`, and `cooling`) based on the methodology defined in BPI-2400-2015 Section 3.2.3.A.

#### Bias Error

Measures the signed percentage deviation between weather-normalized consumption and simulation results. It is used to identify systematic bias, indicating whether the model tends to over- or under-predict energy use.

```json
"bias_error_<fuel_type>_<end_use>"
```

##### Formula

```text
bias_error = ((y - ŷ) / NAC) * 100
```

**Where:**

* `y`: Weather-normalized consumption target
* `ŷ`: Simulated consumption for the same end-use
* `NAC`: Normalized Annual Consumption

##### Interpretation

* **Positive (+) Value**: The simulation underpredicts consumption (`y > ŷ`).
* **Negative (-) Value**: The simulation overpredicts consumption (`y < ŷ`).
* Values closer to 0 indicate better calibration performance.

---

#### Absolute Error

Measures the absolute magnitude of the difference between target and simulated consumption, regardless of direction.

```json
"abs_error_<fuel_type>_<end_use>"
```

##### Formula

```text
abs_error = abs(y - ŷ)
```

**Where:**

* `y`: Weather-normalized consumption target
* `ŷ`: Simulated consumption

##### Interpretation

* Values are `>= 0`.
* Lower values indicate better agreement and higher precision.

---

### 4.3 `best_individual`

Contains the best-performing parameter set for the current generation.

```json
"best_individual": {
  "misc_load_multiplier": 0.75,
  "heating_setpoint_offset": 0,
  "... (truncated for brevity)"
}
```

---

### 4.4 `best_individual_sim_results`

Contains the simulation output generated by the best individual's parameters.

```json
"best_individual_sim_results": {
  "electricity": {
    "cooling": 0.45,
    "baseload": 8.809
  },
  "... (truncated for brevity)"
}
```

---

### 4.5 `diversity`

Represents the genetic variance of the population.

```json
"diversity": 0.6
```

* **High Diversity**: The algorithm is broadly exploring the parameter space.
* **Low Diversity**: The population is converging on a specific solution.

---

### 4.6 `parameter_choice_stats`

Tracks distribution statistics for each parameter across the generation population.

```json
"parameter_choice_stats": {
  "misc_load_multiplier": {
    "min": 0.75,
    "max": 2.0,
    "median": 1.0,
    "std": 0.49
  },
  "... (truncated for brevity)"
}
```

These statistics help diagnose parameter convergence and population diversity throughout the calibration process.

* Low standard deviation may indicate convergence toward a stable parameter value.
* High standard deviation may indicate continued exploration or weak parameter sensitivity.
* Narrow min/max ranges across generations may indicate parameter stabilization.

---

### 4.7 `simulation_result_stats`

Tracks simulation output variability across all individuals in the generation.

```json
"simulation_result_stats": {
  "natural_gas_heating": {
    "min": 47.9,
    "max": 165.1,
    "median": 95.1,
    "std": 34.1
  },
  "... (truncated for brevity)"
}
```

These statistics summarize the variability of simulated energy consumption across the generation population.

They can be used to evaluate:

* Sensitivity of simulation outputs to parameter variation
* Whether the search space remains broadly exploratory or is converging toward stable solutions
