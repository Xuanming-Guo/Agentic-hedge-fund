#!/usr/bin/env bash
set -euo pipefail
(cd apps/api && ruff format app)
(cd apps/web && pnpm format)
