# Inventory Replenishment as Constraint Optimisation: Report Skeleton

> **How to use this file.** This is a skeleton in the structure required by
> Section 4.1 of the CSCI218 guidelines. Technical content (formulation,
> algorithms, results tables, figures, references) is filled in. Lines marked
> **✍ WRITE** are prompts for your own prose: the report is assessed writing,
> so write those parts in your own words. Every number below is generated from
> `results/*.csv` by `experiments/make_tables.py`; if you re-run experiments,
> regenerate rather than retyping.
>
> AI-assistance disclosure: parts of the code and this skeleton were produced
> with AI assistance (see commit co-author lines). State this in the report as
> required by the subject descriptor.

---

## a) Executive summary

✍ WRITE (150–200 words, write it last). Cover: the problem (multi-SKU
replenishment under a shared budget and warehouse limit), the method (a
constraint optimisation problem solved by our own branch-and-bound CSP search
and by the HiGHS MILP solver), the headline result, and the main limitation.

Headline facts you can use:
- On the 12-SKU sample, fill rate is 94.1% (optimizer) vs 89.4% (fair greedy) vs 85.0% (reorder-point). See Table 1.
- On 30 seeded instances per setting, the optimizer beats the fair greedy baseline by +5.5 percentage points when the budget covers 30% of need, shrinking to 0 when the budget is not binding. See Table 4 and Figure 1.
- Our own solver matches HiGHS on every instance it finishes and is faster below about 15 SKUs, but stops scaling at about 30 SKUs. See Table 6 and Figure 3.

## b) Motivation

✍ WRITE. Points to cover:
- Why replenishment is hard for an IT distributor: many SKUs compete for one budget and one warehouse; MOQs and supplier order multiples make quantities discrete; lead times differ by supplier.
- Why rules of thumb fail: a per-SKU rule (reorder point, or greedy by priority) spends the budget on whichever SKU it reaches first, without seeing the portfolio.
- Why this is an AI problem: it is a Constraint Optimisation Problem (Russell & Norvig, Ch. 6): variables, discrete domains, global constraints, an objective. Exhaustive search is exponential in the number of SKUs, so search with propagation and bounding is needed.
- Measurable objectives (state them as numbers you then report against): e.g. (1) every hard constraint satisfied in 100% of plans; (2) higher fill rate than both baselines with p < 0.05 when resources bind; (3) our solver returns the proven optimum on instances up to N SKUs; (4) runtime under 2 s for 500 SKUs with HiGHS.
- Why constraint optimisation rather than alternatives: greedy is fast but myopic (our Table 4 quantifies this); genetic algorithms or simulated annealing give no optimality guarantee and need tuning; reinforcement learning needs a simulator and many episodes for a one-shot planning decision. Constraint optimisation gives provably optimal, explainable plans.

## c) Technical requirements

- Python 3.13; dependencies in `requirements.txt` (PuLP 3.3.2, highspy 1.15.1, pandas, Streamlit, Plotly, SciPy, Matplotlib, pytest).
- Inputs: `data/inventory_data.csv` (per SKU: current and incoming stock, expected demand, unit cost, MOQ, order multiple, lead time, safety stock, max stock, priority 1–5) and `data/company_config.csv` (budget, warehouse capacity, planning horizon).
- Functional requirements: validate inputs; recommend which SKUs to order and how much; respect every hard constraint; explain each decision; compare with baselines; run what-if scenarios through a UI.
- Non-functional: reproducible (fixed seeds, committed CSVs), tested (261 automated tests), interactive response under 2 s for realistic catalogue sizes.

## d) Main constructs

### d.1 Problem formulation (COP)

For SKUs i = 1..n with stock s_i, incoming r_i, demand d_i, safety stock ss_i,
max stock M_i, unit cost c_i, MOQ m_i, order multiple k_i, lead time L_i,
priority p_i, budget B, free capacity C = capacity − Σ(s_i + r_i), horizon H:

