-- Two roles: migrations run as the owner; the app runs as keel_app, which cannot bypass RLS.
CREATE ROLE keel_owner LOGIN PASSWORD 'keel_owner' CREATEDB;
CREATE ROLE keel_app LOGIN PASSWORD 'keel_app' NOBYPASSRLS;
CREATE DATABASE keel OWNER keel_owner;
CREATE DATABASE keel_test OWNER keel_owner;
\c keel
CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS citext;
\c keel_test
CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF NOT EXISTS citext;
