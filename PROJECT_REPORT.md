# Inventory Replenishment Decision-Support System

## Abstract

This project builds a decision-support system for replenishment planning across multiple stock-keeping units (SKUs). Member 2's corrected mixed-integer optimizer is compared with Member 3's priority-based replenishment and stock-allocation baseline. Both plans use the same budget, warehouse-capacity, lead-time, shortage, and demand-fill definitions. The project includes validated inputs, a command-line run, an interactive scenario interface, and repeatable scenario comparisons. The sample contains 12 SKUs.

## 1. Problem and objectives

Replenishment decisions must balance customer availability with limited cash and storage. When several SKUs need stock at the same time, a product-by-product rule can spend the shared budget before the full portfolio is considered.

The system aims to:

1. Load and validate SKU-level inventory and company settings.
2. Calculate inventory coverage, shortage, and a transparent replenishment-risk heuristic.
3. Recommend integer order quantities that respect supplier MOQ and order multiples.
4. Enforce budget, warehouse-capacity, and maximum-stock limits.
5. Compare the optimized plan with a traditional rule-based baseline.
6. Let users change demand, stock, budget, capacity, and planning horizon to inspect scenarios.

## 2. System design

The application is divided into five layers:

| Layer | Responsibility |
|---|---|
| Data preparation | Load the inventory and company CSV files, validate required values, and calculate derived metrics. |
| Baseline | Reorder when available stock reaches a lead-time reorder point; process SKUs in priority order. |
| Optimizer | Choose an order portfolio with a mixed-integer linear model. |
| Evaluation | Score both methods with identical target-shortage and demand-fill-rate definitions. |
| Interface | Display plans, edit data, adjust scenario settings, and export recommendations. |

## 3. Data and validation

Each SKU includes current and incoming stock, expected demand, unit cost, MOQ, order multiple, lead time, safety stock, maximum stock, and a priority score from 1 to 5. Company-level settings include budget, warehouse capacity, planning horizon, and currency.

The loader checks required columns, blank or duplicate SKU identifiers, finite numeric values, whole-number fields, positive cost/MOQ/multiple/max-stock values, non-negative stock and demand fields, valid priority, and safety stock not exceeding maximum stock. Existing stock above maximum stock is retained as an overstock condition. An MOQ that cannot fit below maximum stock is also retained; the optimizer simply will not recommend an infeasible order.

Derived measures are:

- **Available inventory:** current stock plus incoming stock.
- **Projected shortage:** `max(0, expected demand + safety stock − available inventory)` before a new order.
- **Stock coverage:** available inventory divided by expected demand; values above 1 indicate more than one demand period of coverage.
- **Replenishment risk:** projected shortage × priority × `(1 + lead_time_days / planning_horizon_days)`. This is a project-defined heuristic, not an established industry measure.

## 4. Optimization method

For each SKU i, the model chooses an integer order quantity q_i. The first valid order lot is the smallest multiple of the supplier order multiple that is at least the MOQ. Allowed quantities are zero or that first lot plus further supplier multiples. For example, with an MOQ of 25 and an order multiple of 10, valid orders are 0, 30, 40, and so on.

The target inventory is:

```text
target_i = min(max_stock_i, expected_demand_i + safety_stock_i)
```

The replenishment target is `min(max_stock, expected_demand + safety_stock)`. A new order is eligible only when its supplier lead time is no longer than the selected planning horizon H; later orders do not count toward this plan's service results. Incoming stock is treated as available within the horizon because the input file does not contain arrival dates.

The model enforces:

- Total purchase cost does not exceed the purchasing budget.
- Existing stock plus incoming stock plus planned replenishment does not exceed warehouse capacity.
- An SKU's new replenishment does not exceed its maximum stock.
- Every nonzero order respects MOQ and the supplier's order multiple.
- Existing inventory above an SKU's maximum is accepted, but that SKU receives no new order.

The objective is lexicographic, solved in three stages:

1. Minimize shortage weighted by `priority × (1 + lead_time_days / planning_horizon_days)`.
2. Among the best shortage solutions, minimize units above target.
3. Among those solutions, minimize purchase cost.

Priority is a weighted factor, not a strict rank. The urgency formula is a modeling assumption selected for this project and needs industry-mentor review.

## 5. Baseline method

Member 3's baseline calculates a reorder point from safety stock, average demand over the planning horizon, and supplier lead time. If current plus incoming inventory is at or below that point, it orders toward the target inventory, subject to MOQ, supplier multiples, budget, warehouse capacity, and maximum stock. It processes higher-priority products first, so early purchases can use budget that might otherwise support a different portfolio. Its allocation function measures each SKU's demand coverage and ignores orders that arrive after the horizon.

The supplied baseline reference records a spend of $49,800, 445 ordered units, and 620 units below target stock for the provided dataset. The application recalculates the common comparison metrics from the actual plans when run.

## 6. Evaluation definitions

Both methods use the same evaluation function:

- **Shortage to target:** `max(0, target inventory − inventory available within the horizon)`.
- **Unfilled demand:** `demand − min(demand, horizon inventory)`, using Member 3's allocation function. The shortage-to-target metric separately measures whether the safety-stock target is met.
- **Demand fill rate:** total fulfilled demand divided by total demand; it is 1 when total demand is zero.
- **Planned order units and spend:** all recommended new orders, including their costs.
- **Budget utilization:** planned spend divided by the available budget.
- **Excess inventory:** units above the target level within the horizon.
- **Priority-weighted shortage:** shortage to target multiplied by the optimizer's priority/lead-time weight.

Orders whose lead time exceeds the planning horizon are not counted as available inventory for shortage or fill-rate calculations. The optimizer does not place these orders for the current horizon; the baseline may recommend a future order, but its cost is still included in spend and budget utilization.

The application and `python main.py` produce the comparison from the current dataset and settings. The command-line run exports SKU-level recommendations and a JSON summary. Running `python main.py --scenarios` also exports the six-case comparison as a CSV. No result is presented as mentor-validated.

## 7. Scenario analysis and interface

The interactive planner allows users to edit SKU data, set budget/capacity/horizon, and scale demand. The reusable scenario runner compares six repeatable cases: base conditions, a 30% budget reduction, a 20% demand increase, a 10% warehouse-capacity reduction (never below existing inventory), extended supplier lead times, and a 75% reduction in current stock. Each case runs both methods with the same metrics.

## 8. Assumptions and limitations

1. Demand and unit costs are deterministic for each scenario; the scenario runner is repeatable and uses fixed scenario changes rather than random sampling.
2. Incoming stock is assumed to arrive within the horizon; no inbound delivery dates were provided.
3. Lead-time urgency is represented by a simple project-defined weight.
4. The optimizer is a classical mixed-integer model, not a machine-learning system.
5. The sample dataset is suitable for a prototype demonstration, not a production purchasing decision.
6. Supplier price breaks, order cancellation, service-level targets, shelf-life, uncertain demand, and multiple warehouse locations are outside the current model.
7. The project notes request industry-mentor validation; the urgency formula and business assumptions remain unvalidated until that review occurs.

## 9. Conclusion

The completed prototype integrates the corrected Member 2 optimizer with Member 3's baseline and allocation logic, then scores both through one evaluation layer. It makes purchasing trade-offs visible across six repeatable scenarios. The comparison can show where portfolio optimization improves service, spend, or inventory for the chosen data and assumptions; no single approach is guaranteed to dominate on every metric.

