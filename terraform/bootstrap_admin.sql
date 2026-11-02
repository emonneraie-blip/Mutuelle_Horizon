-- ============================================================================================================
-- Mutuelle Horizon Santé · bootstrap ADMIN (the only manual step of the platform)
-- Run ONCE by Lucas (account owner, ACCOUNTADMIN) in Snowsight, BEFORE the first `terraform apply`.
-- Everything else (database, warehouses, roles, service users SVC_INGEST / SVC_TRANSFORM, grants) is Terraform.
-- Paste only PUBLIC keys (content of the .pub file, without the -----BEGIN/END----- lines). Never a private key.
-- ============================================================================================================
USE ROLE ACCOUNTADMIN;

-- 1. Terraform's own identity: a SERVICE user (no password, cannot log into Snowsight), RSA key only.
CREATE USER IF NOT EXISTS SVC_TERRAFORM
  TYPE = SERVICE
  RSA_PUBLIC_KEY = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAx0GQG3VpFxyZwB3QEd2RulFRx6z66evguiFnFGUP69mLr8IK9+wCMvo8irbcGPHuH1EO3t3az66tAKSNFmbqiUHtfUJqZ9sulL+N7MzHmGOKxtLEIzlfzSuaHNd+qLC1cP8BkvuCNbdE8VKwxsn3aeRV9bAp5Yk9WMIdwV+YPMmwxJCmLa/Jy0vNUGLOpstQqTO3QshfcmofwRSWktuPQkAvmz8dww+2q/ULL5hZSuiotNejTmA0mNcwbUdn9TRqDSJdfcWqr35XsYqvT2pgLCjhoBwLGYl0qDjNtSiEyMOYXM/1Bxmqm71DbMcDQy6hdQPGsSu/Bajx3iDt92h4kQIDAQAB'
  DEFAULT_ROLE = SYSADMIN
  COMMENT = 'Terraform (GitHub Actions + Eliott). Owner: Eliott';
GRANT ROLE SYSADMIN      TO USER SVC_TERRAFORM;   -- creates database, warehouses
GRANT ROLE SECURITYADMIN TO USER SVC_TERRAFORM;   -- creates roles, service users, grants

-- 2. Human accounts (one per person, never shared). Type a temporary password in Snowsight only (never commit it),
--    sent to the person by DM, changed at first login. RSA key for the CLI.
CREATE USER IF NOT EXISTS ELIOTT
  TYPE = PERSON
  PASSWORD = 'TEMP_PASSWORD_TO_FILL_IN_SNOWSIGHT_ONLY' MUST_CHANGE_PASSWORD = TRUE
  RSA_PUBLIC_KEY = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArMQYIxc1bWBXfuFtZ4yPsOaQNUs0I6xOu/cYIla56O8KMJSefHZ6M6hu0cnYCugiW7KDXmbWl4VdO0CMq74CrAGfwtqdP/xUZxLnrrh6FAI6/ylZ/dnFm+wlrd8+2zi8Rfez11+zMqhcE0lDJvsNUDk9jnbV/0a8Q0Vxa2ZglpR2fekNRix/svG5T9JqVWUT7w6CpwXJB6WGwDCjRMVIgqZZ999TmPhpw/jS9HRewlFwrz3dN302NKSMyB3dlXtxYWtBZ2dPR23hA+I5Zm5e5UR9rFJCzl0ODq4EOOpXtbsLUa+McTarxEtB54g9mN1KrM2zkQWwygXZ2ZpPrClhUQIDAQAB'
  DEFAULT_ROLE = SYSADMIN
  COMMENT = 'Eliott Monneraie - platform owner';
GRANT ROLE SYSADMIN      TO USER ELIOTT;
GRANT ROLE SECURITYADMIN TO USER ELIOTT;

CREATE USER IF NOT EXISTS CLEMENT
  TYPE = PERSON
  PASSWORD = 'TEMP_PASSWORD_TO_FILL_IN_SNOWSIGHT_ONLY' MUST_CHANGE_PASSWORD = TRUE
  RSA_PUBLIC_KEY = 'PASTE_CLEMENT_PUBLIC_KEY'
  DEFAULT_ROLE = PUBLIC                           -- Terraform grants TRANSFORM_ROLE + ANALYST_ROLE, then: ALTER USER CLEMENT SET DEFAULT_ROLE = TRANSFORM_ROLE
  COMMENT = 'Clément Badalucco - transformation owner';

-- 3. Cost guardrail (needs ACCOUNTADMIN, so it lives here and not in Terraform).
CREATE RESOURCE MONITOR IF NOT EXISTS MUTUELLE_MONITOR
  WITH CREDIT_QUOTA = 20 FREQUENCY = MONTHLY START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 50 PERCENT DO NOTIFY
           ON 80 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND;
-- Attached to the 3 project warehouses once Terraform has created them (step 4).

-- 4. AFTER the first `terraform apply` (re-run only this block):
-- ALTER WAREHOUSE INGEST_WH    SET RESOURCE_MONITOR = MUTUELLE_MONITOR;
-- ALTER WAREHOUSE TRANSFORM_WH SET RESOURCE_MONITOR = MUTUELLE_MONITOR;
-- ALTER WAREHOUSE BI_WH        SET RESOURCE_MONITOR = MUTUELLE_MONITOR;
-- ALTER USER CLEMENT SET DEFAULT_ROLE = TRANSFORM_ROLE DEFAULT_WAREHOUSE = TRANSFORM_WH;

-- Check
SHOW USERS LIKE 'SVC_%';
SHOW GRANTS TO USER SVC_TERRAFORM;
