"""Interactive Streamlit interface for inventory replenishment scenarios."""

from __future__ import annotations

from pathlib import Path
import math

import pandas as pd
import streamlit as st

from src.baseline import baseline_replenishment
from src.data_loader import (
    load_company_config,
    load_inventory_data,
    validate_company_config,
    validate_inventory_data,
)
from src.evaluation import compare_plans
from src.optimizer import optimize_orders

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Inventory Replenishment Planner",
    page_icon="📦",
    layout="wide",
)
st.title("Inventory Replenishment Planner")
st.caption(
    "Compare a priority-based baseline with a constraint optimizer. "
    "Edit the inventory and settings to explore scenarios."
)


@st.cache_data
def _default_inventory():
    return load_inventory_data(ROOT / "data" / "inventory_data.csv")


@st.cache_data
def _default_config():
    return load_company_config(ROOT / "data" / "company_config.csv")


uploaded = st.sidebar.file_uploader("Upload an inventory CSV", type=["csv"])
try:
    raw_inventory = pd.read_csv(uploaded) if uploaded is not None else _default_inventory()
    default_config = dict(_default_config())
    validate_company_config(default_config)
except Exception as error:
    st.error(str(error))
    st.stop()

st.subheader("Inventory scenario")
st.write("Edit stock, demand, supplier, or priority values directly in the table.")
edited_inventory = st.data_editor(
    raw_inventory,
    num_rows="dynamic",
    hide_index=True,
    key="inventory_editor",
)

st.sidebar.subheader("Planning settings")
currency = default_config["currency"]
budget = st.sidebar.number_input(
    f"Purchasing budget ({currency})",
    min_value=0.0,
    value=float(default_config["purchasing_budget"]),
    step=1000.0,
)
capacity = st.sidebar.number_input(
    "Warehouse capacity (units)",
    min_value=0,
    value=int(default_config["warehouse_capacity"]),
    step=100,
)
horizon = st.sidebar.number_input(
    "Planning horizon (days)",
    min_value=1,
    value=int(default_config["planning_horizon_days"]),
    step=1,
)
demand_multiplier = st.sidebar.slider(
    "Demand scenario multiplier",
    min_value=0.5,
    max_value=2.0,
    value=1.0,
    step=0.05,
    help="Scale expected demand for a quick sensitivity scenario.",
)
run_button = st.sidebar.button("Compare replenishment plans", type="primary")

if run_button:
    try:
        scenario_inventory = edited_inventory.copy()
        scenario_inventory["expected_demand"] = scenario_inventory[
            "expected_demand"
        ].map(lambda value: int(math.ceil(float(value) * demand_multiplier)))
        validate_inventory_data(scenario_inventory)
        config = {
            **default_config,
            "purchasing_budget": float(budget),
            "warehouse_capacity": int(capacity),
            "planning_horizon_days": int(horizon),
        }
        validate_company_config(config)
        base_stock = int(
            (
                scenario_inventory["current_stock"]
                + scenario_inventory["incoming_stock"]
            ).sum()
        )
        if base_stock > config["warehouse_capacity"]:
            raise ValueError(
                f"Current plus incoming inventory is {base_stock:,} units, "
                f"above the selected warehouse capacity of {config['warehouse_capacity']:,}."
            )

        baseline = baseline_replenishment(
            scenario_inventory,
            config,
            planning_horizon_days=config["planning_horizon_days"],
        )
        optimized = optimize_orders(
            scenario_inventory.to_dict(orient="records"),
            budget=config["purchasing_budget"],
            warehouse_capacity=config["warehouse_capacity"],
            planning_horizon_days=config["planning_horizon_days"],
        )
        compared = compare_plans(
            scenario_inventory,
            baseline,
            optimized,
            config["planning_horizon_days"],
            config["purchasing_budget"],
        )
        st.subheader("Plan comparison")
        comparison = pd.DataFrame(
            {name: result["metrics"] for name, result in compared.items()}
        ).T
        display_names = {
            "planned_order_units": "Planned order units",
            "planned_purchase_cost": f"Planned spend ({currency})",
            "budget_remaining": f"Budget remaining ({currency})",
            "budget_utilization": "Budget utilization",
            "projected_inventory_in_horizon": "Inventory available in horizon",
            "shortage_to_target_units": "Units below target",
            "unfilled_demand_units": "Unfilled demand units",
            "demand_fill_rate": "Demand fill rate",
            "excess_inventory_units": "Units above target",
            "priority_weighted_shortage": "Priority-weighted shortage",
            "total_demand": "Total demand",
            "sku_count": "SKU count",
        }
        comparison = comparison.rename(index=display_names)
        st.dataframe(comparison, use_container_width=True)
        st.caption(
            "Both plans use the same target-shortage and fill-rate calculations. "
            "Orders with lead times beyond the selected horizon do not count as "
            "available inventory during that period."
        )

        st.subheader("SKU recommendations")
        optimized_detail = {
            row["sku_id"]: row
            for row in compared["Constraint Optimizer"]["details"]
        }
        baseline_order = {
            row["sku_id"]: row["order_quantity"]
            for row in baseline["recommendations"]
        }
        optimized_order = {
            row["sku_id"]: row["order_quantity"]
            for row in optimized["recommendations"]
        }
        recommendations = []
        for row in optimized["recommendations"]:
            sku = row["sku_id"]
            recommendations.append(
                {
                    "SKU": sku,
                    "Product": row["product_name"],
                    "Priority": row["priority"],
                    "Lead time (days)": row["lead_time_days"],
                    "Baseline order": baseline_order[sku],
                    "Optimizer order": optimized_order[sku],
                    "Inventory in horizon": optimized_detail[sku]["projected_inventory"],
                    "Target stock": optimized_detail[sku]["target_inventory"],
                    "Optimizer shortage": optimized_detail[sku]["shortage_to_target"],
                    "Optimizer fill rate": optimized_detail[sku]["fill_rate"],
                    f"Optimizer cost ({currency})": row["purchase_cost"],
                    "Reason": row["explanation"],
                }
            )
        recommendation_frame = pd.DataFrame(recommendations)
        st.dataframe(recommendation_frame, hide_index=True, use_container_width=True)
        spend_label = f"Planned spend ({currency})"
        chart_columns = st.columns(3)
        for column, metric, label in zip(
            chart_columns,
            [spend_label, "Units below target", "Demand fill rate"],
            ["Planned spend", "Units below target", "Demand fill rate"],
        ):
            with column:
                st.markdown(f"**{label}**")
                chart_data = pd.DataFrame(
                    {
                        label: [
                            comparison.loc["Baseline", metric],
                            comparison.loc["Constraint Optimizer", metric],
                        ]
                    },
                    index=["Baseline", "Optimizer"],
                )
                st.bar_chart(chart_data)
        st.download_button(
            "Download SKU recommendations",
            data=recommendation_frame.to_csv(index=False).encode("utf-8"),
            file_name="inventory_recommendations.csv",
            mime="text/csv",
        )
        with st.expander("Model assumptions"):
            st.markdown(
                """
                - This is a deterministic mixed-integer optimization model, not a trained machine-learning model.
                - Priority and supplier lead time form a project-defined shortage weight.
                - Incoming stock is assumed to arrive within the planning horizon because the input data has no incoming-order arrival dates.
                - New orders arriving after the planning horizon do not count as service inventory for that horizon.
                - Existing stock above a SKU's maximum is treated as overstock; the model does not add more units.
                """
            )
    except Exception as error:
        st.error(str(error))
else:
    st.info("Set your scenario, then choose **Compare replenishment plans**.")

