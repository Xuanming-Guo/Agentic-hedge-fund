# Contributing

Thank you for improving Agentic Hedge Fund. This project is a simulation-only agent society lab, not a real trading system.

## Branching Strategy

- `main`: stable, protected.
- `develop`: integration branch.
- `feature/<short-name>`: new features.
- `fix/<short-name>`: bug fixes.
- `chore/<short-name>`: tooling and docs.
- `release/<version>`: release prep.

## Commit Convention

Use Conventional Commits:

- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`
- `chore:`
- `ci:`

## Local Checks

```bash
make test
make lint
make mcp-smoke
```

Tests must pass in mock mode without a Qwen API key.
