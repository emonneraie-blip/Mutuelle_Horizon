# Accès en lecture pour la prof (rôle REDGRAVE_GRADER, créé au TD ingestion).
# Décision d'équipe : la prof lit SILVER, GOLD et OPS, jamais BRONZE (qui contient le NIR en clair).
# Terraform donne seulement l'accès à la base et à un entrepôt. Les droits de lecture sur les tables
# sont posés par dbt (Clément) à chaque `dbt build`, uniquement sur les couches autorisées.

resource "snowflake_grant_privileges_to_account_role" "grader_db" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.mutuelle.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "grader_warehouse" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["USAGE", "MONITOR"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.bi_wh.name
  }
}
