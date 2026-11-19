def calculate_available_inventory(current_stock, incoming_stock):
    """
    Calculate inventory that will be available before new replenishment.
    """
    return current_stock + incoming_stock


def calculate_projected_shortage(
    current_stock,
    incoming_stock,
    expected_demand,
    safety_stock
):
    """
    Calculate the number of units needed to satisfy
    expected demand while maintaining safety stock.
    """

    available_inventory = (
        current_stock + incoming_stock
    )

    shortage = (
        expected_demand
        + safety_stock
        - available_inventory
    )

    return max(0, shortage)


def calculate_stock_coverage(
    current_stock,
    incoming_stock,
    expected_demand
):
    """
    Calculate the proportion of expected demand
    covered by available inventory.
    """

    available_inventory = (
        current_stock + incoming_stock
    )

    if expected_demand == 0:
        return 1.0

    return available_inventory / expected_demand


def calculate_replenishment_risk(shortage, priority, lead_time_days, planning_horizon_days):
    """
    Calculate a simple replenishment-risk score.

    Higher shortage, priority and lead time increase urgency.
    """

    if planning_horizon_days <= 0:
        raise ValueError("planning_horizon_days must be positive")

    return shortage * priority * (1 + lead_time_days / planning_horizon_days)


def check_max_stock(
    current_stock,
    incoming_stock,
    order_quantity,
    max_stock
):
    """
    Check whether an order would exceed maximum stock.
    """

    final_stock = (
        current_stock
        + incoming_stock
        + order_quantity
    )

    return final_stock <= max_stock


def check_moq(order_quantity, moq):
    """
    Check whether the proposed order respects MOQ.
    """

    if order_quantity == 0:
        return True

    return order_quantity >= moq


def check_order_multiple(order_quantity, order_multiple):
    """
    Check whether the order quantity respects
    the supplier order multiple.
    """

    if order_quantity == 0:
        return True
    if order_multiple <= 0:
        return False

    return order_quantity % order_multiple == 0


def check_budget(order_quantity, unit_cost, available_budget):
    """
    Check whether a proposed order is within budget.
    """

    total_cost = order_quantity * unit_cost

    return total_cost <= available_budget
