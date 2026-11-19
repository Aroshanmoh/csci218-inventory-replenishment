"""Solver study: our CSP search vs HiGHS, ablation of search techniques, and
sensitivity of the plan to the urgency weight.

Experiment 4 (scaling):    our solver vs HiGHS, 6-30 SKUs. Agreement, nodes, runtime.
Experiment 5 (ablation):   switch off one technique at a time on 6/8/10 SKUs.
Experiment 6 (sensitivity): urgency weight priority*(1+L/H) vs priority only, 50 SKUs.

Outputs (results/): solver_scaling.csv, solver_ablation.csv, urgency_sensitivity.csv
Usage: python experiments/run_solver_study.py [--quick]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.csp_solver import solve_csp  # noqa: E402
from src.evaluation import evaluate_plan  # noqa: E402
from src.instances import make_instance  # noqa: E402
from src.optimizer import optimize_orders  # noqa: E402

ABLATIONS = {
    "Full (BT + FC + B&B + dominance + ordering)": {},
    "without branch & bound": {"branch_and_bound": False},
    "without forward checking": {"forward_checking": False},
    "without dominance pruning": {"dominance": False},
    "without variable ordering": {"var_order": "input"},
    "plain backtracking": {"branch_and_bound": False, "forward_checking": False,
                           "dominance": False, "var_order": "input"},
}


def args_of(inst):
    c = inst.config
    return inst.inventory.to_dict("records"), c["purchasing_budget"], c["warehouse_capacity"], c["planning_horizon_days"]


def scaling(sizes, runs, node_limit):
    rows = []
    for n in sizes:
        for rep in range(runs):
            seed = 2_000_000 + 1000 * n + rep
            inst = make_instance(n, seed)
            t = time.perf_counter()
            highs = optimize_orders(*args_of(inst))
            highs_time = time.perf_counter() - t
            ours = solve_csp(*args_of(inst), max_nodes=node_limit)
            agree = (ours["status"] == "Optimal" and abs(
                ours["summary"]["priority_weighted_shortage"]
                - highs["summary"]["priority_weighted_shortage"]) < 1e-5)
            rows.append({
                "n_skus": n, "seed": seed, "csp_status": ours["status"],
                "csp_nodes": ours["stats"].nodes, "csp_runtime_s": ours["stats"].runtime_s,
                "csp_pruned_by_bound": ours["stats"].pruned_by_bound,
                "highs_runtime_s": highs_time, "same_optimum": agree,
            })
        print(f"  scaling: {n} SKUs done", flush=True)
    return pd.DataFrame(rows)


def ablation(sizes, runs, node_limit):
    rows = []
    for n in sizes:
        for rep in range(runs):
            seed = 3_000_000 + 1000 * n + rep
            inst = make_instance(n, seed)
            for name, options in ABLATIONS.items():
                result = solve_csp(*args_of(inst), max_nodes=node_limit, **options)
                rows.append({
                    "n_skus": n, "seed": seed, "configuration": name,
                    "status": result["status"], "nodes": result["stats"].nodes,
                    "runtime_s": result["stats"].runtime_s,
                })
        print(f"  ablation: {n} SKUs done", flush=True)
    return pd.DataFrame(rows)


def sensitivity(runs, n=50):
    rows = []
    for rep in range(runs):
        seed = 4_000_000 + rep
        inst = make_instance(n, seed)
        inventory = inst.inventory
        for mode in ("priority_lead", "priority"):
            plan = optimize_orders(*args_of(inst), urgency_mode=mode)
            details = pd.DataFrame(evaluate_plan(inventory, plan, 30, inst.config["purchasing_budget"])["details"])
            details = details.merge(inventory[["sku_id", "expected_demand"]], on="sku_id")
            details["fulfilled"] = details["expected_demand"] - details["unfilled_demand"]
            orderable = details[details["order_arrives_within_horizon"]]
            p5 = details[details["priority"] == 5]
            slow = orderable[orderable["lead_time_days"] >= 20]
            rows.append({
                "seed": seed, "urgency_mode": mode,
                "fill_rate": details["fulfilled"].sum() / details["expected_demand"].sum(),
                "priority_weighted_fill_rate": (details["priority"] * details["fulfilled"]).sum()
                / (details["priority"] * details["expected_demand"]).sum(),
                "priority5_fill_rate": p5["fulfilled"].sum() / max(1, p5["expected_demand"].sum()),
                "slow_orderable_fill_rate": slow["fulfilled"].sum() / max(1, slow["expected_demand"].sum()),
            })
    print("  sensitivity done", flush=True)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True)
    q = args.quick

    print("Experiment 4: scaling, our solver vs HiGHS")
    scale = scaling((6, 10) if q else (6, 10, 15, 20, 25, 30), 3 if q else 15, 1_000_000)
    scale.to_csv(args.out / "solver_scaling.csv", index=False)
    print("Experiment 5: ablation")
    abl = ablation((6, 8) if q else (6, 8, 10), 3 if q else 15, 200_000)
    abl.to_csv(args.out / "solver_ablation.csv", index=False)
    print("Experiment 6: urgency-weight sensitivity")
    sens = sensitivity(5 if q else 30)
    sens.to_csv(args.out / "urgency_sensitivity.csv", index=False)

    pd.set_option("display.width", 200)
    print("\nScaling (mean per size)")
    print(scale.groupby("n_skus").agg(
        solved=("csp_status", lambda s: f"{(s == 'Optimal').sum()}/{len(s)}"),
        same_optimum=("same_optimum", "sum"),
        csp_nodes_mean=("csp_nodes", "mean"), csp_nodes_median=("csp_nodes", "median"),
        csp_runtime_s=("csp_runtime_s", "mean"), highs_runtime_s=("highs_runtime_s", "mean"),
    ).round(3).to_string())
    print("\nAblation (median nodes; runs hitting the node limit)")
    print(abl.groupby(["n_skus", "configuration"], sort=False).agg(
        median_nodes=("nodes", "median"), mean_runtime_s=("runtime_s", "mean"),
        hit_node_limit=("status", lambda s: int((s != "Optimal").sum())),
    ).round(4).to_string())
    print("\nUrgency sensitivity (mean ± SD)")
    print(sens.groupby("urgency_mode").agg(["mean", "std"]).drop(columns="seed").round(4).T.to_string())


if __name__ == "__main__":
    main()
