"""Shared test helpers: an exhaustive brute-force oracle for small instances."""

import itertools
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def target_of(p):
    return min(p["max_stock"], p["expected_demand"] + p["safety_stock"])


def lexicographic_key(products, quantities, horizon):
    """(weighted shortage, excess, cost): the optimizer's objective, scored directly."""
    weighted = excess = cost = 0.0
    for p, q in zip(products, quantities):
        arrives = p["lead_time_days"] <= horizon
        inv = p["current_stock"] + p["incoming_stock"] + (q if arrives else 0)
        t = target_of(p)
        weighted += p["priority"] * (1 + p["lead_time_days"] / horizon) * max(0, t - inv)
        excess += max(0, inv - t)
        cost += q * p["unit_cost"]
    return round(weighted, 6), excess, round(cost, 6)


def brute_force(products, budget, capacity, horizon):
    """Enumerate every valid order combination and return the best key."""
    base = sum(p["current_stock"] + p["incoming_stock"] for p in products)
    domains = []
    for p in products:
        values = [0]
        if p["lead_time_days"] <= horizon:
            upper = min(
                int(budget // p["unit_cost"]),
                capacity - base,
                p["max_stock"] - p["current_stock"] - p["incoming_stock"],
            )
            k = 1
            while p["order_multiple"] * k <= upper:
                q = p["order_multiple"] * k
                if q >= p["moq"]:
                    values.append(q)
                k += 1
        domains.append(values)
    best = None
    for combo in itertools.product(*domains):
        if sum(q * p["unit_cost"] for q, p in zip(combo, products)) > budget + 1e-9:
            continue
        if base + sum(combo) > capacity:
            continue
        key = lexicographic_key(products, combo, horizon)
        if best is None or key < best:
            best = key
    return best


@pytest.fixture
def sample_paths():
    return ROOT / "data" / "inventory_data.csv", ROOT / "data" / "company_config.csv"
