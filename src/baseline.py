

from __future__ import annotations

from math import ceil, floor, isfinite
from typing import Any

from .rules import check_budget, check_max_stock, check_moq, check_order_multiple
from .optimizer import validate_inputs


def _rows(inventory):
    if hasattr(inventory, "to_dict"):
        return inventory.to_dict(orient="records")
    return [dict(product) for product in inventory]


def _number(product, field):
    value = product.get(field, 0)
    if value is None or value == "":
        return 0.0
    number = float(value)
    return number if isfinite(number) else 0.0


def baseline_replenishment(
    inventory, company_config, planning_horizon_days=None
) -> dict[str, Any]:

    products = _rows(inventory)
    try:
        budget_left = float(company_config["purchasing_budget"])
        warehouse_capacity = float(company_config["warehouse_capacity"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError(
         
        ) from error
    if not isfinite(budget_left) or not isfinite(warehouse_capacity):
        raise ValueError("Budget and warehouse capacity must be finite numbers.")
    horizon = (
        planning_horizon_days
        if planning_horizon_days is not None
        else _number(company_config, "planning_horizon_days")
    )
    if not isfinite(horizon) or horizon <= 0 or not float(horizon).is_integer():
        raise ValueError("planning_horizon_days must be a positive integer")
    validated = validate_inputs(products, budget_left, warehouse_capacity)
    # Keep the baseline and optimizer on identical SKU validation rules.
    products = [
        {
            "sku_id": item.sku,
            "product_name": item.product_name,
            "current_stock": item.current_stock,
            "incoming_stock": item.incoming_stock,
            "expected_demand": item.demand,
            "unit_cost": item.unit_cost,
            "moq": item.moq,
            "order_multiple": item.order_multiple,
            "lead_time_days": item.lead_time_days,
            "safety_stock": item.safety_stock,
            "max_stock": item.max_inventory,
            "priority": item.priority,
        }
        for item in validated
    ]
    current_total = sum(
        _number(product, "current_stock") + _number(product, "incoming_stock")
        for product in products
    )
    if current_total > warehouse_capacity:
        raise ValueError(
            f"Existing inventory (current + incoming) totals {current_total:g} units, "
            f"exceeding warehouse capacity of {warehouse_capacity:g} units."
        )
    warehouse_left = max(0, warehouse_capacity - current_total)
    products.sort(key=lambda product: -_number(product, "priority"))
    recommendations = []

    for product in products:
        sku = product.get("sku_id", "Unknown")
        stock = _number(product, "current_stock")
        incoming = _number(product, "incoming_stock")
        available = stock + incoming
        demand = _number(product, "expected_demand")
        safety = _number(product, "safety_stock")
        lead_time = _number(product, "lead_time_days")
        unit_cost = _number(product, "unit_cost")
        moq = _number(product, "moq")
        multiple = _number(product, "order_multiple")
        max_stock = _number(product, "max_stock")
        target = min(max_stock, demand + safety) if max_stock > 0 else demand + safety
        reorder_point = (
            safety + demand / horizon * lead_time if horizon > 0 else safety
        )
        needed = max(0, target - available) if available <= reorder_point else 0

        quantity = 0
        arrives = lead_time <= horizon
     
        if needed > 0 and multiple > 0 and unit_cost > 0 and arrives:
            wanted = ceil(max(needed, moq) / multiple) * multiple
            budget_limit = floor((budget_left + 1e-9) / unit_cost)
            sku_limit = max(0, max_stock - available) if max_stock > 0 else warehouse_left
            limit = min(budget_limit, warehouse_left, sku_limit)
            quantity = min(wanted, floor(limit / multiple) * multiple)
            valid = (
                check_moq(quantity, moq)
                and check_order_multiple(quantity, multiple)
                and (max_stock <= 0 or check_max_stock(stock, incoming, quantity, max_stock))
                and check_budget(quantity, unit_cost, budget_left)
            )
            if not valid:
                quantity = 0

        quantity = int(quantity)
        purchase_cost = quantity * unit_cost
        budget_left -= purchase_cost
        warehouse_left -= quantity
        in_horizon_quantity = quantity if arrives else 0
        projected = available + in_horizon_quantity
        shortage = max(0, target - projected)
        excess = max(0, projected - target)

        if not arrives and needed > 0:
            reason = "Supplier lead time exceeds the planning horizon; no order is placed in this plan."
        elif available > reorder_point:
            reason = "Available stock is above the reorder point."
        elif needed == 0:
            reason = "Available stock already meets the target level."
        elif quantity == 0:
            reason = "No valid order fits the budget, warehouse, MOQ, and stock limits."
        elif quantity < needed:
            reason = "A partial order was placed because budget or a stock limit was reached."
        else:
            reason = "Order brings stock toward the target level."

        recommendations.append(
            {
                "sku": sku,
                "sku_id": sku,
                "product_name": product.get("product_name", sku),
                "priority": _number(product, "priority"),
                "lead_time_days": lead_time,
                "arrives_within_horizon": arrives,
                "available_inventory": available,
                "reorder_point": reorder_point,
                "target_inventory": target,
                "order_quantity": quantity,
                "projected_inventory": projected,
                "projected_inventory_after_order_arrival": available + quantity,
                "purchase_cost": purchase_cost,
                "remaining_shortage": shortage,
                "excess_inventory": excess,
                "explanation": reason,
            }
        )

    return {
        "status": "Completed",
        "recommendations": recommendations,
        "summary": {
            "total_spent": sum(row["purchase_cost"] for row in recommendations),
            "budget_left": budget_left,
            "total_units": sum(row["order_quantity"] for row in recommendations),
            "unmet_shortage": sum(row["remaining_shortage"] for row in recommendations),
        },
    }


def allocate_stock(inventory, available_stock=None, orders=None, planning_days=None):
    """Member 3's priority allocation; orders arriving after the horizon are ignored."""
    products = _rows(inventory)
    products.sort(key=lambda product: -_number(product, "priority"))
    orders = orders or {}
    shared_pool = available_stock is not None
    stock_left = max(0, float(available_stock)) if shared_pool else 0
    results = []
    for product in products:
        sku = product.get("sku_id", "Unknown")
        demand = max(0, _number(product, "expected_demand"))
        ordered = _number({"value": orders.get(sku, 0)}, "value")
        if planning_days is not None and _number(product, "lead_time_days") > planning_days:
            ordered = 0
        if shared_pool:
            allocated = min(demand, stock_left)
            stock_left -= allocated
        else:
            stock = max(
                0,
                _number(product, "current_stock")
                + _number(product, "incoming_stock")
                + ordered,
            )
            allocated = min(demand, stock)
        results.append(
            {
                "sku_id": sku,
                "priority": _number(product, "priority"),
                "demand": demand,
                "allocated": allocated,
                "unfilled": demand - allocated,
                "fill_rate": 1.0 if demand == 0 else allocated / demand,
            }
        )
    return results

