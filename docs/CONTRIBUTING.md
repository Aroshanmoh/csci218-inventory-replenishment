# Team Git Workflow

## Folder layout

- `src/` — application logic, baselines, optimization, data handling, and evaluation
- `data/` — input datasets and configuration
- `tests/` — automated tests
- `docs/` — project documentation and contribution notes
- `experiments/` — reproducible experiment scripts
- `results/` — generated experiment outputs and figures

Keep files in the folder that matches their purpose. Avoid creating duplicate copies of the same source file.

## Member responsibilities and branches

Each member works on their own branch. Do not commit directly to `main`.

| Member | Branch | Main responsibility | Main files / areas |
|---|---|---|---|
| Member 1 | `member-1-work` | Data preparation and validation | `data/`, `src/data_loader.py`, `src/rules.py`, `src/instances.py` |
| Member 2 | `member-2-work` | Mixed-integer optimization (MILP) | `src/optimizer.py` |
| Member 3 | `member-3-work` | Traditional and greedy replenishment baselines | `src/baseline.py` |
| Member 4 | `member-4-work` | CSP solver, evaluation, scenarios, and application integration | `src/csp_solver.py`, `src/evaluation.py`, `src/scenarios.py`, `app.py`, `main.py`, `visualizations.py` |
| Member 5 | `member-5-work` | Experiments, testing, results, and report evidence | `experiments/`, `tests/`, `results/`, `PROJECT_REPORT.md`, `docs/`, `README.md` |

The project report explicitly identifies Member 2 with the optimizer and Member 3 with the baseline. The Member 1 and Member 4 split above is a proposed division based on the current project structure; confirm it with the team before treating it as a record of past individual contributions. Member 5's area follows the experiment/testing responsibility already assigned to that member.

Shared files must be coordinated. In particular, Member 5 should add tests for the features delivered by Members 1–4, rather than independently rewriting their implementation. The team should agree who owns any overlapping edits before changing them.

## First time

Clone the repository, then switch to your assigned branch:

```bash
git clone https://github.com/Aroshanmoh/csci218-inventory-replenishment.git
cd csci218-inventory-replenishment
git switch member-N-work
```

Replace `N` with your member number.

## Every time you contribute

```bash
git pull origin member-N-work
git status
git add path/to/your/changed-files
git commit -m "Describe your contribution"
git push -u origin member-N-work
```

Use your own GitHub account and Git identity so your commits are attributed to you. Do not share accounts or commit under another member's name.

## Submit your work for integration

1. Open a pull request on GitHub.
2. Set the base branch to `main` and compare branch to your member branch.
3. Explain what you changed and how you tested it.
4. Ask the group to review it before merging.
5. Do not merge conflicting or untested changes.

Before starting work, pull the latest `main` changes and coordinate edits to shared files such as `app.py`, `README.md`, and files in `src/`.

## Commit guidance

- Commit only files you personally changed or reviewed.
- Use small commits with clear messages.
- Do not commit virtual environments, caches, passwords, API keys, or temporary files.
- Keep generated results only when they are reproducible and needed for the report.
- Run the relevant tests before opening a pull request.
