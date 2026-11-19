"""Seeded experiments: all three methods on many random instances.

Experiment 1 (size):     12 / 50 / 200 / 500 SKUs; budget 60% of need and
                          warehouse room for 50% of needed units (both bind).
Experiment 2 (budget):   50 SKUs, budget 30/60/90/120% of need, capacity loose.
Experiment 3 (capacity): 50 SKUs, room for 25/50/100% of needed units, budget loose.
Each experiment varies a single factor so its effect can be attributed.
Each cell has --runs instances (default 30). Every instance is generated from
a recorded seed, so any row in the CSVs can be reproduced exactly.

Outputs (results/):
  experiment_runs.csv     one row per (experiment, instance, method)
  experiment_summary.csv  mean and standard deviation per cell
  significance.csv        paired Wilcoxon signed-rank tests, optimizer vs each baseline

Usage:
  python experiments/run_experiments.py            # full run (~5 min)
  python experiments/run_experiments.py --quick    # 5 runs per cell, small sizes
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.baseline import baseline_replenishment, greedy_replenishment  # noqa: E402
from src.evaluation import evaluate_plan  # noqa: E402
from src.instances import make_instance  # noqa: E402
from src.optimizer import optimize_orders  # noqa: E402

METRICS = [
    "demand_fill_rate", "unfilled_demand_units", "shortage_to_target_units",
    "priority_weighted_shortage", "planned_purchase_cost", "budget_utilization",
    "runtime_s",
]


def solve_all(inst):
    cfg = inst.config
    horizon = cfg["planning_horizon_days"]
    methods = {
        "Reorder-point baseline": lambda: baseline_replenishment(inst.inventory, cfg, horizon),
        "Greedy baseline": lambda: greedy_replenishment(inst.inventory, cfg, horizon),
        "Constraint Optimizer": lambda: optimize_orders(
            inst.inventory.to_dict("records"), cfg["purchasing_budget"],
            cfg["warehouse_capacity"], horizon),
    }
    rows = []
    for name, run in methods.items():
        start = time.perf_counter()
        plan = run()
        runtime = time.perf_counter() - start
        metrics = evaluate_plan(inst.inventory, plan, horizon, cfg["purchasing_budget"])["metrics"]
        rows.append({"method": name, "runtime_s": runtime, **metrics})
    return rows


def run_cell(experiment, label, n_skus, budget_ratio, capacity_slack, runs, seed_base):
    rows = []
    for rep in range(runs):
        seed = seed_base + rep
        inst = make_instance(n_skus, seed, budget_ratio=budget_ratio, capacity_slack=capacity_slack)
        for row in solve_all(inst):
            rows.append({"experiment": experiment, "setting": label, "n_skus": n_skus,
                         "budget_ratio": budget_ratio, "capacity_slack": capacity_slack,
                         "seed": seed, **row})
    print(f"  {experiment}: {label} done ({runs} runs)", flush=True)
    return rows


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    grouped = runs.groupby(["experiment", "setting", "method"], sort=False)[METRICS]
    summary = grouped.agg(["mean", "std"])
    summary.columns = [f"{m}_{s}" for m, s in summary.columns]
    return summary.reset_index()


def significance(runs: pd.DataFrame) -> pd.DataFrame:
    """Paired test per cell: same instances, optimizer vs each baseline."""
    out = []
    for (experiment, setting), cell in runs.groupby(["experiment", "setting"], sort=False):
        pivot = cell.pivot(index="seed", columns="method", values="demand_fill_rate")
        for baseline in ("Reorder-point baseline", "Greedy baseline"):
            diff = pivot["Constraint Optimizer"] - pivot[baseline]
            nonzero = diff[diff != 0]
            p = wilcoxon(nonzero).pvalue if len(nonzero) >= 5 else float("nan")
            out.append({
                "experiment": experiment, "setting": setting, "vs": baseline,
                "mean_fill_rate_gain_pp": 100 * diff.mean(),
                "sd_gain_pp": 100 * diff.std(),
                "optimizer_better": int((diff > 0).sum()),
                "ties": int((diff == 0).sum()),
                "optimizer_worse": int((diff < 0).sum()),
                "wilcoxon_p": p,
            })
    return pd.DataFrame(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    runs = 5 if args.quick else args.runs
    sizes = (12, 50) if args.quick else (12, 50, 200, 500)

    rows = []
    print("Experiment 1: problem size")
    for i, n in enumerate(sizes):
        rows += run_cell("size", f"{n} SKUs", n, 0.6, 0.5, runs, seed_base=10_000 * (i + 1))
    print("Experiment 2: budget tightness (capacity loose)")
    for i, ratio in enumerate((0.3, 0.6, 0.9, 1.2)):
        rows += run_cell("budget", f"budget {int(ratio * 100)}% of need", 50, ratio, 3.0, runs,
                         seed_base=100_000 * (i + 1))
    print("Experiment 3: capacity tightness (budget loose)")
    for i, slack in enumerate((0.25, 0.5, 1.0)):
        rows += run_cell("capacity", f"room for {int(slack * 100)}% of needed units", 50, 3.0, slack, runs,
                         seed_base=1_000_000 * (i + 1))

    df = pd.DataFrame(rows)
    args.out.mkdir(exist_ok=True)
    df.to_csv(args.out / "experiment_runs.csv", index=False)
    summary = summarise(df)
    summary.to_csv(args.out / "experiment_summary.csv", index=False)
    sig = significance(df)
    sig.to_csv(args.out / "significance.csv", index=False)

    pd.set_option("display.width", 200)
    print("\nMean fill rate (%) ± SD")
    view = summary[["experiment", "setting", "method", "demand_fill_rate_mean", "demand_fill_rate_std", "runtime_s_mean"]].copy()
    view["demand_fill_rate_mean"] *= 100
    view["demand_fill_rate_std"] *= 100
    print(view.round(3).to_string(index=False))
    print("\nOptimizer vs baselines (paired Wilcoxon on fill rate)")
    print(sig.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
