from pathlib import Path

import pandas as pd
import pytest

from src.data_loader import (
    prepare_project_data,
    validate_company_config,
    validate_inventory_data,
)
from src.baseline import baseline_replenishment

ROOT = Path(__file__).resolve().parents[1]


def load_sample():
    return prepare_project_data(
        ROOT / "data" / "inventory_data.csv",
        ROOT / "data" / "company_config.csv",
    )


def test_sample_data_loads_and_validates():
    inventory, config = load_sample()
    assert len(inventory) == 12
    assert config["purchasing_budget"] == 50000
    assert config["warehouse_capacity"] == 6500
    assert config["planning_horizon_days"] == 30


def test_duplicate_skus_are_rejected():
    inventory, _ = load_sample()
    duplicate = pd.concat([inventory, inventory.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate SKU"):
        validate_inventory_data(duplicate)


def test_negative_stock_is_rejected():
    inventory, _ = load_sample()
    inventory.loc[0, "current_stock"] = -1
    with pytest.raises(ValueError, match="cannot contain negative"):
        validate_inventory_data(inventory)


def test_zero_budget_is_valid_configuration():
    config = {
        "purchasing_budget": 0,
        "warehouse_capacity": 100,
        "planning_horizon_days": 30,
        "currency": "USD",
    }
    assert validate_company_config(config)


def test_baseline_never_places_order_that_arrives_after_horizon():
    inventory, config = load_sample()
    plan = baseline_replenishment(inventory, config)
    late = [
        row for row in plan["recommendations"]
        if row["lead_time_days"] > config["planning_horizon_days"]
    ]
    assert late
    assert all(row["order_quantity"] == 0 for row in late)
    assert all(row["purchase_cost"] == 0 for row in late)


def test_baseline_respects_budget_and_capacity():
    inventory, config = load_sample()
    plan = baseline_replenishment(inventory, config)
    assert plan["summary"]["total_spent"] <= config["purchasing_budget"] + 1e-8
    initial_stock = int((inventory["current_stock"] + inventory["incoming_stock"]).sum())
    assert initial_stock + plan["summary"]["total_units"] <= config["warehouse_capacity"]


def test_baseline_orders_respect_supplier_lots():
    inventory, config = load_sample()
    plan = baseline_replenishment(inventory, config)
    source = inventory.set_index("sku_id")
    for row in plan["recommendations"]:
        quantity = row["order_quantity"]
        product = source.loc[row["sku_id"]]
        if quantity:
            assert quantity >= int(product["moq"])
            assert quantity % int(product["order_multiple"]) == 0
            assert int(product["current_stock"] + product["incoming_stock"] + quantity) <= int(product["max_stock"])



def test_optimizer_respects_all_hard_constraints():
    pulp = pytest.importorskip("pulp")
    from src.optimizer import optimize_orders

    inventory, config = load_sample()
    solver = pulp.COIN_CMD(msg=False)
    if not solver.available():
        pytest.skip("CBC solver is not installed in this test environment.")

    result = optimize_orders(
        inventory.to_dict(orient="records"),
        budget=config["purchasing_budget"],
        warehouse_capacity=config["warehouse_capacity"],
        planning_horizon_days=config["planning_horizon_days"],
        solver=solver,
    )
    assert result["status"] == "Optimal"
    summary = result["summary"]
    assert summary["total_purchase_cost"] <= config["purchasing_budget"] + 1e-6
    initial_stock = int((inventory["current_stock"] + inventory["incoming_stock"]).sum())
    assert initial_stock + summary["total_order_units"] <= config["warehouse_capacity"]

    source = inventory.set_index("sku_id")
    for row in result["recommendations"]:
        product = source.loc[row["sku_id"]]
        quantity = row["order_quantity"]
        if quantity:
            assert row["arrives_within_horizon"]
            assert quantity >= int(product["moq"])
            assert quantity % int(product["order_multiple"]) == 0
            assert int(product["current_stock"] + product["incoming_stock"] + quantity) <= int(product["max_stock"])
