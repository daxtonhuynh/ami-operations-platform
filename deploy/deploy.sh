#!/usr/bin/env bash
# Deploy the database to an empty Supabase project (or any PostgreSQL 15+ server).
#
#   export SUPABASE_DB_URL="postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
#   export APP_PASSWORD="<password for the ami_app login>"
#   bash deploy/deploy.sh            # first time
#   bash deploy/deploy.sh --fresh    # drop the AMI schemas first (all data is lost)
#
# Use the session pooler (port 5432) or the direct connection: the scripts use psql meta-commands and COPY.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SUPABASE_DB_URL:?set SUPABASE_DB_URL}"
: "${APP_PASSWORD:?set APP_PASSWORD}"
PSQL=(psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -q)

if [[ "${1:-}" == "--fresh" ]]; then
  echo "Dropping the AMI schemas..."
  "${PSQL[@]}" -c "drop schema if exists app, rpt, ctl, finance, payroll, hr, billing, academic, crm, ref cascade"
fi
echo "1/3 Building schema, rules, views, reference data and security..."
(cd database && "${PSQL[@]}" -f build.sql)
echo "2/3 Application login..."
"${PSQL[@]}" -v app_password="$APP_PASSWORD" -f deploy/supabase_setup.sql
echo "3/3 Loading the demo dataset..."
"${PSQL[@]}" -1 -o /dev/null -f seed/demo_dataset.sql
"${PSQL[@]}" -At -c "select 'Business date ' || ref.as_of_date() || ' - ' || count(*) || ' enrolments' from billing.enrollment"
echo "Done. Set DATABASE_URL (user ami_app.<project-ref>), DEMO_MODE and DEMO_PASSWORD in the app's secrets."
