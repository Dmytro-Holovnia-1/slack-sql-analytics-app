DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chatbot_ro') THEN
        CREATE ROLE chatbot_ro LOGIN PASSWORD 'chatbot_ro_password';
    END IF;
END $$;

DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM chatbot_ro', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO chatbot_ro', current_database());
END $$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO chatbot_ro;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM chatbot_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chatbot_ro;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM chatbot_ro;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM chatbot_ro;

ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM chatbot_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO chatbot_ro;
ALTER ROLE chatbot_ro SET search_path = public;
