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
