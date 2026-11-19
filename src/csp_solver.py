"""Our own constraint-optimisation solver: backtracking + forward checking + branch and bound.

This solves exactly the same model as ``src/optimizer.py`` (which uses the
HiGHS MILP solver) so that the two can be compared and cross-validated.

Constraint Optimisation Problem (COP)
-------------------------------------
Variables   q_i, the order quantity for SKU i.
Domains     D_i = {0} U {k * multiple_i : k >= 1, k * multiple_i >= MOQ_i, <= U_i}
            where U_i = min(budget // cost_i, free capacity, max_stock_i - stock_i),
            and D_i = {0} if the lead time exceeds the horizon or the SKU is overstocked.
            (Unary constraints are therefore enforced by construction: node consistency.)
Constraints sum_i cost_i * q_i <= budget          (global, n-ary)
            sum_i q_i <= free warehouse capacity    (global, n-ary)
Objective   lexicographic minimum of
            (1) sum_i w_i * shortage_i,  w_i = priority_i * (1 + lead_i / H)
            (2) sum_i excess_i
            (3) sum_i cost_i * q_i

Search techniques (each can be switched off for the ablation study)
-------------------------------------------------------------------
* Backtracking: depth-first assignment of one variable at a time.
* Forward checking: after an assignment, every future domain is cut to values
  that still fit the remaining budget and capacity. Because domains are sorted
  and 0 is always feasible, a domain is simply a prefix, so this is O(1) per SKU.
* Branch and bound: a node is pruned when an optimistic (admissible) bound on
  its best completion cannot beat the incumbent. The bound on weighted shortage
  is the larger of two relaxations, each solved exactly by the fractional
  knapsack greedy rule: (a) drop the capacity constraint and integrality,
  (b) drop the budget constraint and integrality. Both under-estimate the
  true remaining shortage, so the bound is admissible and the search stays
  exact (the same role an admissible heuristic plays in A*).
* Dominance: a lot larger than the first lot covering the gap to target adds
  excess and cost without reducing shortage, so it can never be optimal and is
  removed from the domain before search.
* Variable ordering: "urgency" assigns SKUs with the most weighted shortage
  first (fail-first in spirit); "input" keeps file order.
* Value ordering: largest remaining lot first, which finds a strong incumbent
  on the first dive and makes the bound prune earlier.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .optimizer import Product, urgency_weight, validate_inputs

EPS = 1e-9


@dataclass
class SearchStats:
    nodes: int = 0
    pruned_by_bound: int = 0
    pruned_by_constraints: int = 0
    incumbents: int = 0
    status: str = "Optimal"
    runtime_s: float = 0.0


@dataclass
class _Var:
    product: Product
    base: int
    target: int
    weight: float
    domain: list[int]          # ascending, always starts with 0
    s0: int = field(init=False)  # shortage if nothing is ordered
    e0: int = field(init=False)  # excess if nothing is ordered (unavoidable)

    def __post_init__(self):
        self.s0 = max(0, self.target - self.base)
        self.e0 = max(0, self.base - self.target)

    def shortage(self, q):
        return max(0, self.target - self.base - q)

    def excess(self, q):
        return max(0, self.base + q - self.target)


def _build_variables(items, budget, free_capacity, horizon, use_dominance, urgency_mode):
    variables = []
    for p in items:
        base = p.current_stock + p.incoming_stock
        target = p.demand + p.safety_stock
        if p.max_inventory is not None:
            target = min(target, p.max_inventory)
        domain = [0]
        overstocked = p.max_inventory is not None and base > p.max_inventory
        if p.lead_time_days <= horizon and not overstocked:
            upper = min(math.floor(budget / p.unit_cost + EPS), free_capacity)
            if p.max_inventory is not None:
                upper = min(upper, p.max_inventory - base)
            first = math.ceil(p.moq / p.order_multiple) * p.order_multiple
            domain += list(range(first, upper + 1, p.order_multiple))
        var = _Var(p, base, target, urgency_weight(p, horizon, urgency_mode), domain)
        if use_dominance:
            # Keep values up to (and including) the first lot that covers the gap.
            gap = var.s0
            cut = next((i for i, q in enumerate(domain) if q >= gap), len(domain) - 1)
            var.domain = domain[: cut + 1]
        variables.append(var)
    return variables


def _relaxed_reduction(order, variables, max_q, limit, unit_cost):
    """Fractional knapsack: max weighted shortage removed with `limit` resource."""
    removed = 0.0
    for j in order:
        if j not in max_q:
            continue
        var = variables[j]
        reducible = min(var.s0, max_q[j])
        if reducible <= 0:
            continue
        cost_per_unit = unit_cost(var)
        take = min(reducible, limit / cost_per_unit)
        removed += take * var.weight
        limit -= take * cost_per_unit
        if limit <= EPS:
            break
    return removed


def solve_csp(
    products: Iterable[Product | Mapping[str, Any]],
    budget: float,
    warehouse_capacity: int,
    planning_horizon_days: int = 30,
    *,
    forward_checking: bool = True,
    branch_and_bound: bool = True,
    dominance: bool = True,
    var_order: str = "urgency",
    urgency_mode: str = "priority_lead",
    max_nodes: int = 5_000_000,
) -> dict[str, Any]:
    """Exact search for the lexicographic optimum; see module docstring."""
    start = time.perf_counter()
    horizon = int(planning_horizon_days)
    items = validate_inputs(products, budget, warehouse_capacity)
    budget = float(budget)
    total_base = sum(p.current_stock + p.incoming_stock for p in items)
    if total_base > warehouse_capacity:
        raise ValueError("Existing inventory exceeds warehouse capacity.")
    free_capacity = int(warehouse_capacity) - total_base

    variables = _build_variables(items, budget, free_capacity, horizon, dominance, urgency_mode)
    order = list(range(len(variables)))
    if var_order == "urgency":
        order.sort(key=lambda j: -variables[j].weight * variables[j].s0)
    elif var_order != "input":
        raise ValueError("var_order must be 'urgency' or 'input'")

    # Static ratio orders for the two fractional-knapsack relaxations.
    by_budget_ratio = sorted(order, key=lambda j: -variables[j].weight / variables[j].product.unit_cost)
    by_capacity_ratio = sorted(order, key=lambda j: -variables[j].weight)

    stats = SearchStats()
    best_key = (math.inf, math.inf, math.inf)
    best_assignment: dict[int, int] = {}
    assignment: dict[int, int] = {}
    e0_suffix = [0] * (len(order) + 1)
    for depth in range(len(order) - 1, -1, -1):
        e0_suffix[depth] = e0_suffix[depth + 1] + variables[order[depth]].e0

    def allowed_prefix(var, rb, rc):
        """Forward checking: largest domain value still consistent with resources."""
        limit = min(math.floor(rb / var.product.unit_cost + EPS), rc)
        lo, hi = 0, len(var.domain)
        while lo < hi:  # first index with value > limit
            mid = (lo + hi) // 2
            if var.domain[mid] <= limit:
                lo = mid + 1
            else:
                hi = mid
        return lo  # domain[:lo] is consistent (never empty: 0 always fits)

    def lower_bound(depth, rb, rc, ws, ex, cost):
        remaining = order[depth:]
        if forward_checking:
            max_q = {j: variables[j].domain[allowed_prefix(variables[j], rb, rc) - 1] for j in remaining}
        else:
            max_q = {j: variables[j].domain[-1] for j in remaining}
        total = sum(variables[j].weight * variables[j].s0 for j in remaining)
        by_budget = _relaxed_reduction(by_budget_ratio, variables, max_q, rb, lambda v: v.product.unit_cost)
        by_capacity = _relaxed_reduction(by_capacity_ratio, variables, max_q, rc, lambda v: 1.0)
        ws_lb = ws + max(0.0, total - min(by_budget, by_capacity))
        return ws_lb, ex + e0_suffix[depth], cost

    def better(a, b):
        if a[0] < b[0] - 1e-7:
            return True
        if a[0] > b[0] + 1e-7:
            return False
        if a[1] != b[1]:
            return a[1] < b[1]
        return a[2] < b[2] - 1e-7

    def search(depth, rb, rc, ws, ex, cost):
        nonlocal best_key, best_assignment
        if stats.nodes >= max_nodes:
            stats.status = "NodeLimit"
            return
        if depth == len(order):
            key = (ws, ex, cost)
            if better(key, best_key):
                best_key, best_assignment = key, dict(assignment)
                stats.incumbents += 1
            return
        if branch_and_bound and best_key[0] < math.inf:
            if not better(lower_bound(depth, rb, rc, ws, ex, cost), best_key):
                stats.pruned_by_bound += 1
                return
        j = order[depth]
        var = variables[j]
        values = var.domain[: allowed_prefix(var, rb, rc)] if forward_checking else var.domain
        for q in reversed(values):  # value ordering: largest lot first
            stats.nodes += 1
            spend = q * var.product.unit_cost
            if not forward_checking and (spend > rb + EPS or q > rc):
                stats.pruned_by_constraints += 1
                continue
            assignment[j] = q
            search(depth + 1, rb - spend, rc - q,
                   ws + var.weight * var.shortage(q), ex + var.excess(q), cost + spend)
            del assignment[j]
            if stats.status == "NodeLimit":
                return

    search(0, budget, free_capacity, 0.0, 0, 0.0)
    stats.runtime_s = time.perf_counter() - start

    recommendations = []
    for j, var in enumerate(variables):
        q = best_assignment.get(j, 0)
        recommendations.append({
            "sku": var.product.sku, "sku_id": var.product.sku,
            "product_name": var.product.product_name,
            "order_quantity": q, "purchase_cost": q * var.product.unit_cost,
        })
    return {
        "status": stats.status,
        "recommendations": recommendations,
        "summary": {
            "priority_weighted_shortage": best_key[0],
            "total_excess_inventory": best_key[1],
            "total_purchase_cost": best_key[2],
        },
        "stats": stats,
    }