- **Variables:** q_i, the order quantity for SKU i.
- **Domains:** D_i = {0} ∪ {j·k_i : j ∈ ℕ, j·k_i ≥ m_i, j·k_i ≤ U_i}, with U_i = min(⌊B/c_i⌋, C, M_i − s_i − r_i). D_i = {0} if L_i > H (the order cannot arrive in this plan) or if s_i + r_i > M_i (already overstocked).
- **Unary constraints:** MOQ, order multiple, max stock; enforced by construction of D_i (node consistency).
- **Global constraints:** Σ c_i q_i ≤ B (budget); Σ q_i ≤ C (warehouse).
- **Target:** T_i = min(M_i, d_i + ss_i). Shortage_i = max(0, T_i − s_i − r_i − q_i); excess_i = max(0, s_i + r_i + q_i − T_i).
- **Objective (lexicographic):** minimise (1) Σ w_i·shortage_i, with w_i = p_i·(1 + L_i/H); then (2) Σ excess_i; then (3) Σ c_i q_i.

✍ WRITE: justify each choice in 1–2 sentences. For example: why lexicographic rather than a weighted sum (no arbitrary exchange rate between units of shortage and dollars); why the lead-time term (a unit short on a slow-to-replenish SKU stays short longer); why T_i is capped at M_i.

### d.2 Solver 1: our CSP search (`src/csp_solver.py`)

- **Backtracking:** depth-first, one SKU at a time.
- **Forward checking:** after each assignment, cut every future domain to the values that still fit the remaining budget and capacity. Domains are sorted and always contain 0, so a domain is a prefix and the check is a binary search.
- **Branch and bound:** prune a node when an optimistic bound on its best completion cannot beat the incumbent. The bound on remaining weighted shortage is the larger of two relaxations, each solved exactly by the fractional-knapsack greedy rule (Dantzig, 1957): drop capacity and integrality; or drop budget and integrality. Each relaxation can only under-estimate the true remaining shortage, so the bound is **admissible** and the search stays exact. This is the same role an admissible heuristic plays in A*.
- **Dominance pruning:** a lot larger than the first lot covering the gap adds excess and cost without reducing shortage, so it is removed before search.
- **Ordering:** variables by weighted shortage, descending (most important first); values largest-first, which finds a strong incumbent on the first dive.

✍ WRITE: link each technique to the lecture material on CSPs and search. Discuss complexity: worst case O(Π|D_i|), exponential in n; the bound and dominance shrink the explored tree but not the worst case.

### d.3 Solver 2: MILP with HiGHS (`src/optimizer.py`)

Same model, written as a mixed-integer linear programme in PuLP and solved with HiGHS (Huangfu & Hall, 2018). The lexicographic objective is solved in three stages; each stage's optimum is locked with a 1e-6 tolerance before the next. HiGHS uses LP-relaxation branch and bound (Land & Doig, 1960) with presolve and cutting planes, which explains why it scales further than our solver (Section f).

### d.4 Baselines (`src/baseline.py`)

- **Reorder-point baseline** (the traditional policy): reorder when s + r ≤ ss + d·L/H, up to target, SKUs in priority order. It may place orders that arrive after the horizon.
- **Greedy baseline** (fair comparison): the same eligibility rules and target as the optimizer, but decides one SKU at a time in priority order. The gap between greedy and the optimizer isolates the value of optimising the whole portfolio.

### d.5 Evaluation (`src/evaluation.py`)

A single function scores every plan: fill rate (Σ min(d, available) / Σ d), unfilled units, shortage to target, excess, spend, priority-weighted shortage. Orders arriving after H do not count as available.

## e) Implementation

✍ WRITE: describe the architecture (data loader → solvers/baselines → shared evaluation → CLI / Streamlit UI) and include:
- a screenshot of the Streamlit setup page and the comparison page (all three methods);
- a short code excerpt of the branch-and-bound pruning step (`solve_csp.search`) and of the MILP constraints (`optimize_orders`);
- the testing approach: 261 pytest tests, including a brute-force oracle that enumerates every valid plan on small instances; all five solver configurations must match it; the full solver must match HiGHS on 15-SKU instances; plus hard-constraint checks on 40-SKU instances and edge cases.
- Long-lead handling: SKUs whose lead time exceeds H are flagged "ORDER NOW FOR NEXT CYCLE" with a suggested lot and its cost (e.g. SSD-4TB-J: priority 5, 25 on hand vs 100 demand, 35-day lead time).

