/* =====================================================================================
   deploy/supabase_setup.sql - give the application its own login (run once, after database/build.sql)
       psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -v app_password='<strong password>' -f deploy/supabase_setup.sql
   ami_app has no rights of its own (NOINHERIT). It can only check a password, read the business date and switch to one
   of the five group roles, which is what the application does at the start of every transaction.
   ===================================================================================== */
\set ON_ERROR_STOP 1
alter role ami_app with login noinherit password :'app_password';
alter role ami_app set statement_timeout = '30s';
alter role ami_app set idle_in_transaction_session_timeout = '60s';
\echo 'ami_app can log in. Connect the app with DATABASE_URL=postgresql://ami_app.<project-ref>:<password>@<pooler-host>:5432/postgres'
