"""Baseline validity, shared evaluation, data loading and end-to-end runs."""

import pytest

from src.baseline import baseline_replenishment
from src.data_loader import prepare_project_data, validate_inventory_data
from src.evaluation import evaluate_plan
from src.instances import make_instance
from src.scenarios import run_comparison


@pytest.mark.parametrize("seed", range(20))
def test_baseline_respects_constraints(seed):
    inst = make_instance(40, seed)
    cfg = inst.config
    plan = baseline_replenishment(inst.inventory, cfg, cfg["planning_horizon_days"])
    by_sku = {r["sku_id"]: r["order_quantity"] for r in plan["recommendations"]}
    spend = 0.0
    total = 0
    for p in inst.inventory.to_dict("records"):
        q = by_sku[p["sku_id"]]
        spend += q * p["unit_cost"]
        total += p["current_stock"] + p["incoming_stock"] + q
        if q:
            assert q >= p["moq"] and q % p["order_multiple"] == 0
            assert p["current_stock"] + p["incoming_stock"] + q <= p["max_stock"]
    assert spend <= cfg["purchasing_budget"] + 1e-6
    assert total <= cfg["warehouse_capacity"]


def test_evaluation_ignores_orders_after_horizon():
    inst = make_instance(10, 1)
    rows = inst.inventory.to_dict("records")
    rows[0]["lead_time_days"] = 60
    plan = {"recommendations": [{"sku_id": rows[0]["sku_id"], "order_quantity": 1000, "purchase_cost": 0}]}
    detail = evaluate_plan(rows, plan, 30, 1000)["details"][0]
    assert detail["projected_inventory"] == rows[0]["current_stock"] + rows[0]["incoming_stock"]


def test_sample_data_end_to_end(sample_paths):
    inventory, config = prepare_project_data(*sample_paths)
    *_, optimized, evaluation = run_comparison(inventory, config)
    assert optimized["status"] == "Optimal"
    opt = evaluation["Constraint Optimizer"]["metrics"]
    base = evaluation["Reorder-point baseline"]["metrics"]
    assert opt["planned_purchase_cost"] <= config["purchasing_budget"] + 1e-6
    assert opt["demand_fill_rate"] >= base["demand_fill_rate"]


def test_loader_rejects_fractional_stock(sample_paths):
    inventory, _ = prepare_project_data(*sample_paths)
    bad = inventory.copy()
    bad["current_stock"] = bad["current_stock"].astype(float)
    bad.loc[0, "current_stock"] = 1.5
    with pytest.raises(ValueError):
        validate_inventory_data(bad)
