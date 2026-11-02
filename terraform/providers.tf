# Two connections to the same account, with two different roles:
# SYSADMIN creates warehouses and databases, SECURITYADMIN creates roles and grants.
provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.user
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(pathexpand(var.private_key_path))
  role              = "SYSADMIN"
}

provider "snowflake" {
  alias             = "security"
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.user
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(pathexpand(var.private_key_path))
  role              = "SECURITYADMIN"
}
