#!/usr/bin/env bash
set -euo pipefail
(cd apps/api && ruff check app && mypy app)
(cd apps/web && pnpm lint && pnpm typecheck)
