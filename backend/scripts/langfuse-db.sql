-- Langfuse's own role and database on Keel's Postgres server (local dev). Idempotent: runs on a fresh
-- volume via docker-entrypoint-initdb.d, and `make langfuse` re-runs it against an existing one.
-- Separate role and database: Langfuse never touches Keel's tables, and Keel's roles can't read traces.
SELECT 'CREATE ROLE langfuse LOGIN PASSWORD ''langfuse'''
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'langfuse')\gexec
SELECT 'CREATE DATABASE langfuse OWNER langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
