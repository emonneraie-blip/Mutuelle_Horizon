output "database" {
  value = snowflake_database.mutuelle.name
}

output "warehouses" {
  value = [module.ingest_wh.name, module.transform_wh.name, module.bi_wh.name]
}

output "roles" {
  value = [snowflake_account_role.ingest.name, snowflake_account_role.transform.name, snowflake_account_role.analyst.name]
}

output "service_users" {
  value = [snowflake_service_user.svc_ingest.name, snowflake_service_user.svc_transform.name]
}
