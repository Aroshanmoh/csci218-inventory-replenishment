def calculate_available_inventory(current_stock, incoming_stock):
  
    return current_stock + incoming_stock


def calculate_projected_shortage(
    current_stock,
    incoming_stock,
    expected_demand,
    safety_stock
):
   

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
    

    available_inventory = (
        current_stock + incoming_stock
    )

    if expected_demand == 0:
        return 1.0

    return available_inventory / expected_demand


def calculate_replenishment_risk(shortage, priority, lead_time_days, planning_horizon_days):
   

    if planning_horizon_days <= 0:
        raise ValueError("planning_horizon_days must be positive")

    return shortage * priority * (1 + lead_time_days / planning_horizon_days)


def check_max_stock(
    current_stock,
    incoming_stock,
    order_quantity,
    max_stock
):
    

    final_stock = (
        current_stock
        + incoming_stock
        + order_quantity
    )

    return final_stock <= max_stock


def check_moq(order_quantity, moq):
    

    if order_quantity == 0:
        return True

    return order_quantity >= moq


def check_order_multiple(order_quantity, order_multiple):
  
    if order_quantity == 0:
        return True
    if order_multiple <= 0:
        return False

    return order_quantity % order_multiple == 0


def check_budget(order_quantity, unit_cost, available_budget):
 

    total_cost = order_quantity * unit_cost

    return total_cost <= available_budget
