import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

def render_kpi_card(title: str, value: str, subtitle: str) -> None:
    html = f"""
    <div style="background-color: #2A2A35; border-radius: 8px; padding: 18px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border-top: 4px solid #F28D77; margin-bottom: 10px;">
        <div style="color: #A0A0B0; font-weight: 800; font-size: 11px; letter-spacing: 1px; text-transform: uppercase;">{title}</div>
        <div style="font-size: 28px; font-weight: 800; color: #FFFFFF; margin: 8px 0;">{value}</div>
        <div style="font-size: 11px; color: #8BD99B; font-weight: 600;">{subtitle}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def plot_budget_trend(df: pd.DataFrame) -> go.Figure:
    fig = px.line(df, x="SKU", y="Total Cost", markers=True)
    fig.update_traces(
        line_color="#2B2B36",
        marker=dict(color="#F28D77", size=10, line=dict(color="#FFFFFF", width=1))
    )
    fig.update_layout(
        template="plotly_dark",
        height=280,
        margin=dict(l=10, r=10, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis_title=None,
        yaxis_title="Total Cost ($)"
    )
    return fig

def plot_order_quantities(df: pd.DataFrame) -> go.Figure:
    fig = px.bar(df, x="SKU", y="Order Qty")
    fig.update_traces(marker_color="#8BD99B")
    fig.update_layout(
        template="plotly_dark",
        height=280,
        margin=dict(l=10, r=10, t=20, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis_title=None,
        yaxis_title="Units to Order"
    )
    return fig

def plot_baseline_comparison(ai_metrics: dict, baseline_metrics: dict, greedy_metrics: dict | None = None) -> go.Figure:
    categories = ["Fill Rate (%)", "Budget Utilization (%)"]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=categories,
        y=[
            ai_metrics["fill_rate"],
            ai_metrics["budget_efficiency"],
        ],
        name="Constraint Optimizer",
        marker_color="#8BD99B",
    ))

    fig.add_trace(go.Bar(
        x=categories,
        y=[
            baseline_metrics["fill_rate"],
            baseline_metrics["budget_efficiency"],
        ],
        name="Traditional Baseline",
        marker_color="#F28D77",
    ))

    if greedy_metrics is not None:
        fig.add_trace(go.Bar(
            x=categories,
            y=[
                greedy_metrics["fill_rate"],
                greedy_metrics["budget_efficiency"],
            ],
            name="Greedy Baseline",
            marker_color="#9B8AFB",
        ))

    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        height=300,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Percent",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )

    return fig