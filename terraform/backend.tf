# State distant sur HCP Terraform : versionné, verrouillé, hors de Git.
# Execution Mode = Local : le plan tourne sur notre machine, HCP ne stocke que le state.
terraform {
  cloud {
    organization = "mutuelle-horizon"
    workspaces {
      name = "mutuelle-fraud"
    }
  }
}
