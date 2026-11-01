#!/usr/bin/env bash
# Regenerate the demo year up to today on a local scratch database and reload it into the hosted database.
# Used by the weekly GitHub Action; can be run by hand. Needs a local PostgreSQL superuser (PGHOST/PGUSER...).
#   SUPABASE_DB_URL=... bash deploy/reset_demo.sh [YYYY-MM-DD]
set -euo pipefail
cd "$(dirname "$0")/.."
AS_OF="${1:-$(TZ=Asia/Ho_Chi_Minh date +%F)}"
SCRATCH="${SCRATCH_DB:-ami_gen}"
dropdb --if-exists "$SCRATCH"
createdb "$SCRATCH"
(cd database && psql -q -v ON_ERROR_STOP=1 -d "$SCRATCH" -f build.sql)
python seed/generate_dataset.py --dsn "dbname=$SCRATCH" --as-of "$AS_OF" --password "${DEMO_PASSWORD:-ami-demo}"
bash seed/export_dataset.sh "$SCRATCH" > /tmp/ami_demo_dataset.sql 2>/dev/null
if [[ -n "${SUPABASE_DB_URL:-}" ]]; then
  psql "$SUPABASE_DB_URL" -q -v ON_ERROR_STOP=1 -1 -o /dev/null -f /tmp/ami_demo_dataset.sql
  echo "Hosted demo reset to business date $AS_OF"
else
  cp /tmp/ami_demo_dataset.sql seed/demo_dataset.sql
  echo "seed/demo_dataset.sql regenerated for business date $AS_OF"
fi
