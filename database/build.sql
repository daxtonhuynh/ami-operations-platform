/* =====================================================================================
   build.sql - create the AMI Education database (structure, rules, reference data, security)
       createdb ami
       psql -v ON_ERROR_STOP=1 -d ami -f build.sql
   Then load ONE data set:
       psql -v ON_ERROR_STOP=1 -d ami -f ../seed/demo_dataset.sql     # 12-month operating demo for the application
   or  psql -v ON_ERROR_STOP=1 -d ami -f 07_test_fixture.sql          # small fixture for the tests
       psql -v ON_ERROR_STOP=1 -d ami -f 08_tests.sql                 # 70 business-rule tests (rolled back)
   Requires PostgreSQL 15+ with the pgcrypto and btree_gist extensions (both bundled with PostgreSQL and enabled on Supabase).
   ===================================================================================== */
\set ON_ERROR_STOP 1
\echo '01 schema'
\ir 01_schema.sql
\echo '02 functions (business rules and application API)'
\ir 02_functions.sql
\echo '03 views (reporting + control checks)'
\ir 03_views.sql
\echo '04 comments (data dictionary)'
\ir 04_comments.sql
\echo '05 reference data (chart of accounts, P&L layout, code tables, controls)'
\ir 05_seed_reference.sql
\echo '06 security (roles, grants, row-level security)'
\ir 06_security.sql
\echo 'Build complete.'
