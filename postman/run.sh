#!/usr/bin/env bash
# Run the Postman contract collection locally (no Postman Cloud).
# Requires: newman (npm i -g newman). Fails non-zero when any assertion fails.
# Tokens come from the environment file and are never written back.
set -euo pipefail
ROOT="$(cd "$(dirname "${0}")/.." && pwd)"
COLLECTION="${ROOT}/postman/collections/raghub-api.postman_collection.json"
ENV_FILE="${POSTMAN_ENV:-${ROOT}/postman/environments/local.example.json}"
npx --yes newman@6 run "${COLLECTION}" -e "${ENV_FILE}" \
  --env-var "base_url=${BASE_URL:-http://localhost:8000}"
