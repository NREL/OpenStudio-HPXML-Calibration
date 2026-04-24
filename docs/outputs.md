# `logbook.json` Output Documentation

The `logbook.json` file is generated after each calibration run. It records weather-normalized utility targets, baseline simulation results, genetic algorithm calibration progress across generations, and final calibration status. This file is intended for calibration diagnostics, debugging, and post-processing analysis.

## File Structure

```json
{
  "weather_normalization_results": {...},
  "existing_home_results": {...},
  "calibration_success": false,
  "calibration_results": [...]
}
```

---

## 1. `weather_normalization_results`

This section contains utility consumption targets derived from weather normalization.

### Structure

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
  }
}
```

### Fields

| Field | Description |
|--------|-------------|
| `fuel_type` | Utility fuel type (e.g., electricity, natural gas) |
| `calibration_type` | Type of weather normalization method (e.g., detailed) |
| `model_type` | Regression model used (e.g., 5-parameter, 3-parameter heating, or 3-parameter cooling) |
| `cvrmse` | Coefficient of Variation of Root Mean Square Error, indicating goodness-of-fit |
| `consumption.baseload` | Non-weather-dependent usage |
| `consumption.heating` | Heating-related consumption |
| `consumption.cooling` | Cooling-related consumption |

### Purpose

These values serve as the targets for the calibration process.

---

## 2. `existing_home_results`

Contains simulation outputs for the original uncalibrated home model. Values are annual consumption estimates from the initial simulation.

### Structure

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
    }
  }
}
```

### Purpose

Represents the baseline simulation before calibration begins.

Used to quantify the initial mismatch between simulation and normalized utility data.

---

## 3. `calibration_success`

```json
"calibration_success": false
```

### Description

Indicates whether the calibration process met predefined acceptance criteria.

| Value | Description |
|--------|----------|
| `true` | Calibration met predefined acceptance criteria |
| `false` | Calibration did not converge to acceptable error thresholds |

---

## 4. `calibration_results`

Contains detailed results for each generation of the genetic algorithm.

```json
"calibration_results": [
  {
    "gen": 0,
    ...
  }
]
```

Each object represents one generation.

---

### 4.1 Genetic Algorithm Metrics

| Field | Description |
|--------|-------------|
| `gen` | Generation index |
| `nevals` | Number of individuals evaluated |
| `min` | Best fitness score in generation |
| `avg` | Average fitness score across the generation population |

---

### 4.2 Error Metrics

#### Bias Error

```json
"bias_error_<fuel>_<end_use>"
```

Signed percentage error between simulation output and calibration target.

- Positive value represents overprediction
- Negative value represents underprediction

---

#### Absolute Error

```json
"abs_error_<fuel>_<end_use>"
```

Absolute difference between simulation output and target consumption.

These values are typically used in the fitness/objective function.

---

### 4.3 `best_individual`

Contains the best-performing parameter set for the current generation.

```json
"best_individual": {
  "misc_load_multiplier": 0.75,
  "heating_setpoint_offset": 0,
  ...
}
```

---

### 4.4 `best_individual_sim_results`

Simulation outputs corresponding to the best individual.

```json
"best_individual_sim_results": {
  "electricity": {
    "cooling": 0.45,
    "baseload": 8.809
  }
}
```

These results should be compared against:

- `weather_normalization_results`
- `existing_home_results`

---

### 4.5 `diversity`

```json
"diversity": 1.0
```

Measures population diversity within the genetic algorithm.

#### Interpretation

- Higher values represent broader parameter exploration
- Lower values represent population convergence

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
  }
}
```

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
  }
}
```
