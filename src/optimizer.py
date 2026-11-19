"""Member 2's mixed-integer inventory optimizer, integrated with the project."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Optional



@dataclass(frozen=True)
class Product:
    sku: str
    current_stock: int
    demand: int
    unit_cost: float
    moq: int = 1
    order_multiple: int = 1
    lead_time_days: int = 0
    safety_stock: int = 0
    incoming_stock: int = 0
    priority: int = 3
    max_inventory: Optional[int] = None
    product_name: Optional[str] = None


INTEGER_FIELDS = (
    "current_stock", "demand", "moq", "order_multiple", "lead_time_days",
    "safety_stock", "incoming_stock", "priority", "max_inventory",
)


def _integer(value: Any, field: str, sku: str = "") -> int:
    """Accept finite whole numbers without silently truncating fractions."""
    prefix = f"{sku}: " if sku else ""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{prefix}{field} is required and cannot be blank")
    if isinstance(value, bool):
        raise ValueError(f"{prefix}{field} must be a finite integer")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{prefix}{field} must be a finite integer") from error
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{prefix}{field} must be a finite integer")
    return int(number)


def _finite_number(value: Any, field: str, sku: str = "") -> float:
    prefix = f"{sku}: " if sku else ""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{prefix}{field} is required and cannot be blank")
    if isinstance(value, bool):
        raise ValueError(f"{prefix}{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{prefix}{field} must be a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"{prefix}{field} must be a finite number")
    return number


def _to_product(raw: Product | Mapping[str, Any]) -> Product:
    if isinstance(raw, Product):
        sku_raw = raw.sku
        values = {
            "current_stock": raw.current_stock,
            "demand": raw.demand,
            "moq": raw.moq,
            "order_multiple": raw.order_multiple,
            "lead_time_days": raw.lead_time_days,
            "safety_stock": raw.safety_stock,
            "incoming_stock": raw.incoming_stock,
            "priority": raw.priority,
            "max_inventory": raw.max_inventory,
        }
        unit_cost_raw, product_name = raw.unit_cost, raw.product_name
    else:
        sku_raw = raw.get("sku_id", raw.get("sku", raw.get("product", "")))
        values = {
            "current_stock": raw.get("current_stock", raw.get("stock")),
            "demand": raw.get("expected_demand", raw.get("demand")),
            "moq": raw.get("moq", raw.get("minimum_order_quantity", 1)),
            "order_multiple": raw.get("order_multiple", 1),
            "lead_time_days": raw.get("lead_time_days", raw.get("lead_time", 0)),
            "safety_stock": raw.get("safety_stock", 0),
            "incoming_stock": raw.get("incoming_stock", 0),
            "priority": raw.get("priority", 3),
            "max_inventory": raw.get("max_stock", raw.get("max_inventory")),
        }
        unit_cost_raw = raw.get("unit_cost", raw.get("cost"))
        product_name = raw.get("product_name")

    if sku_raw is None or not str(sku_raw).strip():
        raise ValueError("Every product must have a non-empty sku_id")
    sku = str(sku_raw).strip().upper()
    parsed = {
        field: (
            None if field == "max_inventory" and value is None
            else _integer(value, field, sku)
        )
        for field, value in values.items()
    }
    unit_cost = _finite_number(unit_cost_raw, "unit_cost", sku)
    if product_name is not None and not str(product_name).strip():
        product_name = None
    return Product(
        sku=sku,
        unit_cost=unit_cost,
        product_name=str(product_name).strip() if product_name is not None else sku,
        **parsed,
    )


def validate_inputs(
    products: Iterable[Product | Mapping[str, Any]],
    budget: float,
    warehouse_capacity: int,
) -> list[Product]:
    budget = _finite_number(budget, "budget")
    warehouse_capacity = _integer(warehouse_capacity, "warehouse_capacity")
    if budget < 0:
        raise ValueError("budget cannot be negative")
    if warehouse_capacity < 0:
        raise ValueError("warehouse_capacity cannot be negative")

    items = [_to_product(product) for product in products]
    if not items:
        raise ValueError("At least one product is required")

    seen: set[str] = set()
    for product in items:
        if product.sku in seen:
            raise ValueError(f"Duplicate SKU: {product.sku}")
        seen.add(product.sku)

        for field in (
            "current_stock", "demand", "moq", "order_multiple",
            "lead_time_days", "safety_stock", "incoming_stock",
        ):
            if getattr(product, field) < 0:
                raise ValueError(f"{product.sku}: {field} cannot be negative")
        if product.unit_cost <= 0:
            raise ValueError(f"{product.sku}: unit_cost must be greater than zero")
        if product.moq < 1:
            raise ValueError(f"{product.sku}: moq must be at least 1")
        if product.order_multiple < 1:
            raise ValueError(f"{product.sku}: order_multiple must be at least 1")
        if not 1 <= product.priority <= 5:
            raise ValueError(f"{product.sku}: priority must be an integer from 1 to 5")
        if product.max_inventory is not None:
            if product.max_inventory < 1:
                raise ValueError(f"{product.sku}: max_stock must be positive")
            if product.safety_stock > product.max_inventory:
                raise ValueError(f"{product.sku}: safety_stock exceeds max_stock")
    return items


def optimize_orders(
    products: Iterable[Product | Mapping[str, Any]],
    budget: float,
    warehouse_capacity: int,
    planning_horizon_days: int = 30,
    solver: Optional[Any] = None,
) -> dict[str, Any]:
    """Minimize weighted target shortage, then excess, then purchase cost."""
    try:
        import pulp
    except ImportError as error:
        raise RuntimeError(
            "PuLP is required to run the optimizer. Install dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from error

    horizon = _integer(planning_horizon_days, "planning_horizon_days")
    if horizon <= 0:
        raise ValueError("planning_horizon_days must be positive")
    budget = _finite_number(budget, "budget")
    capacity = _integer(warehouse_capacity, "warehouse_capacity")
    items = validate_inputs(products, budget, capacity)

    base = {
        product.sku: product.current_stock + product.incoming_stock
        for product in items
    }
    total_base = sum(base.values())
    if total_base > capacity:
        raise ValueError(
            f"Existing inventory (current + incoming) totals {total_base} units, "
            f"exceeding warehouse capacity of {capacity} units. "
            "Resolve the existing capacity overage before running replenishment."
        )

    target = {
        product.sku: min(
            product.max_inventory
            if product.max_inventory is not None else math.inf,
            product.demand + product.safety_stock,
        )
        for product in items
    }
    arrives_within_horizon = {
        product.sku: product.lead_time_days <= horizon
        for product in items
    }

    try:
        import pulp
    except ImportError as error:
        raise ImportError(
            "The MILP optimizer requires PuLP and HiGHS. "
            "Install project dependencies with: python -m pip install -r requirements.txt"
        ) from error

    model = pulp.LpProblem("Inventory_Replenishment", pulp.LpMinimize)
    order: dict[str, pulp.LpVariable] = {}
    active: dict[str, pulp.LpVariable] = {}
    multiple_count: dict[str, pulp.LpVariable] = {}
    shortage: dict[str, pulp.LpVariable] = {}
    excess: dict[str, pulp.LpVariable] = {}
    capacity_for_orders = capacity - total_base

    for index, product in enumerate(items):
        sku = product.sku
        order[sku] = pulp.LpVariable(f"order_{index}", lowBound=0, cat="Integer")
        active[sku] = pulp.LpVariable(f"active_{index}", cat="Binary")
        multiple_count[sku] = pulp.LpVariable(
            f"order_multiple_count_{index}", lowBound=0, cat="Integer"
        )
        shortage[sku] = pulp.LpVariable(f"shortage_{index}", lowBound=0, cat="Integer")
        excess[sku] = pulp.LpVariable(f"excess_{index}", lowBound=0, cat="Integer")

        budget_bound = max(0, math.floor(budget / product.unit_cost + 1e-9))
        upper = min(budget_bound, capacity_for_orders)
        if product.max_inventory is not None:
            upper = min(upper, max(0, product.max_inventory - base[sku]))
        # The shared evaluation horizon counts only orders that can arrive in time.
        if not arrives_within_horizon[sku]:
            upper = 0

        # Every order is zero or a supplier multiple that is at least the MOQ.
        # MOQ is a lower bound, not an additive first order tranche.
        model += order[sku] == product.order_multiple * multiple_count[sku]
        model += order[sku] >= product.moq * active[sku]
        model += order[sku] <= upper * active[sku]

        horizon_inventory = base[sku] + (
            order[sku] if arrives_within_horizon[sku] else 0
        )
        model += horizon_inventory + shortage[sku] - excess[sku] == target[sku]

        # Existing overstock is accepted. It prevents further orders but is not
        # treated as invalid input or forced below the per-SKU maximum.
        if product.max_inventory is not None and base[sku] <= product.max_inventory:
            model += base[sku] + order[sku] <= product.max_inventory

    model += pulp.lpSum(product.unit_cost * order[product.sku] for product in items) <= budget
    model += pulp.lpSum(base[product.sku] + order[product.sku] for product in items) <= capacity

    active_solver = solver or pulp.COIN_CMD(msg=False)
    available = getattr(active_solver, "available", None)
    if callable(available) and not available():
        raise RuntimeError(
            "CBC solver is unavailable. Install the project requirements or add CBC to PATH."
        )

    def solve(stage: str) -> float:
        try:
            status_code = model.solve(active_solver)
        except Exception as error:
            raise RuntimeError(
                f"Could not run the CBC solver during the {stage} stage. "
                "Install the project requirements and CBC support."
            ) from error
        status = pulp.LpStatus.get(status_code, "Unknown")
        if status != "Optimal":
            raise RuntimeError(
                f"Optimization stage '{stage}' failed: {status}. "
                "Review warehouse capacity, budget, MOQ, order multiples, and max_stock."
            )
        return float(pulp.value(model.objective) or 0)

    urgency = {
        product.sku: product.priority * (1 + product.lead_time_days / horizon)
        for product in items
    }
    weighted_shortage = pulp.lpSum(
        urgency[product.sku] * shortage[product.sku]
        for product in items
    )
    model.setObjective(weighted_shortage)
    best_shortage = solve("weighted shortage")
    # A small tolerance avoids false infeasibility from floating-point solver
    # tolerances while preserving the first-stage optimum.
    model += weighted_shortage <= best_shortage + 1e-7

    total_excess = pulp.lpSum(excess[product.sku] for product in items)
    model.setObjective(total_excess)
    best_excess = solve("excess inventory")
    model += total_excess <= best_excess + 1e-7

    total_cost = pulp.lpSum(
        product.unit_cost * order[product.sku]
        for product in items
    )
    model.setObjective(total_cost)
    solve("purchase cost")

    recommendations = []
    for product in items:
        sku = product.sku
        quantity = int(round(pulp.value(order[sku]) or 0))
        in_horizon_quantity = quantity if arrives_within_horizon[sku] else 0
        projected = base[sku] + in_horizon_quantity
        remaining = int(round(pulp.value(shortage[sku]) or 0))
        excess_units = int(round(pulp.value(excess[sku]) or 0))
        fulfilled = min(product.demand, projected)
        is_overstock = (
            product.max_inventory is not None
            and base[sku] > product.max_inventory
        )

        if is_overstock:
            explanation = "Existing stock is already above max_stock; no additional order."
        elif not arrives_within_horizon[sku]:
            explanation = "Supplier lead time exceeds this horizon; no order is placed in this plan."
        elif quantity:
            explanation = "Order respects the MOQ, supplier multiple, budget, capacity, and max_stock."
        else:
            explanation = "No order is needed or a feasible order does not improve this horizon's plan."

        recommendations.append({
            "sku": sku,
            "sku_id": sku,
            "product_name": product.product_name or sku,
            "priority": product.priority,
            "lead_time_days": product.lead_time_days,
            "urgency_weight": urgency[sku],
            "order_quantity": quantity,
            "current_stock": product.current_stock,
            "incoming_stock": product.incoming_stock,
            "arrives_within_horizon": arrives_within_horizon[sku],
            "projected_inventory": projected,
            "projected_inventory_after_order_arrival": base[sku] + quantity,
            "target_inventory": target[sku],
            "remaining_shortage": remaining,
            "demand_shortfall": max(0, product.demand - fulfilled),
            "safety_stock_shortfall": max(
                0, product.safety_stock - max(0, projected - product.demand)
            ),
            "demand_fulfilled": fulfilled,
            "excess_inventory": excess_units,
            "is_existing_overstock": is_overstock,
            "unit_cost": product.unit_cost,
            "purchase_cost": quantity * product.unit_cost,
            "explanation": explanation,
        })

    total_units = sum(row["order_quantity"] for row in recommendations)
    total_spend = sum(row["purchase_cost"] for row in recommendations)
    total_demand = sum(product.demand for product in items)
    total_fulfilled = sum(row["demand_fulfilled"] for row in recommendations)
    return {
        "status": "Optimal",
        "recommendations": recommendations,
        "summary": {
            "total_order_units": total_units,
            "total_purchase_cost": total_spend,
            "budget": budget,
            "budget_remaining": budget - total_spend,
            "warehouse_capacity": capacity,
            "projected_total_inventory": sum(
                row["projected_inventory"] for row in recommendations
            ),
            "total_remaining_shortage": sum(
                row["remaining_shortage"] for row in recommendations
            ),
            "total_demand_shortfall": sum(
                row["demand_shortfall"] for row in recommendations
            ),
            "total_safety_stock_shortfall": sum(
                row["safety_stock_shortfall"] for row in recommendations
            ),
            "priority_weighted_shortage": best_shortage,
            "total_excess_inventory": best_excess,
            "demand_fill_rate": (
                1.0 if total_demand == 0 else total_fulfilled / total_demand
            ),
        },
    }
