"""Generate the report's results tables (Markdown) directly from the CSVs.

Usage: python experiments/make_tables.py   (writes results/tables.md)
Numbers in the report should be pasted from this file, never retyped.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
METHODS = ["Reorder-point baseline", "Greedy baseline", "Constraint Optimizer"]


def md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def pm(mean, sd, scale=100, digits=1):
    return f"{mean * scale:.{digits}f} ± {sd * scale:.{digits}f}"


def base_case():
    s = pd.read_csv(RESULTS / "scenario_comparison.csv")
    b = s[s["scenario"] == "Base case"].set_index("method").loc[METHODS]
    return md(pd.DataFrame({
        "Method": b.index,
        "Fill rate (%)": (b["demand_fill_rate"] * 100).round(1),
        "Unfilled demand (units)": b["unfilled_demand_units"],
        "Shortage to target (units)": b["shortage_to_target_units"],
        "Spend ($)": b["planned_purchase_cost"].map(lambda v: f"{v:,.0f}"),
    }))


def scenarios():
    s = pd.read_csv(RESULTS / "scenario_comparison.csv")
    pivot = s.pivot(index="scenario", columns="method", values="demand_fill_rate").loc[
        s["scenario"].unique(), METHODS] * 100
    pivot = pivot.round(1).reset_index().rename(columns={"scenario": "Scenario"})
    pivot.columns = ["Scenario"] + [f"{m} fill (%)" for m in METHODS]
    return md(pivot)


def experiment(name):
    summary = pd.read_csv(RESULTS / "experiment_summary.csv")
    sig = pd.read_csv(RESULTS / "significance.csv")
    cell = summary[summary["experiment"] == name]
    rows = []
    for setting in cell["setting"].unique():
        row = {"Setting": setting}
        for m in METHODS:
            r = cell[(cell["setting"] == setting) & (cell["method"] == m)].iloc[0]
            row[f"{m} fill (%)"] = pm(r["demand_fill_rate_mean"], r["demand_fill_rate_std"])
        g = sig[(sig["experiment"] == name) & (sig["setting"] == setting) & (sig["vs"] == "Greedy baseline")].iloc[0]
        row["Gain vs greedy (pp)"] = f"{g['mean_fill_rate_gain_pp']:.2f}"
        row["Better / tie / worse"] = f"{g['optimizer_better']} / {g['ties']} / {g['optimizer_worse']}"
        row["Wilcoxon p"] = "n/a (all ties)" if pd.isna(g["wilcoxon_p"]) else f"{g['wilcoxon_p']:.1e}"
        if name == "size":
            opt = cell[(cell["setting"] == setting) & (cell["method"] == "Constraint Optimizer")].iloc[0]
            row["Optimizer runtime (s)"] = f"{opt['runtime_s_mean']:.3f}"
        rows.append(row)
    return md(pd.DataFrame(rows))


def scaling():
    s = pd.read_csv(RESULTS / "solver_scaling.csv")
    g = s.groupby("n_skus").agg(
        solved=("csp_status", lambda x: f"{(x == 'Optimal').sum()}/{len(x)}"),
        agree=("same_optimum", "sum"),
        nodes=("csp_nodes", "median"),
        csp=("csp_runtime_s", "mean"),
        highs=("highs_runtime_s", "mean"),
    ).reset_index()
    return md(pd.DataFrame({
        "SKUs": g["n_skus"],
        "Our solver: solved within 1M nodes": g["solved"],
        "Same optimum as HiGHS": g["agree"].astype(int).astype(str) + " of solved",
        "Median nodes": g["nodes"].map(lambda v: f"{v:,.0f}"),
        "Our runtime (s)": g["csp"].map(lambda v: f"{v:.3f}"),
        "HiGHS runtime (s)": g["highs"].map(lambda v: f"{v:.3f}"),
    }))


def ablation():
    a = pd.read_csv(RESULTS / "solver_ablation.csv")
    rows = []
    for config, cell in a.groupby("configuration", sort=False):
        row = {"Configuration": config}
        for n, sub in cell.groupby("n_skus"):
            hits = int((sub["status"] != "Optimal").sum())
            med = sub["nodes"].median()
            row[f"{n} SKUs: median nodes"] = (">=" if med >= 200_000 else "") + f"{med:,.0f}" + (
                f" ({hits}/{len(sub)} at limit)" if hits else "")
        rows.append(row)
    return md(pd.DataFrame(rows))


def sensitivity():
    s = pd.read_csv(RESULTS / "urgency_sensitivity.csv")
    labels = {
        "fill_rate": "Overall fill rate (%)",
        "priority_weighted_fill_rate": "Priority-weighted fill rate (%)",
        "priority5_fill_rate": "Priority-5 SKUs fill rate (%)",
        "slow_orderable_fill_rate": "Orderable SKUs with lead time >= 20 days, fill rate (%)",
    }
    rows = []
    for col, label in labels.items():
        row = {"Metric": label}
        for mode, name in (("priority_lead", "priority x (1 + L/H)"), ("priority", "priority only")):
            v = s[s["urgency_mode"] == mode][col]
            row[name] = pm(v.mean(), v.std())
        rows.append(row)
    return md(pd.DataFrame(rows))


def main():
    sections = [
        ("Table 1. Sample dataset (12 SKUs), base case", base_case()),
        ("Table 2. Single-factor what-if scenarios on the sample dataset (fill rate %)", scenarios()),
        ("Table 3. Experiment 1, problem size (budget 60% of need, warehouse room for 50% of needed units; 30 instances per row; mean ± SD)", experiment("size")),
        ("Table 4. Experiment 2, budget tightness (50 SKUs, capacity loose; 30 instances per row)", experiment("budget")),
        ("Table 5. Experiment 3, warehouse tightness (50 SKUs, budget loose; 30 instances per row)", experiment("capacity")),
        ("Table 6. Experiment 4, our CSP solver vs HiGHS (15 instances per size)", scaling()),
        ("Table 7. Experiment 5, ablation of search techniques (15 instances per size; node limit 200,000)", ablation()),
        ("Table 8. Experiment 6, urgency-weight sensitivity (50 SKUs, 30 instances)", sensitivity()),
    ]
    text = "# Results tables (generated by experiments/make_tables.py, do not edit by hand)\n\n"
    text += "\n\n".join(f"**{title}**\n\n{table}" for title, table in sections) + "\n"
    (RESULTS / "tables.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
