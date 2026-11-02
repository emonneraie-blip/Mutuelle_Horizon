# terraform/ · owner Eliott

0. `bootstrap_admin.sql`: run once by Lucas (ACCOUNTADMIN). Creates `SVC_TERRAFORM`, `ELIOTT`, `CLEMENT`, the resource monitor.
1. `main.tf` + `modules/warehouse/` (reuse the RED-401 lab): database `MUTUELLE_FRAUD`, warehouses `INGEST_WH` / `TRANSFORM_WH` / `BI_WH`
   (XSMALL, auto_suspend 60), roles `INGEST_ROLE` / `TRANSFORM_ROLE` / `ANALYST_ROLE` (granted to SYSADMIN),
   service users `SVC_INGEST` / `SVC_TRANSFORM` (`snowflake_service_user`, public keys as variables), grants
   (USAGE + CREATE SCHEMA on the database for INGEST/TRANSFORM, USAGE on their warehouse, project roles to the human users,
   read access for `REDGRAVE_GRADER`).
2. Remote state on HCP Terraform (`cloud {}` block, free tier). `terraform.tfvars` and `*.tfstate` are gitignored.
3. `.github/workflows/ci.yml`: `fmt -check`, `validate`, `plan` on each PR + a Python job (`generate.py` then `validate.py`).
   Do NOT put `${{ runner.temp }}` in the job-level `env:` (invalid context). Write the key inside the step:

```yaml
      - name: Write Snowflake key
        run: |
          printf '%s\n' "${{ secrets.SF_PRIVATE_KEY }}" > "$RUNNER_TEMP/rsa_key.p8"
          echo "TF_VAR_private_key_path=$RUNNER_TEMP/rsa_key.p8" >> "$GITHUB_ENV"
```

---

# Terraform · plateforme Snowflake (owner : Eliott)

## Ce que Terraform crée

| Objet | Nom |
|---|---|
| Base | `MUTUELLE_FRAUD` |
| Entrepôts XSMALL, auto-suspend 60 s | `INGEST_WH`, `TRANSFORM_WH`, `BI_WH` |
| Rôles (rattachés à SYSADMIN) | `INGEST_ROLE`, `TRANSFORM_ROLE`, `ANALYST_ROLE` |
| Comptes de service (clé RSA seule) | `SVC_INGEST`, `SVC_TRANSFORM` |
| Accès prof | `REDGRAVE_GRADER` : lecture sur tout ce qui sera créé dans `MUTUELLE_FRAUD` |

Les schémas ne sont pas créés ici : `BRONZE` est créé par `INGEST_ROLE`, `SILVER`/`GOLD`/`OPS` par `TRANSFORM_ROLE`.

## Étapes manuelles (à citer à l'oral)

1. Lucas exécute `bootstrap_admin.sql` (ACCOUNTADMIN, déjà dans le repo), étapes 1 à 3 avant le premier `apply`, puis le bloc 4 après (resource monitor rattaché aux 3 entrepôts).
2. Clés RSA générées sur chaque machine. Seules les clés publiques circulent.
3. (Option) Compte HCP Terraform pour le state distant : voir `backend.tf.example`.

## Lancer

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars    # puis remplir
terraform init
terraform fmt -check && terraform validate
terraform plan        # relire : rien ne doit être détruit
terraform apply
terraform plan        # doit afficher "No changes" (pas de dérive)
```

## Arrêt après la note

```bash
terraform destroy
```

Puis, dans Snowsight, avec ACCOUNTADMIN : `DROP USER SVC_TERRAFORM;` et `DROP RESOURCE MONITOR MUTUELLE_MONITOR;`.

