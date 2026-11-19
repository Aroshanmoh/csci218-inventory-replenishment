"""Seeded random instance generator for tests and experiments.

Every instance is fully determined by (n_skus, seed, tightness settings), so
any experiment can be reproduced exactly from the seed recorded in its CSV.
Parameter ranges mirror the bundled IT-distribution sample data
(storage, memory, monitors: unit costs $6.5-$290, MOQs 10-200).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

COST_CHOICES = (6.5, 18, 22, 28, 52, 55, 75, 95, 120, 180, 250, 290)
MULTIPLE_CHOICES = (5, 10, 25, 50)


@dataclass(frozen=True)
class Instance:
    inventory: pd.DataFrame
    config: dict
    seed: int


def random_inventory(n_skus: int, seed: int, max_lead_time: int = 45) -> pd.DataFrame:
    """Generate n_skus products with valid, internally consistent fields."""
    rng = random.Random(seed)
    rows = []
    for i in range(n_skus):
        multiple = rng.choice(MULTIPLE_CHOICES)
        moq = multiple * rng.randint(1, 4)
        demand = rng.randint(20, 400)
        safety = rng.randint(5, max(6, demand // 4))
        max_stock = demand + safety + rng.randint(moq, moq + 300)
        current = rng.randint(0, int(demand * 1.2))
        incoming = rng.choice((0, 0, 0, multiple, 2 * multiple))
        rows.append({
            "sku_id": f"SKU-{seed}-{i:04d}",
            "product_name": f"Product {i}",
            "current_stock": current,
            "incoming_stock": incoming,
            "expected_demand": demand,
            "unit_cost": rng.choice(COST_CHOICES),
            "moq": moq,
            "order_multiple": multiple,
            "lead_time_days": rng.randint(3, max_lead_time),
            "safety_stock": safety,
            "max_stock": max_stock,
            "priority": rng.randint(1, 5),
        })
    return pd.DataFrame(rows)


def needed_spend(inventory: pd.DataFrame) -> float:
    """Cost of topping every SKU up to its target (ignoring lot sizes)."""
    target = (inventory["expected_demand"] + inventory["safety_stock"]).clip(upper=inventory["max_stock"])
    gap = (target - inventory["current_stock"] - inventory["incoming_stock"]).clip(lower=0)
    return float((gap * inventory["unit_cost"]).sum())


def make_instance(
    n_skus: int,
    seed: int,
    budget_ratio: float = 0.6,
    capacity_slack: float = 0.5,
    horizon: int = 30,
    max_lead_time: int = 45,
) -> Instance:
    """Build an instance whose budget and capacity are genuinely binding.

    budget_ratio: budget as a fraction of the spend needed to reach every target.
    capacity_slack: free warehouse space as a fraction of the total units needed.
    """
    inventory = random_inventory(n_skus, seed, max_lead_time)
    base = int((inventory["current_stock"] + inventory["incoming_stock"]).sum())
    target = (inventory["expected_demand"] + inventory["safety_stock"]).clip(upper=inventory["max_stock"])
    units_needed = int((target - inventory["current_stock"] - inventory["incoming_stock"]).clip(lower=0).sum())
    config = {
        "purchasing_budget": round(max(1.0, needed_spend(inventory) * budget_ratio), 2),
        "warehouse_capacity": base + max(1, int(units_needed * capacity_slack)),
        "planning_horizon_days": horizon,
    }
    return Instance(inventory=inventory, config=config, seed=seed)
