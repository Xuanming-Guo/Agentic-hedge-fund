#!/usr/bin/env bash
set -euo pipefail
(cd apps/api && pytest)
(cd apps/web && pnpm test -- --run)
