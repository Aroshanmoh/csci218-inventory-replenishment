"""Repeatable scenario comparisons for budget, demand, and capacity changes."""

from __future__ import annotations

import math

import pandas as pd

from .baseline import baseline_replenishment
from .evaluation import compare_plans
from .optimizer import optimize_orders


def run_comparison(inventory, config):
    baseline = baseline_replenishment(
        inventory,
        config,
        planning_horizon_days=config["planning_horizon_days"],
    )
    optimized = optimize_orders(
        inventory.to_dict(orient="records") if hasattr(inventory, "to_dict") else inventory,
        budget=config["purchasing_budget"],
        warehouse_capacity=config["warehouse_capacity"],
        planning_horizon_days=config["planning_horizon_days"],
    )
    evaluation = compare_plans(
        inventory,
        baseline,
        optimized,
        config["planning_horizon_days"],
        config["purchasing_budget"],
    )
    return baseline, optimized, evaluation


def _scaled_inventory(inventory, demand_multiplier):
    try:
        multiplier = float(demand_multiplier)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Demand multiplier must be a finite positive number.") from error
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("Demand multiplier must be a finite positive number.")
    result = inventory.copy()
    result["expected_demand"] = result["expected_demand"].map(
        lambda value: int(math.ceil(float(value) * multiplier))
    )
    return result


def run_standard_scenarios(inventory, config):
    """Compare both methods across six repeatable operating scenarios."""
    current_stock = int(
        (inventory["current_stock"] + inventory["incoming_stock"]).sum()
    )
    reduced_capacity = max(
        current_stock,
        int(math.floor(config["warehouse_capacity"] * 0.9)),
    )
    cases = [
        ("Base case", inventory.copy(), dict(config)),
        ("Budget reduced by 30%", inventory.copy(), {
            **config,
            "purchasing_budget": round(config["purchasing_budget"] * 0.7, 2),
        }),
        ("Demand increased by 20%", _scaled_inventory(inventory, 1.2), dict(config)),
        ("Warehouse capacity reduced by 10%", inventory.copy(), {
            **config,
            "warehouse_capacity": reduced_capacity,
        }),
        ("Supplier lead times extended", inventory.copy(), {
            **config,
        }),
        ("Current stock reduced by 75%", inventory.copy(), dict(config)),
    ]
    horizon = int(config["planning_horizon_days"])
    cases[4][1]["lead_time_days"] = cases[4][1]["lead_time_days"].map(
        lambda value: int(value) + horizon
    )
    cases[5][1]["current_stock"] = cases[5][1]["current_stock"].map(
        lambda value: int(math.floor(float(value) * 0.25))
    )
    results = []
    for label, case_inventory, case_config in cases:
        _, _, compared = run_comparison(case_inventory, case_config)
        for method, evaluation in compared.items():
            results.append(
                {
                    "scenario": label,
                    "method": method,
                    **evaluation["metrics"],
                }
            )
    return pd.DataFrame(results)

