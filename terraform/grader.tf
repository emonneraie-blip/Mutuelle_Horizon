# Accès en lecture pour la prof (rôle REDGRAVE_GRADER, créé au TD ingestion).
# Les schémas et tables n'existent pas encore : on donne des droits « futurs »,
# appliqués automatiquement à chaque schéma et chaque table créés ensuite dans MUTUELLE_FRAUD.

resource "snowflake_grant_privileges_to_account_role" "grader_db" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.mutuelle.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "grader_future_schemas" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.mutuelle.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "grader_future_tables" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.mutuelle.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "grader_future_views" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = snowflake_database.mutuelle.name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "grader_warehouses" {
  provider          = snowflake.security
  account_role_name = "REDGRAVE_GRADER"
  privileges        = ["USAGE", "MONITOR"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = module.bi_wh.name
  }
}
