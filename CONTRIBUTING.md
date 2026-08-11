# Contributing to Renglo Projects

Thank you for considering contributing!

## How to Contribute
- Fork the repository
- Create a feature branch (never develop directly on `main`)
- Submit a Pull Request

## Branching

All work happens on feature branches. Do not commit directly to `main`.

### Cross-repository features

Features often span multiple repositories (for example `renglo-lib`, `renglo-api`, `console`, extensions, and ops). When a feature touches more than one repo:

1. **Use the same branch name** in every participating repository (for example `feature/vector-store-rag`).
2. **Branch only repos that change** — do not create empty matching branches.
3. **Use a descriptive prefix**, typically `feature/<short-description>` or `feature/<ticket>-<short-description>`.
4. **Track coordination** with a meta issue or checklist listing each repo, branch, PR, and merge order.

Example branch names:

- `feature/vector-store-rag` — platform vector store and RAG knowledge base
- `feature/pes-plan-handlers` — PES plan generation handlers

### Merge order

When repos depend on each other, merge bottom-up:

```
renglo-lib → renglo-api → consumers (console, extensions, ops)
```

Open one PR per repository when the feature is stable. Link all PRs to the same tracking issue.

## Contributor License Agreement (CLA)
By contributing to this project, you agree to the Contributor License Agreement (CLA) in `CLA.md`.  
Pull Requests cannot be merged until the CLA check has passed.

## License Model
This project is licensed under the MIT License. See `LICENSE.txt` for details.


## Instructions

Option A.
To contribute, please fill out the appropriate sign-off form (ICLA.md or CCLA.md) by copying it into a Pull Request comment or GitHub Issue and completing your details.

Option B.
In GitHub, click on New Issue, look for the “Sign the CLA” option.
They fill out the form → it becomes a permanent signed issue (which you can label with cla-signed).