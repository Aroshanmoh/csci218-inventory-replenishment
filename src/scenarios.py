"""Repeatable what-if scenarios on the bundled dataset, for all three methods.

Each scenario changes one factor so its effect can be attributed. The two
scenarios that were uninformative in the first version are redesigned:
  * capacity: the original -10% never bound (6,500 -> 5,850 vs ~4,100 used),
    so the tight case now leaves free space for only half the units needed;
  * lead time: adding the full horizon to every lead time made every SKU
    unorderable, so lead times are now extended by 10 days, which pushes
    some (not all) SKUs past the horizon.
"""

from __future__ import annotations

import math

import pandas as pd

from .baseline import baseline_replenishment, greedy_replenishment
from .evaluation import compare_plans
from .optimizer import optimize_orders


def run_comparison(inventory, config):
    """Plan with all three methods and score them with the same evaluation."""
    horizon = config["planning_horizon_days"]
    baseline = baseline_replenishment(inventory, config, planning_horizon_days=horizon)
    greedy = greedy_replenishment(inventory, config, planning_horizon_days=horizon)
    optimized = optimize_orders(
        inventory.to_dict(orient="records") if hasattr(inventory, "to_dict") else inventory,
        budget=config["purchasing_budget"],
        warehouse_capacity=config["warehouse_capacity"],
        planning_horizon_days=horizon,
    )
    evaluation = compare_plans(
        inventory, baseline, optimized, horizon, config["purchasing_budget"], greedy=greedy
    )
    return baseline, greedy, optimized, evaluation


def _units_needed(inventory):
    target = (inventory["expected_demand"] + inventory["safety_stock"]).clip(upper=inventory["max_stock"])
    return int((target - inventory["current_stock"] - inventory["incoming_stock"]).clip(lower=0).sum())


def standard_cases(inventory, config):
    base_units = int((inventory["current_stock"] + inventory["incoming_stock"]).sum())
    demand_up = inventory.copy()
    demand_up["expected_demand"] = demand_up["expected_demand"].map(lambda v: int(math.ceil(v * 1.2)))
    lead_up = inventory.copy()
    lead_up["lead_time_days"] = lead_up["lead_time_days"] + 10
    stock_down = inventory.copy()
    stock_down["current_stock"] = stock_down["current_stock"].map(lambda v: int(math.floor(v * 0.25)))
    return [
        ("Base case", inventory.copy(), dict(config)),
        ("Budget reduced by 30%", inventory.copy(),
         {**config, "purchasing_budget": round(config["purchasing_budget"] * 0.7, 2)}),
        ("Demand increased by 20%", demand_up, dict(config)),
        ("Tight warehouse (room for 50% of needed units)", inventory.copy(),
         {**config, "warehouse_capacity": base_units + _units_needed(inventory) // 2}),
        ("Lead times +10 days", lead_up, dict(config)),
        ("Current stock reduced by 75%", stock_down, dict(config)),
    ]


def run_standard_scenarios(inventory, config):
    """Compare all three methods across six single-factor scenarios."""
    results = []
    for label, case_inventory, case_config in standard_cases(inventory, config):
        *_, compared = run_comparison(case_inventory, case_config)
        for method, evaluation in compared.items():
            results.append({"scenario": label, "method": method, **evaluation["metrics"]})
    return pd.DataFrame(results)
