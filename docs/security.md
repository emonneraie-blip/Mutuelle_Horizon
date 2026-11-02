# Sécurité · Mutuelle Horizon Santé (owner : Eliott)

Principe : chacun n'a que les droits de sa tâche. Les humains et les machines ont des comptes séparés. Aucun secret n'est dans Git.

## 1. Comptes

| Compte | Type | Rôles | Authentification | Sert à |
|---|---|---|---|---|
| `lstefani` (Lucas) | humain, propriétaire du compte | ACCOUNTADMIN (bootstrap uniquement), `INGEST_ROLE` | mot de passe + MFA, clé RSA | bootstrap, développement de l'ingestion |
| `CLEMENT` | humain | `TRANSFORM_ROLE`, `ANALYST_ROLE` | mot de passe + MFA, clé RSA | développement dbt, dashboard |
| `ELIOTT` | humain | SYSADMIN, SECURITYADMIN, `ANALYST_ROLE` | mot de passe + MFA, clé RSA | Terraform en local, démo d'accès |
| `SVC_TERRAFORM` | service | SYSADMIN, SECURITYADMIN | clé RSA seule | Terraform en CI |
| `SVC_INGEST` | service | `INGEST_ROLE` | clé RSA seule | tâches d'ingestion lancées par Airflow |
| `SVC_TRANSFORM` | service | `TRANSFORM_ROLE` | clé RSA seule | `dbt build` lancé par Airflow |

Un compte de service (`TYPE = SERVICE`) n'a pas de mot de passe et ne peut pas se connecter à Snowsight. Chacun n'a qu'un seul rôle, donc il ne peut pas sortir de sa couche.

## 2. Un rôle par couche

| Rôle | Peut | Ne peut pas |
|---|---|---|
| `INGEST_ROLE` | utiliser `INGEST_WH`, créer et écrire `BRONZE` | lire SILVER / GOLD |
| `TRANSFORM_ROLE` | utiliser `TRANSFORM_WH` et `BI_WH`, lire `BRONZE`, écrire `SILVER` / `GOLD` / `OPS` | écrire `BRONZE` |
| `ANALYST_ROLE` (direction) | utiliser `BI_WH`, lire `GOLD.KPI_FRAUDE_QUOTIDIEN` | lire la liste nominative des factures, lire `BRONZE` |
| `REDGRAVE_GRADER` (prof) | lire `SILVER`, `GOLD`, `OPS` | lire `BRONZE` |

Qui donne quoi :
- Terraform crée les rôles, les rattache à SYSADMIN, et donne l'usage des entrepôts et de la base (`terraform/roles.tf`, `terraform/grader.tf`).
- Chaque rôle propriétaire d'une couche donne la lecture à la couche suivante. `INGEST_ROLE` ouvre BRONZE à `TRANSFORM_ROLE` (`ingestion/sql/bronze_ddl.sql`). dbt ouvre SILVER, GOLD et OPS à la prof, et le seul KPI à `ANALYST_ROLE`, à chaque `dbt build` (`dbt_project.yml`, `macros/grant_acces.sql`).

## 3. Preuve : accès autorisé et refusé (testé le 02/11 sur Snowflake)

```sql
USE ROLE ANALYST_ROLE;
USE SECONDARY ROLES NONE;     -- seulement les droits d'ANALYST_ROLE
USE WAREHOUSE BI_WH;

SELECT * FROM MUTUELLE_FRAUD.GOLD.KPI_FRAUDE_QUOTIDIEN;          -- autorisé : 9 lots
SELECT * FROM MUTUELLE_FRAUD.GOLD.MART_FACTURES_A_CONTROLER;     -- refusé
SELECT * FROM MUTUELLE_FRAUD.BRONZE.FACTURES_OPTIQUE;            -- refusé
```

| Requête | Résultat |
|---|---|
| KPI direction | autorisée, 9 lignes (un lot par jour) |
| Factures à contrôler | refusée : « Your primary role ANALYST_ROLE must have at least one privilege granted on TABLE … » |
| BRONZE (NIR) | refusée dès le schéma : pas d'USAGE sur `MUTUELLE_FRAUD.BRONZE` |

Leçon du test. Par défaut, Snowflake active **tous** les rôles d'un utilisateur dans une session (rôles secondaires). Sans `USE SECONDARY ROLES NONE`, un humain qui a aussi SYSADMIN lit BRONZE même après `USE ROLE ANALYST_ROLE`. Nos comptes de service n'ont qu'un rôle chacun : ils ne sont pas concernés.

## 4. Secrets : où ils vivent

| Secret | Où | Jamais |
|---|---|---|
| Clés privées personnelles (`rsa_key.p8`) | `~/keys/` sur le Mac de chacun | dans Git, dans une image, dans un message |
| Clés des comptes de service (`svc_ingest.p8`, `svc_transform.p8`) | `~/keys/mutuelle/` sur la machine de démo, montées **en lecture seule** dans les conteneurs | copiées dans une image |
| Clé `svc_terraform.p8` | Mac d'Eliott (réservée à un futur `terraform plan` en CI) | dans Git |
| `.env` (mot de passe Postgres local, webhook Discord, `NIR_SALT`) | `airflow/.env` et `.env` à la racine, ignorés par Git. Dans Airflow, `PGPASSWORD` et `NIR_SALT` passent en `private_environment` : jamais affichés dans l'interface | commités : seuls les `.env.example` le sont |
| `terraform.tfvars`, `*.tfstate` | Mac d'Eliott, ignorés par Git | commités |

Seules les clés **publiques** circulent. `.gitignore` bloque `*.p8`, `*.pem`, `*.pub`, `.env`, `*.tfvars` et `*.tfstate`. Contrôle avant le rendu : `git log -p | grep -i "private key"` ne renvoie rien.

## 5. Données sensibles

- **NIR** : présent en clair seulement dans BRONZE, qui n'est lisible que par `INGEST_ROLE` et `TRANSFORM_ROLE`. Dès SILVER, il est haché avec un sel secret : `SHA2(sel || nir)`. Sans sel, un NIR haché se retrouve facilement, parce que sa structure est connue.
- **Minimisation** : on ne charge des adhérents que ce que les règles utilisent (identifiant, formule, dates de contrat, statut), sans NIR, nom, e-mail, téléphone ni adresse. Le NIR n'arrive que par les factures et les décomptes NOEMIE. Le RPPS est réduit au numéro, à la profession, à la spécialité et au lieu d'exercice (code postal, commune), sans nom.
- **Données fictives** : adhérents, NIR et factures sont simulés. Les SIRET et RPPS réels ne servent jamais à désigner un vrai opticien ou un vrai médecin comme fraudeur.

## 6. Limites connues (et ce qu'on ferait en production)

| Limite du prototype | En production |
|---|---|
| Le state Terraform est local, sur le Mac d'Eliott | State distant verrouillé (HCP Terraform, bucket versionné) |
| Airflow tourne en root pour piloter Docker (raccourci de TD) | Tâches sur Kubernetes, rien en root |
| Les humains ont des rôles secondaires actifs par défaut | `ALTER USER … SET DEFAULT_SECONDARY_ROLES = ()` pour tous |
| Le NIR est en clair dans BRONZE | Hachage dès l'ingestion, ou masquage dynamique Snowflake |
| Un seul sel pour tout le projet, partagé à la main | Sel dans un coffre à secrets, avec rotation |
| Le sel est écrit dans le SQL compilé par dbt, donc visible dans l'historique des requêtes de `TRANSFORM_ROLE` | Hachage par une fonction sécurisée (secure UDF) qui lit le sel dans un secret Snowflake |
