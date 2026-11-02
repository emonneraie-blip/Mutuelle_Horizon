# Comptes de service : une machine = un compte, limité à sa couche, clé RSA uniquement (pas de mot de passe).

resource "snowflake_service_user" "svc_ingest" {
  provider          = snowflake.security
  name              = "SVC_INGEST"
  rsa_public_key    = var.svc_ingest_public_key
  default_role      = snowflake_account_role.ingest.name
  default_warehouse = module.ingest_wh.name
  comment           = "Tâches d'ingestion lancées par Airflow"
}

resource "snowflake_service_user" "svc_transform" {
  provider          = snowflake.security
  name              = "SVC_TRANSFORM"
  rsa_public_key    = var.svc_transform_public_key
  default_role      = snowflake_account_role.transform.name
  default_warehouse = module.transform_wh.name
  comment           = "dbt lancé par Airflow"
}

# Qui a quel rôle
resource "snowflake_grant_account_role" "svc_ingest_role" {
  provider  = snowflake.security
  role_name = snowflake_account_role.ingest.name
  user_name = snowflake_service_user.svc_ingest.name
}

resource "snowflake_grant_account_role" "svc_transform_role" {
  provider  = snowflake.security
  role_name = snowflake_account_role.transform.name
  user_name = snowflake_service_user.svc_transform.name
}

resource "snowflake_grant_account_role" "lucas_ingest" {
  provider  = snowflake.security
  role_name = snowflake_account_role.ingest.name
  user_name = var.lucas_user
}

resource "snowflake_grant_account_role" "clement_transform" {
  provider  = snowflake.security
  role_name = snowflake_account_role.transform.name
  user_name = "CLEMENT"
}

resource "snowflake_grant_account_role" "clement_analyst" {
  provider  = snowflake.security
  role_name = snowflake_account_role.analyst.name
  user_name = "CLEMENT"
}

# Eliott a ANALYST_ROLE pour la démo « accès refusé »
resource "snowflake_grant_account_role" "eliott_analyst" {
  provider  = snowflake.security
  role_name = snowflake_account_role.analyst.name
  user_name = "ELIOTT"
}
