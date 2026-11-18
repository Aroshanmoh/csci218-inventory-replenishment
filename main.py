"""Run the baseline and constraint optimizer on the bundled dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.data_loader import prepare_project_data
from src.scenarios import run_comparison, run_standard_scenarios
from src.experiments import run_experiments, summarize_experiments

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=ROOT / "data" / "inventory_data.csv")
    parser.add_argument("--config", type=Path, default=ROOT / "data" / "company_config.csv")
    parser.add_argument("--no-save", action="store_true", help="Print results without writing result files.")
    parser.add_argument("--experiments", action="store_true", help="Run Member 5 repeatable experiments.")
    parser.add_argument("--experiment-count", type=int, default=30, help="Number of generated experiments (default: 30).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible experiments.")
    parser.add_argument(
        "--scenarios",
        action="store_true",
        help="Also compare both methods across the standard scenarios.",
    )
    args = parser.parse_args()

    inventory, config = prepare_project_data(args.inventory, args.config)
    baseline, optimized, evaluation = run_comparison(inventory, config)

    comparison = pd.DataFrame(
        {
            method: result["metrics"]
            for method, result in evaluation.items()
        }
    ).T
    print("INVENTORY REPLENISHMENT COMPARISON")
    print(comparison.to_string(float_format=lambda value: f"{value:,.2f}"))
    print("\nOPTIMIZER RECOMMENDATIONS")
    recommendations = pd.DataFrame(optimized["recommendations"])
    columns = [
        "sku_id",
        "priority",
        "lead_time_days",
        "order_quantity",
        "projected_inventory",
        "target_inventory",
        "remaining_shortage",
        "purchase_cost",
        "explanation",
    ]
    print(recommendations[columns].to_string(index=False))

    experiment_results = None
    if args.experiments:
        experiment_results = run_experiments(
            inventory,
            config,
            n_scenarios=args.experiment_count,
            seed=args.seed,
            output_path=(ROOT / "results" / "member5_experiment_results.csv") if not args.no_save else None,
        )
        print("\\nMEMBER 5 EXPERIMENT SUMMARY")
        print(summarize_experiments(experiment_results).to_string(index=False))

    scenario_results = None
    if args.scenarios:
        scenario_results = run_standard_scenarios(inventory, config)
        print("\nSTANDARD SCENARIO COMPARISON")
        print(scenario_results.to_string(index=False, float_format=lambda value: f"{value:,.2f}"))

    if not args.no_save:
        result_dir = ROOT / "results"
        result_dir.mkdir(exist_ok=True)
        comparison_path = result_dir / "comparison.json"
        comparison_path.write_text(
            json.dumps(
                {
                    "config": config,
                    "comparison": evaluation,
                    "optimizer_status": optimized["status"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        baseline_rows = {
            row["sku_id"]: row for row in baseline["recommendations"]
        }
        optimized_rows = {
            row["sku_id"]: row for row in optimized["recommendations"]
        }
        base_details = evaluation["Baseline"]["details"]
        optimized_details = evaluation["Constraint Optimizer"]["details"]
        detail_lookup = {
            method: {row["sku_id"]: row for row in rows}
            for method, rows in [
                ("Baseline", base_details),
                ("Constraint Optimizer", optimized_details),
            ]
        }
        output = []
        for product in inventory.to_dict(orient="records"):
            sku = str(product["sku_id"])
            output.append(
                {
                    "sku_id": sku,
                    "product_name": product["product_name"],
                    "baseline_order_quantity": baseline_rows[sku]["order_quantity"],
                    "optimizer_order_quantity": optimized_rows[sku]["order_quantity"],
                    "baseline_shortage_to_target": detail_lookup["Baseline"][sku]["shortage_to_target"],
                    "optimizer_shortage_to_target": detail_lookup["Constraint Optimizer"][sku]["shortage_to_target"],
                    "baseline_demand_fill_rate": detail_lookup["Baseline"][sku]["fill_rate"],
                    "optimizer_demand_fill_rate": detail_lookup["Constraint Optimizer"][sku]["fill_rate"],
                    "baseline_purchase_cost": baseline_rows[sku]["purchase_cost"],
                    "optimizer_purchase_cost": optimized_rows[sku]["purchase_cost"],
                }
            )
        pd.DataFrame(output).to_csv(result_dir / "recommendations.csv", index=False)
        if scenario_results is not None:
            scenario_results.to_csv(result_dir / "scenario_comparison.csv", index=False)
        if experiment_results is not None:
            experiment_results.to_csv(result_dir / "member5_experiment_results.csv", index=False)
        print(f"\nSaved results to {result_dir}")


if __name__ == "__main__":
    main()

