import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    from openstudio_hpxml_calibration.calibrate import Calibrate

    return Calibrate, Path


@app.cell
def _(Path):
    repo_root = Path(__file__).resolve().parent
    list((repo_root / "test_hpxmls" / "ira_rebates").glob("*.xml"))
    list((repo_root / "test_hpxmls" / "real_homes").glob("*.xml"))
    repo_root / "test_hpxmls" / "ira_rebates" / "5_fuel_oil_fuel_furnace.xml"
    filename = repo_root / "test_hpxmls" / "real_homes" / "house21.xml"
    repo_root / "tests" / "data" / "house21_daily_results_timeseries.json"
    annual_json_results_path = repo_root / "tests" / "data" / "house_21_results_annual.json"
    return annual_json_results_path, filename


@app.cell
def _(Calibrate, filename):
    cal = Calibrate(filename)
    return (cal,)


@app.cell
def _(cal):
    normalized_bills_mbtu = cal.get_normalized_consumption_per_bill()
    return (normalized_bills_mbtu,)


@app.cell
def _(normalized_bills_mbtu):
    normalized_bills_mbtu.keys()


@app.cell
def _(normalized_bills_mbtu):
    normalized_bills_mbtu["electricity"]


@app.cell
def _(normalized_bills_mbtu):
    normalized_bills_mbtu["electricity"]["baseload"].sum().round(2)


@app.cell
def _(normalized_bills_mbtu):
    # Build annual normalized bill consumption dicts
    annual_normalized_bill_consumption = {}
    for bill_fuel_type, consumption in normalized_bills_mbtu.items():
        annual_normalized_bill_consumption[bill_fuel_type] = {}
        for end_use in ["heating", "cooling", "baseload"]:
            annual_normalized_bill_consumption[bill_fuel_type][end_use] = (
                consumption[end_use].sum().round(3)
            )
    return (annual_normalized_bill_consumption,)


@app.cell
def _(annual_normalized_bill_consumption):
    annual_normalized_bill_consumption.keys()


@app.cell
def _(annual_normalized_bill_consumption):
    annual_normalized_bill_consumption["electricity"]


@app.cell
def _():
    return


@app.cell
def _(annual_json_results_path, cal):
    annual_model_results_mbtu = cal.get_model_results(annual_json_results_path)
    return (annual_model_results_mbtu,)


@app.cell
def _(annual_model_results_mbtu):
    annual_model_results_mbtu.keys()


@app.cell
def _(annual_model_results_mbtu):
    annual_model_results_mbtu["electricity"]


@app.cell
def _():
    return


@app.cell
def _(annual_model_results_mbtu, annual_normalized_bill_consumption, cal):
    comparison = cal.compare_results(
        normalized_consumption=annual_normalized_bill_consumption,
        annual_model_results=annual_model_results_mbtu,
    )
    return (comparison,)


@app.cell
def _(comparison):
    comparison


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