## f) Experiments and results

**Setup.** Instances come from `src/instances.py` with recorded seeds. Parameter ranges mirror the sample data. Budget and capacity are set relative to what is needed, so they genuinely bind. Each experiment varies one factor. 30 instances per setting (15 for the solver study); mean ± SD; paired Wilcoxon signed-rank tests (Wilcoxon, 1945) on fill rate, because the same instance is solved by every method. With 30 pairs all favouring one method, the exact test's smallest possible p is 1.9e-09, which is why that value repeats.

**Table 1. Sample dataset (12 SKUs), base case**

| Method | Fill rate (%) | Unfilled demand (units) | Shortage to target (units) | Spend ($) |
|---|---|---|---|---|
| Reorder-point baseline | 85.0 | 480 | 665 | 49,800 |
| Greedy baseline | 89.4 | 340 | 475 | 49,550 |
| Constraint Optimizer | 94.1 | 190 | 270 | 50,000 |

**Table 2. Single-factor what-if scenarios on the sample dataset (fill rate %)**

| Scenario | Reorder-point baseline fill (%) | Greedy baseline fill (%) | Constraint Optimizer fill (%) |
|---|---|---|---|
| Base case | 85.0 | 89.4 | 94.1 |
| Budget reduced by 30% | 85.0 | 85.0 | 92.5 |
| Demand increased by 20% | 81.7 | 83.7 | 90.9 |
| Tight warehouse (room for 50% of needed units) | 85.0 | 88.8 | 88.8 |
| Lead times +10 days | 75.9 | 86.6 | 86.6 |
| Current stock reduced by 75% | 48.1 | 49.7 | 78.6 |

**Table 3. Experiment 1, problem size (budget 60% of need, warehouse room for 50% of needed units; 30 instances per row; mean ± SD)**

| Setting | Reorder-point baseline fill (%) | Greedy baseline fill (%) | Constraint Optimizer fill (%) | Gain vs greedy (pp) | Better / tie / worse | Wilcoxon p | Optimizer runtime (s) |
|---|---|---|---|---|---|---|---|
| 12 SKUs | 72.9 ± 8.7 | 78.0 ± 6.5 | 80.2 ± 6.3 | 2.27 | 21 / 7 / 2 | 2.6e-05 | 0.040 |
| 50 SKUs | 72.7 ± 4.1 | 79.2 ± 2.7 | 81.1 ± 2.8 | 1.95 | 30 / 0 / 0 | 1.9e-09 | 0.169 |
| 200 SKUs | 72.6 ± 2.5 | 78.6 ± 1.6 | 80.7 ± 1.6 | 2.13 | 30 / 0 / 0 | 1.9e-09 | 0.640 |
| 500 SKUs | 72.3 ± 1.4 | 78.5 ± 0.9 | 80.6 ± 0.9 | 2.13 | 30 / 0 / 0 | 1.9e-09 | 1.636 |

**Table 4. Experiment 2, budget tightness (50 SKUs, capacity loose; 30 instances per row)**

| Setting | Reorder-point baseline fill (%) | Greedy baseline fill (%) | Constraint Optimizer fill (%) | Gain vs greedy (pp) | Better / tie / worse | Wilcoxon p |
|---|---|---|---|---|---|---|
| budget 30% of need | 69.1 ± 4.1 | 73.9 ± 4.0 | 79.3 ± 3.5 | 5.49 | 30 / 0 / 0 | 1.9e-09 |
| budget 60% of need | 75.0 ± 4.5 | 83.0 ± 4.6 | 85.6 ± 3.5 | 2.56 | 24 / 5 / 1 | 1.2e-07 |
| budget 90% of need | 80.1 ± 5.9 | 86.4 ± 4.7 | 86.7 ± 5.0 | 0.27 | 6 / 24 / 0 | 3.1e-02 |
| budget 120% of need | 81.9 ± 4.7 | 86.3 ± 5.4 | 86.3 ± 5.4 | 0.00 | 0 / 30 / 0 | n/a (all ties) |

