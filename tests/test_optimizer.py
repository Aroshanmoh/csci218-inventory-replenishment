"""Correctness tests for the HiGHS constraint-optimisation model."""

import random

import pytest

from conftest import brute_force, lexicographic_key
from src.instances import make_instance
from src.optimizer import optimize_orders


def tiny_products(rng, n=4):
    """Small domains so brute force stays fast (each SKU has ~2-15 values)."""
    products = []
    for i in range(n):
        multiple = rng.choice([5, 10, 25])
        moq = multiple * rng.randint(1, 3)
        demand = rng.randint(20, 120)
        safety = rng.randint(5, 30)
        products.append(dict(
            sku_id=f"S{i}", product_name=f"S{i}",
            current_stock=rng.randint(0, 80), incoming_stock=rng.choice([0, 0, 10, 20]),
            expected_demand=demand, unit_cost=rng.choice([6.5, 18, 28, 55, 95, 120]),
            moq=moq, order_multiple=multiple, lead_time_days=rng.randint(3, 40),
            safety_stock=safety, max_stock=demand + safety + rng.randint(20, 120),
            priority=rng.randint(1, 5),
        ))
    return products


@pytest.mark.parametrize("seed", range(60))
def test_matches_brute_force_optimum(seed):
    rng = random.Random(seed)
    products = tiny_products(rng)
    base = sum(p["current_stock"] + p["incoming_stock"] for p in products)
    budget = rng.choice([1500, 3000, 6000])
    capacity = base + rng.randint(50, 300)
    result = optimize_orders(products, budget, capacity, 30)
    quantities = [row["order_quantity"] for row in result["recommendations"]]
    got = lexicographic_key(products, quantities, 30)
    expected = brute_force(products, budget, capacity, 30)
    assert got[0] == pytest.approx(expected[0], abs=1e-6)
    assert got[1] == pytest.approx(expected[1], abs=1e-6)
    assert got[2] == pytest.approx(expected[2], abs=1e-6)


@pytest.mark.parametrize("seed", range(20))
def test_every_hard_constraint_holds(seed):
    inst = make_instance(40, seed)
    cfg = inst.config
    products = inst.inventory.to_dict("records")
    result = optimize_orders(products, cfg["purchasing_budget"], cfg["warehouse_capacity"], cfg["planning_horizon_days"])
    spend = 0.0
    total = 0
    for p, row in zip(products, result["recommendations"]):
        q = row["order_quantity"]
        spend += q * p["unit_cost"]
        total += p["current_stock"] + p["incoming_stock"] + q
        if q:
            assert q >= p["moq"], "MOQ violated"
            assert q % p["order_multiple"] == 0, "order multiple violated"
            assert p["current_stock"] + p["incoming_stock"] + q <= p["max_stock"], "max_stock violated"
            assert p["lead_time_days"] <= cfg["planning_horizon_days"]
    assert spend <= cfg["purchasing_budget"] + 1e-6, "budget violated"
    assert total <= cfg["warehouse_capacity"], "capacity violated"


def base_product(**overrides):
    product = dict(sku_id="A", product_name="A", current_stock=10, incoming_stock=0,
                   expected_demand=100, unit_cost=10, moq=20, order_multiple=10,
                   lead_time_days=5, safety_stock=10, max_stock=200, priority=3)
    product.update(overrides)
    return product


def test_zero_budget_orders_nothing():
    result = optimize_orders([base_product()], 0, 1000, 30)
    assert result["summary"]["total_order_units"] == 0


def test_lead_time_beyond_horizon_is_not_ordered():
    result = optimize_orders([base_product(lead_time_days=45)], 10000, 1000, 30)
    assert result["recommendations"][0]["order_quantity"] == 0


def test_existing_overstock_gets_no_order():
    result = optimize_orders([base_product(current_stock=250)], 10000, 1000, 30)
    assert result["recommendations"][0]["order_quantity"] == 0
    assert result["recommendations"][0]["is_existing_overstock"]


def test_existing_stock_over_capacity_is_rejected():
    with pytest.raises(ValueError, match="exceeding warehouse capacity"):
        optimize_orders([base_product(current_stock=150)], 10000, 100, 30)


def test_moq_larger_than_room_means_no_order():
    # Only 15 units of room below max_stock, but the MOQ is 20.
    result = optimize_orders([base_product(current_stock=185, expected_demand=300)], 10000, 1000, 30)
    assert result["recommendations"][0]["order_quantity"] == 0


def test_single_sku_orders_exact_gap_rounded_to_lot():
    # Gap to target = 100 + 10 - 10 = 100, already a multiple of 10 and >= MOQ.
    result = optimize_orders([base_product()], 10000, 1000, 30)
    assert result["recommendations"][0]["order_quantity"] == 100


def test_budget_goes_to_higher_priority_first():
    high = base_product(sku_id="HIGH", priority=5)
    low = base_product(sku_id="LOW", priority=1)
    result = optimize_orders([high, low], 1000, 10000, 30)  # enough for 100 units only
    orders = {row["sku"]: row["order_quantity"] for row in result["recommendations"]}
    assert orders["HIGH"] == 100 and orders["LOW"] == 0


@pytest.mark.parametrize("bad", [
    {"unit_cost": 0}, {"moq": 0}, {"order_multiple": 0}, {"priority": 6},
    {"current_stock": -1}, {"safety_stock": 300},
])
def test_invalid_input_is_rejected(bad):
    with pytest.raises(ValueError):
        optimize_orders([base_product(**bad)], 1000, 1000, 30)


def test_duplicate_skus_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        optimize_orders([base_product(), base_product()], 1000, 1000, 30)
