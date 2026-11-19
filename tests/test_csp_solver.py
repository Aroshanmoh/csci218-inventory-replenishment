"""Our CSP solver must reach the same lexicographic optimum as HiGHS and brute force."""

import random

import pytest

from conftest import brute_force
from src.csp_solver import solve_csp
from src.instances import make_instance
from src.optimizer import optimize_orders
from test_optimizer import base_product, tiny_products

CONFIGS = {
    "full": {},
    "no_bound": {"branch_and_bound": False},
    "no_forward_checking": {"forward_checking": False},
    "no_dominance": {"dominance": False},
    "input_order": {"var_order": "input"},
}


def key(result):
    s = result["summary"]
    return s["priority_weighted_shortage"], s["total_excess_inventory"], s["total_purchase_cost"]


@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("seed", range(25))
def test_every_configuration_matches_brute_force(seed, config):
    rng = random.Random(seed)
    products = tiny_products(rng)
    base = sum(p["current_stock"] + p["incoming_stock"] for p in products)
    budget = rng.choice([1500, 3000, 6000])
    capacity = base + rng.randint(50, 300)
    result = solve_csp(products, budget, capacity, 30, **CONFIGS[config])
    assert result["status"] == "Optimal"
    expected = brute_force(products, budget, capacity, 30)
    got = key(result)
    assert got[0] == pytest.approx(expected[0], abs=1e-6)
    assert got[1] == pytest.approx(expected[1], abs=1e-6)
    assert got[2] == pytest.approx(expected[2], abs=1e-6)


@pytest.mark.parametrize("seed", range(15))
def test_matches_highs_on_larger_instances(seed):
    inst = make_instance(15, 500 + seed)
    cfg = inst.config
    rows = inst.inventory.to_dict("records")
    ours = solve_csp(rows, cfg["purchasing_budget"], cfg["warehouse_capacity"], 30)
    highs = optimize_orders(rows, cfg["purchasing_budget"], cfg["warehouse_capacity"], 30)
    assert ours["status"] == "Optimal"
    hs = highs["summary"]
    assert key(ours)[0] == pytest.approx(hs["priority_weighted_shortage"], abs=1e-5)
    assert key(ours)[1] == pytest.approx(hs["total_excess_inventory"], abs=1e-6)
    assert key(ours)[2] == pytest.approx(hs["total_purchase_cost"], abs=1e-4)


def test_bound_prunes_and_reduces_nodes():
    inst = make_instance(10, 7)
    cfg = inst.config
    rows = inst.inventory.to_dict("records")
    full = solve_csp(rows, cfg["purchasing_budget"], cfg["warehouse_capacity"], 30)
    plain = solve_csp(rows, cfg["purchasing_budget"], cfg["warehouse_capacity"], 30,
                      branch_and_bound=False, max_nodes=200_000)
    assert full["stats"].pruned_by_bound > 0
    assert full["stats"].nodes < plain["stats"].nodes


def test_node_limit_reports_status():
    inst = make_instance(30, 3)
    cfg = inst.config
    result = solve_csp(inst.inventory.to_dict("records"), cfg["purchasing_budget"],
                       cfg["warehouse_capacity"], 30, branch_and_bound=False, max_nodes=1000)
    assert result["status"] == "NodeLimit"


def test_long_lead_items_flagged_for_next_cycle():
    result = optimize_orders([base_product(lead_time_days=45)], 10000, 1000, 30)
    row = result["recommendations"][0]
    assert row["order_quantity"] == 0
    assert row["next_cycle_order"] == 100
    assert "ORDER NOW FOR NEXT CYCLE" in row["explanation"]


def test_priority_only_mode_ignores_lead_time():
    fast = base_product(sku_id="FAST", lead_time_days=1)
    slow = base_product(sku_id="SLOW", lead_time_days=29)
    # Same priority, budget for one lot only: lead-aware mode must favour SLOW.
    lead = optimize_orders([fast, slow], 1000, 10000, 30, urgency_mode="priority_lead")
    orders = {r["sku"]: r["order_quantity"] for r in lead["recommendations"]}
    assert orders["SLOW"] == 100 and orders["FAST"] == 0