**Table 5. Experiment 3, warehouse tightness (50 SKUs, budget loose; 30 instances per row)**

| Setting | Reorder-point baseline fill (%) | Greedy baseline fill (%) | Constraint Optimizer fill (%) | Gain vs greedy (pp) | Better / tie / worse | Wilcoxon p |
|---|---|---|---|---|---|---|
| room for 25% of needed units | 68.0 ± 4.3 | 70.8 ± 3.3 | 72.4 ± 3.5 | 1.54 | 29 / 0 / 1 | 3.7e-09 |
| room for 50% of needed units | 71.4 ± 4.2 | 78.6 ± 3.1 | 80.4 ± 2.9 | 1.78 | 29 / 1 / 0 | 3.7e-09 |
| room for 100% of needed units | 82.0 ± 4.8 | 87.1 ± 4.8 | 87.1 ± 4.9 | 0.05 | 2 / 28 / 0 | n/a (all ties) |

**Table 6. Experiment 4, our CSP solver vs HiGHS (15 instances per size)**

| SKUs | Our solver: solved within 1M nodes | Same optimum as HiGHS | Median nodes | Our runtime (s) | HiGHS runtime (s) |
|---|---|---|---|---|---|
| 6 | 15/15 | 15 of solved | 23 | 0.001 | 0.023 |
| 10 | 15/15 | 15 of solved | 193 | 0.004 | 0.066 |
| 15 | 15/15 | 15 of solved | 320 | 0.019 | 0.056 |
| 20 | 14/15 | 14 of solved | 4,049 | 0.785 | 0.074 |
| 25 | 13/15 | 13 of solved | 6,866 | 2.215 | 0.092 |
| 30 | 12/15 | 12 of solved | 52,940 | 3.791 | 0.099 |

**Table 7. Experiment 5, ablation of search techniques (15 instances per size; node limit 200,000)**

| Configuration | 6 SKUs: median nodes | 8 SKUs: median nodes | 10 SKUs: median nodes |
|---|---|---|---|
| Full (BT + FC + B&B + dominance + ordering) | 41 | 69 | 84 |
| without branch & bound | 1,773 (1/15 at limit) | 2,828 (4/15 at limit) | 33,692 (5/15 at limit) |
| without forward checking | 92 | 69 | 137 |
| without dominance pruning | 129 | 249 | 454 |
| without variable ordering | 87 | 146 | 220 |
| plain backtracking | 12,332 (3/15 at limit) | 136,148 (7/15 at limit) | >=200,000 (9/15 at limit) |

**Table 8. Experiment 6, urgency-weight sensitivity (50 SKUs, 30 instances)**

| Metric | priority x (1 + L/H) | priority only |
|---|---|---|
| Overall fill rate (%) | 80.7 ± 3.1 | 80.9 ± 3.0 |
| Priority-weighted fill rate (%) | 83.6 ± 3.8 | 83.8 ± 3.7 |
| Priority-5 SKUs fill rate (%) | 85.5 ± 10.0 | 85.5 ± 10.0 |
| Orderable SKUs with lead time >= 20 days, fill rate (%) | 92.7 ± 5.1 | 90.3 ± 5.7 |

**Figures** (in `results/figures/`):
- Figure 1: `fig1_budget_tightness.png`: fill rate vs budget tightness.
- Figure 2: `fig2_capacity_tightness.png`: fill rate vs warehouse tightness.
- Figure 3: `fig3_runtime_scaling.png`: runtime of our solver vs HiGHS.
- Figure 4: `fig4_ablation_nodes.png`: nodes expanded per search configuration.

