

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import pandas as pd

from .baseline import baseline_replenishment
from .evaluation import compare_plans
from .optimizer import optimize_orders


METRICS = (
    "planned_order_units",
    "planned_purchase_cost",
    "budget_utilization",
    "shortage_to_target_units",
    "unfilled_demand_units",
    "demand_fill_rate",
    "excess_inventory_units",
    "priority_weighted_shortage",
)


def generate_experiment_scenarios(
    n_scenarios: int = 30,
    seed: int = 42,
    minimum_multiplier: float = 0.8,
    maximum_multiplier: float = 1.2,
) -> list[dict[str, Any]]:

    if isinstance(n_scenarios, bool) or not isinstance(n_scenarios, int) or n_scenarios < 1:
        raise ValueError("n_scenarios must be a positive integer.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer.")
    try:
        low = float(minimum_multiplier)
        high = float(maximum_multiplier)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Scenario multiplier bounds must be finite numbers.") from exc
    if not math.isfinite(low) or not math.isfinite(high) or low <= 0 or high < low:
        raise ValueError("Multiplier bounds must be finite, positive, and maximum >= minimum.")

    rng = random.Random(seed)
    scenarios = []
    for index in range(1, n_scenarios + 1):
        scenarios.append({
            "scenario_id": index,
            "demand_multiplier": round(rng.uniform(low, high), 6),
            "budget_multiplier": round(rng.uniform(low, high), 6),
        })
    return scenarios


def _scenario_inventory(inventory: pd.DataFrame, demand_multiplier: float) -> pd.DataFrame:
    """Return a copy with scaled, whole-unit expected demand."""
    result = inventory.copy(deep=True)
    if "expected_demand" not in result.columns:
        raise ValueError("Inventory data must include expected_demand.")
    result["expected_demand"] = result["expected_demand"].map(
        lambda value: int(math.ceil(float(value) * demand_multiplier))
    )
    return result


def run_experiments(
    inventory: pd.DataFrame,
    config: dict[str, Any],
    n_scenarios: int = 30,
    seed: int = 42,
    minimum_multiplier: float = 0.8,
    maximum_multiplier: float = 1.2,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
  
    required_config = (
        "purchasing_budget",
        "warehouse_capacity",
        "planning_horizon_days",
    )
    missing = [key for key in required_config if key not in config]
    if missing:
        raise ValueError(f"Missing configuration settings: {', '.join(missing)}")

    base_budget = float(config["purchasing_budget"])
    capacity = int(config["warehouse_capacity"])
    horizon = int(config["planning_horizon_days"])
    if not math.isfinite(base_budget) or base_budget < 0:
        raise ValueError("purchasing_budget must be finite and non-negative.")
    if capacity < 0 or horizon <= 0:
        raise ValueError("warehouse_capacity must be non-negative and planning_horizon_days positive.")

    scenarios = generate_experiment_scenarios(
        n_scenarios=n_scenarios,
        seed=seed,
        minimum_multiplier=minimum_multiplier,
        maximum_multiplier=maximum_multiplier,
    )
    output_rows: list[dict[str, Any]] = []

    for scenario in scenarios:
        scenario_inventory = _scenario_inventory(
            inventory, scenario["demand_multiplier"]
        )
        scenario_config = {
            **config,
            "purchasing_budget": round(
                base_budget * scenario["budget_multiplier"], 2
            ),
            "warehouse_capacity": capacity,
            "planning_horizon_days": horizon,
        }

        baseline_plan = baseline_replenishment(
            scenario_inventory,
            scenario_config,
            planning_horizon_days=horizon,
        )
        optimizer_plan = optimize_orders(
            scenario_inventory.to_dict(orient="records"),
            budget=scenario_config["purchasing_budget"],
            warehouse_capacity=capacity,
            planning_horizon_days=horizon,
        )
        evaluations = compare_plans(
            scenario_inventory,
            baseline_plan,
            optimizer_plan,
            horizon,
            scenario_config["purchasing_budget"],
        )

        for method, evaluation in evaluations.items():
            row = {
                "scenario_id": scenario["scenario_id"],
                "seed": seed,
                "method": method,
                "demand_multiplier": scenario["demand_multiplier"],
                "budget_multiplier": scenario["budget_multiplier"],
                "scenario_budget": scenario_config["purchasing_budget"],
                "optimizer_status": optimizer_plan.get("status", "not_applicable"),
            }
            metrics = evaluation["metrics"]
            row.update({metric: metrics.get(metric) for metric in METRICS})
            output_rows.append(row)

    results = pd.DataFrame(output_rows)
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        results.to_csv(destination, index=False)
    return results


def summarize_experiments(results: pd.DataFrame) -> pd.DataFrame:
    
    required = {"method", *METRICS}
    missing = required.difference(results.columns)
    if missing:
        raise ValueError(f"Experiment results are missing columns: {sorted(missing)}")
    grouped = results.groupby("method")[list(METRICS)]
    summary = grouped.agg(["mean", "std", "min", "max"])
    summary.columns = [f"{metric}_{stat}" for metric, stat in summary.columns]
    return summary.reset_index()
