# Deployment: Supabase (PostgreSQL) + Streamlit Community Cloud

Total cost: zero on the free tiers. About 20 minutes.

```
Browser ──► Streamlit app (streamlit_app.py, ami/)  ──login ami_app──►  Supabase PostgreSQL
                                                       SET LOCAL ROLE ami_<role> per transaction
GitHub Actions ── CI on every push (database tests, generator, app tests)
               └─ every Monday: regenerate the demo year up to today and reload it into Supabase
```

## 1. Database on Supabase

1. Create a project at supabase.com (any region; note the database password).
2. *Project settings → Database → Connection string*: copy the **Session pooler** URI (port 5432, user `postgres.<project-ref>`).
   The build uses psql meta-commands and COPY, so use the session pooler or the direct connection, not the transaction pooler.
3. From a machine with `psql` (PostgreSQL 15+ client):

```bash
export SUPABASE_DB_URL="postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
export APP_PASSWORD="<a long random password for the application login>"
bash deploy/deploy.sh          # schema, rules, views, reference data, security, ami_app login, demo dataset
```

The script prints the business date and the number of enrolments when it is done. To start over: `bash deploy/deploy.sh --fresh`.

The AMI schemas are not exposed through Supabase's REST API (only `public` is), and `06_security.sql` revokes everything
from `anon` and `authenticated`. The application reaches the data only through `ami_app`, which has no rights of its own.

## 2. Application on Streamlit Community Cloud

1. Push this repository to GitHub.
2. share.streamlit.io → **Create app** → the repository, branch `main`, main file `streamlit_app.py`.
3. *Advanced settings → Secrets*:

```toml
DATABASE_URL = "postgresql://ami_app.<project-ref>:<APP_PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
DEMO_MODE = "true"
DEMO_PASSWORD = "ami-demo"
```

`DEMO_MODE` shows the one-click role buttons on the sign-in page. The demo accounts use the password the dataset was generated with
(`--password`, default `ami-demo`).

## 3. Weekly reset and keep-alive (optional)

Supabase pauses free projects after a week without activity, and a demo looks best when its business date is recent.
`.github/workflows/reset-demo.yml` runs every Monday: it builds a scratch PostgreSQL in the runner, simulates the year up to today
(`seed/generate_dataset.py`) and reloads it into Supabase in one transaction.

In the GitHub repository: *Settings → Secrets and variables → Actions*

| Kind | Name | Value |
|---|---|---|
| Secret | `SUPABASE_DB_URL` | the `postgres` session-pooler URI from step 1 |
| Secret | `DEMO_PASSWORD` | the demo password (optional, default `ami-demo`) |
| Variable | `DEMO_RESET_ENABLED` | `true` |

Run it once by hand (*Actions → Reset demo data → Run workflow*) to check it.

## 4. Running locally

```bash
createdb ami_demo
(cd database && psql -v ON_ERROR_STOP=1 -d ami_demo -f build.sql)
psql -v ON_ERROR_STOP=1 -d ami_demo -f seed/demo_dataset.sql
pip install -r requirements.txt
DATABASE_URL=postgresql:///ami_demo streamlit run streamlit_app.py
```

Locally the app may connect as a superuser; it still switches to the user's role for every transaction, so permissions behave as
in production. Tests: `pip install -r requirements-dev.txt && pytest -q tests` (builds its own throw-away database).

## 5. Using it for real

The same code runs a real centre with three changes: set `DEMO_MODE = "false"`; create real accounts
(`insert into app.app_user …` then `select app.set_password('<user>', '<password>')` as the database owner); and clear the
`as_of_date` setting (`update ref.app_setting set setting_value = null where setting_key = 'as_of_date'`) so the business date is today.
