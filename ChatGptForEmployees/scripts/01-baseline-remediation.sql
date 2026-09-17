-- REVIEWED AGAINST IMAGE sha256:570a872d2fde8f1bc4a147634810941103c14697270f0f2918c5aa7d8201cac5
-- LOCAL REHEARSAL FIRST. Dev requires a fresh verified backup, stopped writers,
-- owner privileges, and a fresh catalog comparison against the captured inputs.
-- This file DOES NOT mark any migration applied and DOES NOT run migrate deploy.
--
-- REQUIRES an explicit -v target_env=dev argument. Missing, blank, "test", and
-- "prod" values all abort before any DDL runs (see the romchat.target_env
-- guard below). An explicit "dev" argument expresses operator INTENT only --
-- it is not proof the connection itself is to dev. Verify PGHOST/PGDATABASE
-- and the connected role against the dev server separately before running
-- this script; see REVIEW-AND-CUTOVER.md section 2 for the supported
-- invocation and its limitations.
--
-- Run using:
--   psql -X -v ON_ERROR_STOP=1 -v target_env=dev -f 01-baseline-remediation.sql

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog, public;

-- psql does NOT interpolate :'variables' inside a dollar-quoted DO $$ ... $$
-- body. set_config() is called here, OUTSIDE any DO block (where :'target_env'
-- IS textually substituted by psql before the statement is sent to the
-- server), then read back inside the DO block below via current_setting().
--
-- If target_env was never passed on the command line, psql leaves the
-- quoted-literal form :'target_env' completely unsubstituted, which is not
-- valid SQL inside set_config()'s argument list. That raises a syntax error
-- here, and \set ON_ERROR_STOP on aborts the script immediately -- before any
-- DDL below runs and before this transaction can commit anything.
SELECT set_config('romchat.target_env', :'target_env', true);

DO $$
BEGIN
    IF current_setting('romchat.target_env', true) IS DISTINCT FROM 'dev' THEN
        RAISE EXCEPTION 'Wrong target environment; remediation aborted';
    END IF;
    -- Secondary check only. Every environment's database is named "litellm",
    -- so this does not by itself prove which environment this connection is
    -- on -- that's why the target_env guard above exists. dev_rehearsal is
    -- the database name used by this task's own local Docker fixture.
    IF current_database() NOT IN ('litellm', 'dev_rehearsal') THEN
        RAISE EXCEPTION 'Unexpected database; remediation aborted';
    END IF;
    IF to_regclass('public._prisma_migrations') IS NOT NULL THEN
        RAISE EXCEPTION 'Migration history now exists; re-audit before proceeding';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN
            ('LiteLLM_UserTable','LiteLLM_VerificationToken','LiteLLM_SpendLogs')
        AND NOT pg_has_role(current_user,c.relowner,'USAGE')
    ) THEN
        RAISE EXCEPTION 'Must execute as the table owner or an authorized owner role';
    END IF;
END $$;

-- Fail on contention before making changes; no live queries should be admitted
-- during the approved maintenance window.
LOCK TABLE public."LiteLLM_UserTable", public."LiteLLM_VerificationToken",
    public."LiteLLM_SpendLogs" IN ACCESS EXCLUSIVE MODE;

CREATE TABLE public."LiteLLM_CredentialsTable" (
    "credential_id" TEXT NOT NULL,
    "credential_name" TEXT NOT NULL,
    "credential_values" JSONB NOT NULL,
    "credential_info" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by" TEXT NOT NULL,
    CONSTRAINT "LiteLLM_CredentialsTable_pkey" PRIMARY KEY ("credential_id")
);

ALTER TABLE public."LiteLLM_UserTable" ADD COLUMN "sso_user_id" TEXT;
ALTER TABLE public."LiteLLM_VerificationToken"
    ADD COLUMN "organization_id" TEXT,
    ADD COLUMN "created_by" TEXT,
    ADD COLUMN "updated_by" TEXT;
ALTER TABLE public."LiteLLM_SpendLogs"
    ADD COLUMN "messages" JSONB DEFAULT '{}',
    ADD COLUMN "response" JSONB DEFAULT '{}';

CREATE UNIQUE INDEX "LiteLLM_CredentialsTable_credential_name_key"
    ON public."LiteLLM_CredentialsTable"("credential_name");
CREATE UNIQUE INDEX "LiteLLM_UserTable_sso_user_id_key"
    ON public."LiteLLM_UserTable"("sso_user_id");
ALTER TABLE public."LiteLLM_VerificationToken"
    ADD CONSTRAINT "LiteLLM_VerificationToken_organization_id_fkey"
    FOREIGN KEY ("organization_id")
    REFERENCES public."LiteLLM_OrganizationTable"("organization_id")
    ON DELETE SET NULL ON UPDATE CASCADE;
COMMIT;
