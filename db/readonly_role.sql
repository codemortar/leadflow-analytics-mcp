-- Role used for every model-generated query. Run as a superuser or the schema owner:
--   psql -v readonly_password="'...'" -f db/readonly_role.sql
-- psql variables don't expand inside DO blocks, so the password is set with ALTER ROLE below.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'leadflow_readonly') THEN
        CREATE ROLE leadflow_readonly LOGIN;
    END IF;
END
$$;
ALTER ROLE leadflow_readonly PASSWORD :readonly_password;

-- Backstop if the application guard misses something: read-only by default, short timeout.
ALTER ROLE leadflow_readonly SET default_transaction_read_only = on;
ALTER ROLE leadflow_readonly SET statement_timeout = '5s';
ALTER ROLE leadflow_readonly SET search_path = leadflow;

REVOKE ALL ON SCHEMA leadflow FROM PUBLIC;
GRANT USAGE ON SCHEMA leadflow TO leadflow_readonly;
GRANT SELECT ON
    leadflow.affiliates, leadflow.campaigns, leadflow.buyers, leadflow.leads,
    leadflow.pings, leadflow.sales, leadflow.returns
TO leadflow_readonly;
-- Deliberately no grant on leadflow.staff_accounts.
