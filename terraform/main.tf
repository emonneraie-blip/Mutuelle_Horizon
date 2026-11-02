# Mutuelle Horizon Santé · la plateforme Snowflake, déclarée en code.
# terraform plan = voir ce qui va changer      terraform apply = appliquer

# 1. La base du projet. Les schémas BRONZE / SILVER / GOLD / OPS sont créés par les rôles
#    qui les possèdent (INGEST_ROLE et TRANSFORM_ROLE) : chaque rôle possède sa couche.
resource "snowflake_database" "mutuelle" {
  name    = "MUTUELLE_FRAUD"
  comment = "Détection de fraude optique - géré par Terraform, ne pas modifier à la main"
}

# 2. Trois entrepôts XSMALL, un par usage, pour voir le coût de chaque usage (FinOps)
module "ingest_wh" {
  source  = "./modules/warehouse"
  name    = "INGEST_WH"
  size    = "XSMALL"
  comment = "Jobs d'ingestion (SVC_INGEST)"
}

module "transform_wh" {
  source  = "./modules/warehouse"
  name    = "TRANSFORM_WH"
  size    = "XSMALL"
  comment = "dbt (SVC_TRANSFORM)"
}

module "bi_wh" {
  source  = "./modules/warehouse"
  name    = "BI_WH"
  size    = "XSMALL"
  comment = "Dashboard Streamlit et analystes"
}
