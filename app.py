import streamlit as st
import pandas as pd
from visualizations import render_kpi_card, plot_budget_trend, plot_order_quantities, plot_baseline_comparison
from src.optimizer import optimize_orders
from src.baseline import baseline_replenishment, allocate_stock
from pathlib import Path
from src.data_loader import prepare_project_data, validate_inventory_data

st.set_page_config(page_title="AI Inventory Optimizer", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).resolve().parent

default_inventory, company_config = prepare_project_data(
    ROOT / "data" / "inventory_data.csv",
    ROOT / "data" / "company_config.csv",
)

st.markdown("""
<style>
    .stApp { background-color: #1A1A24 !important; }
    [data-testid="stSidebar"] { background-color: #22222B !important; border-right: none !important; min-width: 100px !important; max-width: 100px !important; }
    [data-testid="stSidebar"] div[role="radiogroup"] { align-items: center; gap: 1.5rem; margin-top: 20px; }
    [data-testid="stSidebar"] p { color: #F28D77 !important; font-size: 26px !important; text-align: center; }
    [data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child { display: none; }
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: #2A2A35 !important; border-radius: 8px !important; border: 1px solid #333344 !important; box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important; padding: 15px; }
    .stMarkdown p, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5 { color: #FFFFFF !important; }
    .block-container { padding-top: 2rem !important; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

if 'budget' not in st.session_state:
    st.session_state['budget'] = int(company_config['purchasing_budget'])

if 'capacity' not in st.session_state:
    st.session_state['capacity'] = int(company_config['warehouse_capacity'])

if 'horizon' not in st.session_state:
    st.session_state['horizon'] = int(company_config['planning_horizon_days'])
if 'results_df' not in st.session_state: st.session_state['results_df'] = None
if 'kpis' not in st.session_state: st.session_state['kpis'] = None
if 'raw_data' not in st.session_state: st.session_state['raw_data'] = None
if 'active_page' not in st.session_state: st.session_state['active_page'] = ":material/bar_chart:"

if 'jump_to_page' in st.session_state:
    st.session_state['active_page'] = st.session_state['jump_to_page']
    del st.session_state['jump_to_page']

page = st.sidebar.radio("", [
    ":material/bar_chart:",
    ":material/home:",
    ":material/compare_arrows:"
], key="active_page", label_visibility="collapsed")

if page == ":material/bar_chart:":
    st.session_state['results_df'] = None
    st.session_state['kpis'] = None
    st.session_state['raw_data'] = None

    st.markdown("### DATA INGESTION & SETUP")
    
    col1, col2 = st.columns([1.5, 1])
    with col1:
        with st.container(border=True):
            st.markdown("**Enter Product Data**")
            uploaded_file = st.file_uploader("Upload Master Inventory CSV", type=["csv"])
            
            if uploaded_file is not None:
                df = pd.read_csv(uploaded_file)
                st.dataframe(df, use_container_width=True, height=200)
            else:
                df = None
                st.info("Please upload a Master Inventory CSV file to proceed.")
            
    with col2:
        with st.container(border=True):
            st.markdown("**Enter Constraints**")
            st.session_state['budget'] = st.number_input("Purchasing Budget ($)", min_value=0, value=st.session_state['budget'], step=5000)
            st.session_state['capacity'] = st.number_input("Warehouse Capacity (Units)", min_value=0, value=st.session_state['capacity'], step=500)
            st.session_state['horizon'] = st.number_input(
                "Planning Horizon (Days)",
                min_value=1,
                value=st.session_state['horizon'],
                step=1,
            )
            st.selectbox("Safety Stock Policy", ["Conservative", "Standard", "Aggressive"], index=1, key="policy_choice")
            
    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("RUN AI OPTIMIZER", type="primary", use_container_width=True):
        if df is None:
            st.error("Please upload a CSV file before running the optimizer.")
        else:
            try:
                df = df.copy()
                validate_inventory_data(df)
                policy = st.session_state.get('policy_choice', 'Standard')
                
                if "safety_stock" in df.columns:
                    if policy == "Conservative":
                        df["safety_stock"] = (df["safety_stock"] * 1.5).astype(int)
                    elif policy == "Aggressive":
                        df["safety_stock"] = (df["safety_stock"] * 0.5).astype(int)

                validate_inventory_data(df)
                raw_products = df.to_dict(orient="records")
                
                opt_result = optimize_orders(
                    products=raw_products,
                    budget=float(st.session_state['budget']),
                    warehouse_capacity=int(st.session_state['capacity']),
                    planning_horizon_days=int(st.session_state['horizon']),
                )
                
                recs = opt_result["recommendations"]
                summary = opt_result["summary"]

                st.session_state['raw_data'] = df.copy()
                
                results_list = []
                for r in recs:
                    results_list.append({
                        "SKU": r["sku"],
                        "Order Qty": r["order_quantity"],
                        "Total Cost": r["purchase_cost"],
                        "Explanation": r["explanation"]
                    })
                    
                st.session_state['results_df'] = pd.DataFrame(results_list)
                st.session_state['kpis'] = {
                    "spent": summary["total_purchase_cost"],
                    "units": summary["total_order_units"],
                    "active_skus": len([x for x in results_list if x["Order Qty"] > 0]),
                    "utilization": (summary["total_purchase_cost"] / st.session_state['budget']) * 100 if st.session_state['budget'] > 0 else 0,
                    "fill_rate": summary["demand_fill_rate"] * 100,
                    "unmet_shortage": summary["total_remaining_shortage"]
                }
                
                st.session_state['jump_to_page'] = ":material/home:"
                st.rerun()
                
            except Exception as err:
                st.error(f"Optimization Failed: {err}")

elif page == ":material/home:":
    st.markdown("### RECOMMENDED PURCHASES")
    
    if st.session_state['results_df'] is None:
        st.warning("Please upload data and run the optimizer first.")
    else:
        kpis = st.session_state['kpis']
        res_df = st.session_state['results_df']
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: 
            render_kpi_card("BUDGET SPENT", f"${kpis['spent']:,.0f}", f"{kpis['utilization']:.1f}% OF LIMIT")
        with col2: 
            render_kpi_card("UNITS ORDERED", f"{kpis['units']:,}", "TOTAL REPLENISHMENT")
        with col3: 
            render_kpi_card("SKUS ACTIONED", f"{kpis['active_skus']}", "ITEMS RESTOCKED")
        with col4: 
            render_kpi_card("EST. FILL RATE", f"{kpis['fill_rate']:.1f}%", "PROJECTED SERVICE LEVEL")

        st.markdown("<br>", unsafe_allow_html=True)
        chart_col1, chart_col2 = st.columns([1.5, 1])
        filtered_df = res_df[res_df["Total Cost"] > 0]
        
        with chart_col1:
            with st.container(border=True):
                st.markdown("**BUDGET ALLOCATION TREND**")
                if not filtered_df.empty: 
                    st.plotly_chart(plot_budget_trend(filtered_df), use_container_width=True, config={'displayModeBar': False})

        with chart_col2:
            with st.container(border=True):
                st.markdown("**ORDER QUANTITIES (UNITS)**")
                if not filtered_df.empty: 
                    st.plotly_chart(plot_order_quantities(filtered_df), use_container_width=True, config={'displayModeBar': False})

        with st.container(border=True):
            st.markdown("**DETAILED ACTION PLAN**")
            styled_res = res_df.style.format({"Total Cost": "${:,.2f}"})
            st.dataframe(styled_res, use_container_width=True, hide_index=True)

elif page == ":material/compare_arrows:":
    st.markdown("### AI VS TRADITIONAL BASELINE")
    
    if st.session_state['results_df'] is None or st.session_state['raw_data'] is None:
        st.warning("Please run the optimizer first.")
    else:
        # Run Member 3's baseline replenishment engine
        config = {
            "purchasing_budget": st.session_state['budget'],
            "warehouse_capacity": st.session_state['capacity'],
            "planning_horizon_days": int(st.session_state['horizon']),
        }
        
        baseline_res = baseline_replenishment(st.session_state['raw_data'], config)

        baseline_summary = baseline_res["summary"]
        
        # Calculate baseline fill rate using Member 3's stock allocation function
        orders_dict = {r["sku_id"]: r["order_quantity"] for r in baseline_res["recommendations"]}
        allocations = allocate_stock(
            st.session_state['raw_data'],
            orders=orders_dict,
            planning_days=int(st.session_state['horizon']),
        )
        
        total_demand = sum(a["demand"] for a in allocations)
        total_allocated = sum(a["allocated"] for a in allocations)
        baseline_fill_rate = (total_allocated / total_demand * 100) if total_demand > 0 else 100.0
        
        ai_kpis = st.session_state['kpis']
        
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.markdown("**Constraint AI (Our System)**")
                st.metric("Total Budget Spent", f"${ai_kpis['spent']:,.0f}", f"Within Limit (${st.session_state['budget']:,})", delta_color="normal")
                st.metric("Shortage After Order", f"{ai_kpis['unmet_shortage']:,} Units", "Optimized", delta_color="normal")
                st.metric("Demand Fill Rate", f"{ai_kpis['fill_rate']:.1f}%", "High Service Level", delta_color="normal")
                
        with col2:
            with st.container(border=True):
                st.markdown("**Traditional Baseline**")
                st.metric("Total Budget Spent", f"${baseline_summary['total_spent']:,.0f}", f"Remaining: ${baseline_summary['budget_left']:,.0f}", delta_color="off")
                st.metric("Shortage After Order", f"{baseline_summary['unmet_shortage']:,} Units", "Unmet Target Stock", delta_color="inverse")
                st.metric("Demand Fill Rate", f"{baseline_fill_rate:.1f}%", "Baseline Allocation", delta_color="off")
                
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("**Performance Comparison Chart**")
            ai_efficiency = (ai_kpis['spent'] / st.session_state['budget'] * 100) if st.session_state['budget'] > 0 else 0
            base_efficiency = (baseline_summary['total_spent'] / st.session_state['budget'] * 100) if st.session_state['budget'] > 0 else 0
            
            fig_comp = plot_baseline_comparison(
                ai_metrics={"fill_rate": ai_kpis['fill_rate'], "budget_efficiency": ai_efficiency},
                baseline_metrics={"fill_rate": baseline_fill_rate, "budget_efficiency": base_efficiency}
            )
            st.plotly_chart(fig_comp, use_container_width=True, config={'displayModeBar': False})