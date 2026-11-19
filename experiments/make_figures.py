"""Build the report figures from the committed results CSVs.

Usage: python experiments/make_figures.py   (writes results/figures/*.png)
Colours: first three slots of a colour-blind-validated categorical palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLOURS = {
    "Constraint Optimizer": "#2a78d6",
    "Greedy baseline": "#eb6834",
    "Reorder-point baseline": "#1baf7a",
    "Our CSP solver": "#eb6834",
    "HiGHS (MILP)": "#2a78d6",
}
ABLATION_NODE_LIMIT = 200_000  # must match run_solver_study.py
ORDER = ["Constraint Optimizer", "Greedy baseline", "Reorder-point baseline"]
MARKERS = {"Constraint Optimizer": "o", "Greedy baseline": "s", "Reorder-point baseline": "D"}


def style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.tick_params(colors=INK_2, length=0)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)


def tightness(summary, experiment, xcol, xlabel, title, filename):
    cell = summary[summary["experiment"] == experiment].copy()
    cell["x"] = cell["setting"].str.extract(r"(\d+)%").astype(int)
    fig, ax = plt.subplots(figsize=(7, 4.4))
    step = (cell["x"].max() - cell["x"].min()) / 60  # small horizontal dodge per method
    for offset, method in zip((-1, 0, 1), ORDER):
        rows = cell[cell["method"] == method].sort_values("x")
        mean = rows["demand_fill_rate_mean"] * 100
        sd = rows["demand_fill_rate_std"] * 100
        ax.errorbar(rows["x"] + offset * step, mean, yerr=sd, color=COLOURS[method], linewidth=2,
                    marker=MARKERS[method], markersize=8, markeredgecolor=SURFACE, markeredgewidth=2,
                    capsize=4, elinewidth=1, label=method)
    style(ax, title, xlabel, "Fill rate (%), mean ± SD, 30 instances")
    ax.set_xticks(sorted(cell["x"].unique()))
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=3,
              fontsize=9, labelcolor=INK, handletextpad=0.4, columnspacing=1.2)
    ax.set_ylim(top=ax.get_ylim()[1] + 4)
    fig.tight_layout()
    fig.savefig(FIGURES / filename, dpi=200)
    plt.close(fig)


def runtime(summary, scaling):
    size = summary[(summary["experiment"] == "size") & (summary["method"] == "Constraint Optimizer")].copy()
    size["n"] = size["setting"].str.extract(r"(\d+)").astype(int)
    ours = scaling[scaling["csp_status"] == "Optimal"].groupby("n_skus")["csp_runtime_s"].mean()
    highs_small = scaling.groupby("n_skus")["highs_runtime_s"].mean()
    # Small sizes come from the solver study; sizes beyond it from experiment 1.
    large = size.set_index("n")["runtime_s_mean"]
    highs = pd.concat([highs_small, large[large.index > highs_small.index.max()]]).sort_index()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for name, series in (("HiGHS (MILP)", highs), ("Our CSP solver (solved runs only)", ours)):
        COLOURS.setdefault(name, COLOURS["Our CSP solver"])
        ax.plot(series.index, series.values, color=COLOURS[name], linewidth=2, marker="o",
                markersize=8, markeredgecolor=SURFACE, markeredgewidth=2, label=name)
    ax.set_xscale("log")
    ax.set_yscale("log")
    style(ax, "Runtime vs problem size", "Number of SKUs (log scale)", "Mean runtime, seconds (log scale)")
    unsolved = scaling.groupby("n_skus")["csp_status"].apply(lambda s: int((s != "Optimal").sum()))
    note = ", ".join(f"{n}: {k}" for n, k in unsolved.items() if k)
    if note:
        ax.text(0.99, 0.02, f"Our solver hit the 1M-node limit on (SKUs: runs out of 15) {note}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color=INK_2)
    ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig3_runtime_scaling.png", dpi=200)
    plt.close(fig)


def ablation(abl):
    n = abl["n_skus"].max()
    cell = abl[abl["n_skus"] == n].groupby("configuration", sort=False)
    med = cell["nodes"].median().sort_values()
    limit_hits = cell["status"].apply(lambda s: int((s != "Optimal").sum()))
    runs = cell.size()
    node_limit = ABLATION_NODE_LIMIT
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(med.index, med.values, color=COLOURS["Constraint Optimizer"], height=0.55)
    for i, (name, value) in enumerate(med.items()):
        note = ("≥" if value >= node_limit else "") + f"{value:,.0f}"
        if limit_hits[name]:
            note += f" ({limit_hits[name]}/{runs[name]} stopped at limit)"
        ax.annotate(note, (value, i), xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=9)
    ax.set_xscale("log")
    ax.invert_yaxis()
    style(ax, "", "Nodes expanded (log scale)", "")
    fig.suptitle(f"Ablation: nodes expanded, {n} SKUs (median of {runs.iloc[0]} instances)",
                 x=0.02, ha="left", color=INK, fontsize=12, fontweight="bold")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(left=10, right=med.max() * 400)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig4_ablation_nodes.png", dpi=200)
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(RESULTS / "experiment_summary.csv")
    tightness(summary, "budget", "budget", "Budget as % of the spend needed to reach every target",
              "Fill rate vs budget tightness (50 SKUs, capacity loose)", "fig1_budget_tightness.png")
    tightness(summary, "capacity", "capacity", "Free warehouse space as % of the units needed",
              "Fill rate vs warehouse tightness (50 SKUs, budget loose)", "fig2_capacity_tightness.png")
    runtime(summary, pd.read_csv(RESULTS / "solver_scaling.csv"))
    ablation(pd.read_csv(RESULTS / "solver_ablation.csv"))
    print(f"Figures written to {FIGURES}")


if __name__ == "__main__":
    main()
