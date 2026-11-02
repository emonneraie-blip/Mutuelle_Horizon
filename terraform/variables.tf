# Identifiant du compte DPNIFMK-WG18146 -> organization_name = "DPNIFMK", account_name = "WG18146"
variable "organization_name" {
  description = "Première partie de l'identifiant du compte (avant le tiret)"
  type        = string
}

variable "account_name" {
  description = "Deuxième partie de l'identifiant du compte (après le tiret)"
  type        = string
}

variable "user" {
  description = "Utilisateur qui lance Terraform : ELIOTT en local, SVC_TERRAFORM en CI"
  type        = string
}

variable "private_key_path" {
  description = "Chemin de la clé privée .p8. La clé n'est jamais commitée."
  type        = string
  default     = "~/keys/rsa_key.p8"
}

variable "lucas_user" {
  description = "Nom de l'utilisateur Snowflake de Lucas (propriétaire du compte)"
  type        = string
  default     = "lstefani"
}

variable "svc_ingest_public_key" {
  description = "Clé PUBLIQUE de SVC_INGEST (contenu de svc_ingest.pub, sans les lignes BEGIN/END)"
  type        = string
}

variable "svc_transform_public_key" {
  description = "Clé PUBLIQUE de SVC_TRANSFORM (contenu de svc_transform.pub, sans les lignes BEGIN/END)"
  type        = string
}
