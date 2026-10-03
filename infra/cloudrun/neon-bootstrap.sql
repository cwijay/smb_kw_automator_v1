-- Run once on the Neon database, as the Neon owner role, before the first deploy.
-- Same two-role model as local (backend/scripts/init-db.sql): migrations run as keel_owner; the app
-- runs as keel_app, which cannot bypass row-level security. Replace both passwords first.
CREATE ROLE keel_owner LOGIN PASSWORD 'CHANGE-ME-owner';
CREATE ROLE keel_app LOGIN PASSWORD 'CHANGE-ME-app' NOBYPASSRLS;
GRANT ALL ON SCHEMA public TO keel_owner;
GRANT USAGE ON SCHEMA public TO keel_app;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