✍ WRITE an interpretation for each table and figure. Key points to make in your own words:
1. The optimizer's advantage over the fair baseline is real but conditional: large when a resource binds (+5.5 pp at 30% budget), zero when nothing binds (120% budget, 100% room). This is what theory predicts: there is nothing to optimise without a binding constraint.
2. Against the traditional reorder-point policy the gap is larger (4.4–10.6 pp across Tables 3–5; about 8 pp when both resources bind). Part of that gap is the policy, not the optimisation: it spends budget on orders that arrive after the horizon, and it does not reorder SKUs just above their reorder point.
3. With both resources binding, the gain is stable at about 2 pp from 12 to 500 SKUs, and HiGHS stays under 2 s.
4. Branch and bound is the decisive search technique (84 vs 33,692 median nodes at 10 SKUs). Forward checking adds little, because the bound already accounts for remaining resources and 0 is always a legal value (no domain wipe-outs).
5. Our solver is exact but exponential; HiGHS's LP bounds, presolve and cuts are why industrial solvers are used in practice.
6. The lead-time term in the urgency weight is a trade-off, not a free gain: it raises fill on slow-lead SKUs (92.7% vs 90.3%) at a small cost in overall fill (80.7% vs 80.9%).

## g) Limitations, difficulties and constraints

Threats to validity (✍ WRITE these up properly):
- **Synthetic data:** instances are generated, and the 12-SKU sample is illustrative, not from a real company. Results may not transfer to real demand patterns.
- **Deterministic demand:** expected demand is treated as known. Real demand is uncertain; safety stock only partly covers this.
- **Single period:** one planning horizon. Long-lead SKUs are flagged but not planned; a multi-period model would plan them properly.
- **Metric alignment:** the optimizer minimises priority-weighted shortage, so it is favoured on that metric by construction. We therefore lead with fill rate, which neither method optimises directly; the optimizer can lose on fill rate (e.g. 2 of 30 instances at 12 SKUs).
- **Urgency weight:** the formula is our own modelling choice, not validated by a practitioner (sensitivity analysis in Table 8).
- **Baseline design:** we added the greedy baseline because the original reorder-point policy is disadvantaged by the single-period evaluation.
- **Solver scalability:** our solver hits the node limit on some instances of 20 or more SKUs.

✍ WRITE: difficulties the team faced (e.g. the float-equality bug when locking lexicographic stages, CRLF line endings, designing scenarios that actually bind).

## h) Conclusion and discussion

✍ WRITE. Answer the objectives from (b) with numbers. Suggested future work: multi-period planning; stochastic demand (scenario-based or chance constraints); a stronger joint LP bound for our solver; supplier price breaks; validation with a distributor's real data.

## i) References

Verify each against your subject's recommended reading list and add at least one from it.

1. Russell, S., & Norvig, P. (2021). *Artificial Intelligence: A Modern Approach* (4th ed.). Pearson. (Ch. 3, search; Ch. 6, constraint satisfaction problems.)
2. Silver, E. A., Pyke, D. F., & Thomas, D. J. (2017). *Inventory and Production Management in Supply Chains* (4th ed.). CRC Press.
3. Land, A. H., & Doig, A. G. (1960). An automatic method of solving discrete programming problems. *Econometrica, 28*(3), 497–520.
4. Haralick, R. M., & Elliott, G. L. (1980). Increasing tree search efficiency for constraint satisfaction problems. *Artificial Intelligence, 14*(3), 263–313.
5. Dantzig, G. B. (1957). Discrete-variable extremum problems. *Operations Research, 5*(2), 266–288.
6. Huangfu, Q., & Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. *Mathematical Programming Computation, 10*(1), 119–142.
7. Mitchell, S., O'Sullivan, M., & Dunning, I. (2011). *PuLP: A linear programming toolkit for Python.* University of Auckland.
8. Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin, 1*(6), 80–83.

## j) Appendices

- **Appendix A:** Git repository link + team contribution table (template in Appendix A of the guidelines). ✍ Fill in names, IDs, contributions with commit references, estimated shares.
- **Appendix B (bonus only):** industry meeting log + mentor feedback form.
- **Appendix C (replication):** commands to reproduce every table and figure: `python experiments/run_experiments.py`, `python experiments/run_solver_study.py`, `python experiments/make_tables.py`, `python experiments/make_figures.py`.
