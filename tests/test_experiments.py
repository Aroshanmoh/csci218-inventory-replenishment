from pathlib import Path

import pandas as pd
import pytest

from src.experiments import (
    generate_experiment_scenarios,
    run_experiments,
    summarize_experiments,
)


def test_scenarios_are_reproducible_and_within_bounds():
    first = generate_experiment_scenarios(n_scenarios=30, seed=42)
    second = generate_experiment_scenarios(n_scenarios=30, seed=42)
    assert first == second
    assert len(first) == 30
    assert all(0.8 <= row["demand_multiplier"] <= 1.2 for row in first)
    assert all(0.8 <= row["budget_multiplier"] <= 1.2 for row in first)


def test_scenario_generator_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        generate_experiment_scenarios(n_scenarios=0)
    with pytest.raises(ValueError):
        generate_experiment_scenarios(minimum_multiplier=0)
    with pytest.raises(ValueError):
        generate_experiment_scenarios(minimum_multiplier=1.2, maximum_multiplier=0.8)


def test_experiment_runner_uses_same_scenarios_for_both_methods(monkeypatch, tmp_path):
    import src.experiments as module

    inventory = pd.DataFrame({
        "sku_id": ["A"],
        "product_name": ["Sample"],
        "current_stock": [10],
        "incoming_stock": [0],
        "expected_demand": [20],
        "unit_cost": [2.0],
        "moq": [1],
        "order_multiple": [1],
        "lead_time_days": [2],
        "safety_stock": [2],
        "max_stock": [100],
        "priority": [3],
    })
    config = {
        "purchasing_budget": 100.0,
        "warehouse_capacity": 100,
        "planning_horizon_days": 30,
        "currency": "USD",
    }

    calls = []

    def fake_baseline(frame, cfg, planning_horizon_days=None):
        calls.append(("baseline", int(frame.iloc[0]["expected_demand"]), cfg["purchasing_budget"]))
        return {"recommendations": [{"sku_id": "A", "order_quantity": 1, "purchase_cost": 2.0}]}

    def fake_optimizer(records, budget, warehouse_capacity, planning_horizon_days):
        calls.append(("optimizer", int(records[0]["expected_demand"]), budget))
        return {"status": "Optimal", "recommendations": [{"sku_id": "A", "order_quantity": 1, "purchase_cost": 2.0}]}

    def fake_compare(frame, baseline, optimized, horizon, budget):
        metric = {
            "planned_order_units": 1,
            "planned_purchase_cost": 2.0,
            "budget_utilization": 0.02,
            "shortage_to_target_units": 0,
            "unfilled_demand_units": 0,
            "demand_fill_rate": 1.0,
            "excess_inventory_units": 0,
            "priority_weighted_shortage": 0,
        }
        return {"Baseline": {"metrics": metric}, "Constraint Optimizer": {"metrics": metric}}

    monkeypatch.setattr(module, "baseline_replenishment", fake_baseline)
    monkeypatch.setattr(module, "optimize_orders", fake_optimizer)
    monkeypatch.setattr(module, "compare_plans", fake_compare)

    output = tmp_path / "experiment_results.csv"
    result = run_experiments(inventory, config, n_scenarios=3, seed=42, output_path=output)

    assert len(result) == 6
    assert set(result["method"]) == {"Baseline", "Constraint Optimizer"}
    assert output.exists()
    assert len(calls) == 6
    for i in range(0, len(calls), 2):
        assert calls[i][1:] == calls[i + 1][1:]


def test_summary_returns_descriptive_statistics():
    rows = []
    for method in ("Baseline", "Constraint Optimizer"):
        for value in (1.0, 2.0):
            row = {"method": method}
            row.update({metric: value for metric in (
                "planned_order_units", "planned_purchase_cost",
                "budget_utilization", "shortage_to_target_units",
                "unfilled_demand_units", "demand_fill_rate",
                "excess_inventory_units", "priority_weighted_shortage",
            )})
            rows.append(row)
    summary = summarize_experiments(pd.DataFrame(rows))
    assert len(summary) == 2
    assert "demand_fill_rate_mean" in summary.columns
    assert "planned_purchase_cost_std" in summary.columns
