# Les trois rôles du pipeline. Ils sont rattachés à SYSADMIN : l'admin garde la main sur tout.

resource "snowflake_account_role" "ingest" {
  provider = snowflake.security
  name     = "INGEST_ROLE"
  comment  = "Écrit BRONZE"
}

resource "snowflake_account_role" "transform" {
  provider = snowflake.security
  name     = "TRANSFORM_ROLE"
  comment  = "Lit BRONZE, écrit SILVER / GOLD / OPS, possède le dashboard"
}

resource "snowflake_account_role" "analyst" {
  provider = snowflake.security
  name     = "ANALYST_ROLE"
  comment  = "Direction : lit uniquement les KPI agrégés"
}

resource "snowflake_grant_account_role" "ingest_to_sysadmin" {
  provider         = snowflake.security
  role_name        = snowflake_account_role.ingest.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "transform_to_sysadmin" {
  provider         = snowflake.security
  role_name        = snowflake_account_role.transform.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "analyst_to_sysadmin" {
  provider         = snowflake.security
  role_name        = snowflake_account_role.analyst.name
  parent_role_name = "SYSADMIN"
}

# ---- INGEST_ROLE : son entrepôt + droit de créer le schéma BRONZE ----
resource "snowflake_grant_privileges_to_account_role" "ingest_wh" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.ingest.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.ingest_wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ingest_db" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.ingest.name
  privileges        = ["USAGE", "CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.mutuelle.name
  }
}

# ---- TRANSFORM_ROLE : son entrepôt, BI_WH (dashboard) + droit de créer SILVER / GOLD / OPS ----
# La lecture de BRONZE lui est donnée par INGEST_ROLE, propriétaire de BRONZE (job bootstrap_bronze).
resource "snowflake_grant_privileges_to_account_role" "transform_wh" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.transform.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.transform_wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "transform_bi_wh" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.transform.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.bi_wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "transform_db" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.transform.name
  privileges        = ["USAGE", "CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.mutuelle.name
  }
}

# ---- ANALYST_ROLE : BI_WH + la base. La lecture de GOLD.KPI_FRAUDE_QUOTIDIEN lui est donnée par
#      TRANSFORM_ROLE (dbt). Elle ne voit RIEN d'autre : c'est la démo « accès refusé ».
resource "snowflake_grant_privileges_to_account_role" "analyst_bi_wh" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.analyst.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.bi_wh.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "analyst_db" {
  provider          = snowflake.security
  account_role_name = snowflake_account_role.analyst.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.mutuelle.name
  }
}
