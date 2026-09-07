\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ownsis') THEN
        CREATE ROLE ownsis LOGIN PASSWORD 'ownsis' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ownsis_worker') THEN
        CREATE ROLE ownsis_worker LOGIN PASSWORD 'ownsis_worker' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE ownsis TO ownsis;
GRANT USAGE ON SCHEMA public TO ownsis;
GRANT CONNECT ON DATABASE ownsis TO ownsis_worker;
GRANT USAGE ON SCHEMA public TO ownsis_worker;

-- Alembic grants each table and column privilege explicitly. Broad default
-- privileges would silently give future tables more authority than reviewed.
