#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CF_RECOVERY_PASSWORD:-}" ]]; then
  echo "CF_RECOVERY_PASSWORD is required." >&2
  exit 1
fi

ready=false
for attempt in $(seq 1 90); do
  if cypher-shell -a bolt://127.0.0.1:7687 'RETURN 1' >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  exit 1
fi

{
  printf ":param newPassword => '%s'\n" "$CF_RECOVERY_PASSWORD"
  printf '%s\n' 'ALTER USER neo4j SET PASSWORD $newPassword CHANGE NOT REQUIRED;'
} | cypher-shell -a bolt://127.0.0.1:7687 >/dev/null
