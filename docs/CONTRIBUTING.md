# Team Git Workflow

## Folder layout

- `src/` — application logic, baselines, optimization, data handling, and evaluation
- `data/` — input datasets and configuration
- `tests/` — automated tests
- `docs/` — project documentation and contribution notes
- `experiments/` — reproducible experiment scripts
- `results/` — generated experiment outputs and figures

Keep files in the folder that matches their purpose. Avoid creating duplicate copies of the same source file.

## Individual contribution workflow

Each member works on their own branch. Do not commit directly to `main`.

| Member | Branch |
|---|---|
| Member 1 | `member-1-work` |
| Member 2 | `member-2-work` |
| Member 3 | `member-3-work` |
| Member 4 | `member-4-work` |
| Member 5 | `member-5-work` |

### First time

Clone the repository, then switch to your assigned branch:

```bash
git clone https://github.com/Aroshanmoh/csci218-inventory-replenishment.git
cd csci218-inventory-replenishment
git switch member-N-work
```

Replace `N` with your member number.

### Every time you contribute

```bash
git pull origin member-N-work
git status
git add path/to/your/changed-files
git commit -m "Describe your contribution"
git push -u origin member-N-work
```

Use your own GitHub account and Git identity so your commits are attributed to you. Do not share accounts or commit under another member's name.

### Submit your work for integration

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
