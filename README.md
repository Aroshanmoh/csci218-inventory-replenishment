# Inventory Replenishment Optimizer

CSCI218 group project comparing constraint-based inventory
replenishment with a traditional rule-based baseline.

## Features

- Validate inventory data.
- Optimize orders within budget and warehouse capacity.
- Respect minimum order quantities, order multiples, and stock limits.
- Consider product priority and supplier lead time.
- Compare purchasing plans and demand fill rates.
- Display recommendations through a Streamlit interface.

## Setup

Use Python 3.13, the version used during development.

Create a virtual environment:

python3 -m venv .venv

Activate it on macOS/Linux:

source .venv/bin/activate

Or on Windows PowerShell:

.venv\Scripts\Activate.ps1

Install dependencies:

python -m pip install -r requirements.txt

## Run the interface

From the project folder:

python -m streamlit run app.py

Upload data/inventory_data.csv, set the constraints, and run
the optimizer. Open the comparison page to view baseline results.

Returning to the setup page clears previous results, so run
the optimizer again after changing inputs.

## Run command-line comparisons

python main.py

Run the six predefined scenarios:

python main.py --scenarios

These commands save outputs in results/.
Add --no-save to print results without saving files.

## Project structure

- app.py: Streamlit interface
- visualizations.py: Charts and KPI cards
- main.py: Command-line comparisons
- src/: Data validation, optimizer, baseline, evaluation, and scenarios
- data/: Sample inventory and company settings
- PROJECT_REPORT.md: Academic report
- requirements.txt: Python dependencies

## Model assumptions

The optimizer uses PuLP with the HiGHS solver.

Incoming stock is assumed available within the planning horizon.
The optimizer places no new orders whose lead time exceeds that
horizon. The baseline may place future orders, but those orders
do not contribute to current-horizon demand fulfillment.

Priority and lead time contribute to a project-defined shortage
weight. This is a deterministic optimization model, not a trained
machine-learning model.

## Status

The sample interface flow and backend scenarios have been checked.
Final regression testing and report alignment remain outstanding.
