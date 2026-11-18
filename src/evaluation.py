"""Shared evaluation definitions for Member 2 and Member 3 plans."""

from __future__ import annotations

from collections.abc import Mapping

from .baseline import allocate_stock


def _rows(inventory):
    return (
        inventory.to_dict(orient="records")
        if hasattr(inventory, "to_dict")
        else [dict(product) for product in inventory]
    )


def evaluate_plan(inventory, plan, planning_horizon_days, budget):
    """Score a plan with Member 3's allocation logic and common target metrics."""
    rows = _rows(inventory)
    recommendation_rows = plan.get("recommendations", [])
    recommendations = {}
    for row in recommendation_rows:
        sku = str(row.get("sku_id", row.get("sku", ""))).strip().upper()
        if not sku:
            raise ValueError("Every plan recommendation must include a SKU identifier.")
        if sku in recommendations:
            raise ValueError(f"Duplicate recommendation for SKU: {sku}")
        recommendations[sku] = row
    orders = {
        sku: int(float(row.get("order_quantity", 0) or 0))
        for sku, row in recommendations.items()
    }
    allocations = allocate_stock(
        rows,
        orders=orders,
        planning_days=planning_horizon_days,
    )
    allocation_by_sku = {
        str(row["sku_id"]).strip().upper(): row
        for row in allocations
    }

    details = []
    total_demand = 0
    total_fulfilled = 0
    total_shortage = 0
    total_excess = 0
    total_units = 0
    total_cost = 0.0
    projected_total = 0
    weighted_shortage = 0.0

    for product in rows:
        sku = str(product.get("sku_id", product.get("sku", ""))).strip().upper()
        rec: Mapping = recommendations.get(sku, {})
        allocation: Mapping = allocation_by_sku.get(sku, {})
        current = int(float(product.get("current_stock", 0) or 0))
        incoming = int(float(product.get("incoming_stock", 0) or 0))
        demand = int(float(product.get("expected_demand", product.get("demand", 0)) or 0))
        safety = int(float(product.get("safety_stock", 0) or 0))
        lead = int(float(product.get("lead_time_days", 0) or 0))
        priority = int(float(product.get("priority", 3) or 3))
        unit_cost = float(product.get("unit_cost", 0) or 0)
        max_value = product.get("max_stock", product.get("max_inventory"))
        target = demand + safety
        if max_value is not None and str(max_value).strip() != "":
            target = min(target, int(float(max_value)))

        order = int(float(rec.get("order_quantity", 0) or 0))
        cost = float(
            rec.get("purchase_cost", rec.get("order_cost", order * unit_cost))
            or 0
        )
        order_arrives = lead <= planning_horizon_days
        in_horizon_inventory = current + incoming + (order if order_arrives else 0)
        fulfilled = int(float(allocation.get("allocated", min(demand, in_horizon_inventory))))
        unfilled = max(0, demand - fulfilled)
        shortage = max(0, target - in_horizon_inventory)
        excess = max(0, in_horizon_inventory - target)
        fill_rate = 1.0 if demand == 0 else fulfilled / demand

        total_demand += demand
        total_fulfilled += fulfilled
        total_shortage += shortage
        total_excess += excess
        total_units += order
        total_cost += cost
        projected_total += in_horizon_inventory
        weighted_shortage += (
            priority * (1 + lead / max(1, planning_horizon_days)) * shortage
        )
        details.append({
            "sku_id": sku,
            "product_name": product.get("product_name", sku),
            "priority": priority,
            "lead_time_days": lead,
            "order_quantity": order,
            "order_arrives_within_horizon": order_arrives,
            "projected_inventory": in_horizon_inventory,
            "target_inventory": target,
            "shortage_to_target": shortage,
            "unfilled_demand": unfilled,
            "fill_rate": fill_rate,
            "excess_inventory": excess,
            "purchase_cost": cost,
            "explanation": rec.get("explanation", rec.get("reason", "")),
        })

    return {
        "metrics": {
            "planned_order_units": total_units,
            "planned_purchase_cost": total_cost,
            "budget_remaining": max(0.0, float(budget) - total_cost),
            "budget_utilization": (
                0.0 if budget == 0 else total_cost / float(budget)
            ),
            "projected_inventory_in_horizon": projected_total,
            "shortage_to_target_units": total_shortage,
            "unfilled_demand_units": total_demand - total_fulfilled,
            "demand_fill_rate": (
                1.0 if total_demand == 0 else total_fulfilled / total_demand
            ),
            "excess_inventory_units": total_excess,
            "priority_weighted_shortage": weighted_shortage,
            "total_demand": total_demand,
            "sku_count": len(rows),
        },
        "details": details,
    }


def compare_plans(inventory, baseline, optimized, planning_horizon_days, budget):
    return {
        "Baseline": evaluate_plan(
            inventory, baseline, planning_horizon_days, budget
        ),
        "Constraint Optimizer": evaluate_plan(
            inventory, optimized, planning_horizon_days, budget
        ),
    }
