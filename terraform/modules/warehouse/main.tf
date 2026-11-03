# Module : un entrepôt Snowflake avec nos règles de coût (arrêt après 60 s, démarrage à la demande).
terraform {
  required_providers {
    snowflake = { source = "snowflakedb/snowflake" }
  }
}

variable "name" { type = string }
variable "size" { type = string }
variable "comment" {
  type    = string
  default = ""
}

resource "snowflake_warehouse" "this" {
  name                = var.name
  warehouse_size      = var.size
  auto_suspend        = 60 # stop after 60 s idle: no credits burnt overnight
  auto_resume         = true
  initially_suspended = true
  comment             = var.comment

  # Le resource monitor est rattaché à la main par ACCOUNTADMIN (bootstrap_admin.sql, bloc 4) :
  # Terraform ne doit pas le retirer au prochain apply.
  lifecycle {
    ignore_changes = [resource_monitor]
  }
}

output "name" {
  value = snowflake_warehouse.this.name
}
