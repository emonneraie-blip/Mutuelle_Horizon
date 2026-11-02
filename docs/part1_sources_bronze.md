# Partie 1 · Sources → BRONZE (owner : Lucas)

Le tronçon **sources → bronze** du pipeline « Mutuelle Horizon Santé — détection de fraude optique » :

```
data_generator/   generate.py (données réalistes + fraudes + corrigés)   validate.py (spécification exécutable)
                  ref/ (extraits SIRENE / RPPS réels figés, sans noms)
ingestion/        jobs Python (1 job = 1 source), sql/bronze_ddl.sql, Dockerfile, requirements.txt figé
docs/             contracts.md (contrat bronze ↔ silver, règles de fraude), ce runbook
docker-compose.crm.yml   Postgres du CRM (source opérationnelle)
.env.example      variables à copier dans .env (jamais commité)
```

## Décisions de l'équipe (review du 02/11)

| Sujet | Décision |
|---|---|
| F2 « sans décompte NOEMIE » | évaluée seulement quand `date_reception <= batch_date - 2 jours` (donc le matin de J+3, quand tourne le lot J+2), avec les fichiers NOEMIE reçus jusqu'à `batch_date`. Avant : statut **EN_ATTENTE**. Avec 1 jour de grâce, `validate.py` mesure 23 faux positifs le matin de l'incident du 30/10 ; avec 2 jours, 0 |
| Données personnelles | `BRONZE.ADHERENTS` = identifiant, formule, dates de contrat, statut, `UPDATED_AT`. Ni NIR, ni nom, prénom, naissance, e-mail, téléphone, code postal, ville (restent dans le CRM source). Le seul NIR dans Snowflake est celui de la facture (F2) |
| Opticiens réels | vrai SIRET (vérifié par la vraie API SIRENE), **nom toujours fictif** |
| Références | extraits SIRENE / RPPS figés dans `data_generator/ref/` : même seed = mêmes fichiers sur toutes les machines |
| Jeu officiel | `--seed 42`, incident NOEMIE du 30/10 inclus par défaut, ≥ 5 fraudes par règle, une F5 le 04/11, 1 facture invalide par jour (quarantaine) |
| Démo | préchargement jusqu'au **03/11 inclus** ; jeudi 5, « Trigger » → le run traite le **04/11** |
| Ordre de chargement | d'abord `run_day` jusqu'au 03/11 (Clément développe dbt dessus) ; quand le DAG et dbt sont prêts : `reset_demo` (SIRENE / RPPS conservés) puis backfill Airflow |
| Remise à zéro | `jobs.reset_demo` : `TRUNCATE` (efface aussi la mémoire de chargement de COPY, contrairement à `DELETE`) |

## Ce qui a été testé (et ce qui ne l'a pas été)

| Testé | Résultat |
|---|---|
| Générateur + `validate.py --each-day`, seeds 1, 7, 42, 123, 2026, mess `medium` et `high` | chaque matin : 100 % de rappel sur les règles évaluables, 0 faux positif, quarantaine exacte ; ≥ 5 fraudes par règle, F5 le dernier jour |
| Délai de grâce F2 (seed 42) | 0 jour : faux positifs tous les matins · 1 jour : 23 le 30/10 · **2 jours : 0** |
| Reproductibilité | même seed + mêmes références → fichiers identiques au bit près |
| `seed_postgres` + requête incrémentale sur un vrai Postgres 16 | OK, rejeu idempotent |
| Détection du schema drift (nouvelle colonne) | le job s'arrête avant de charger, statut `SCHEMA_DRIFT` |
| Extraction RPPS sur un fichier au format officiel | OK (filtre ophtalmologie, dédoublonnage, sans les noms) |
| `docker build`, API SIRENE (catalogue), téléchargement RPPS — Mac de démo, 02/11 | OK : 400 opticiens actifs, 2,3 M lignes RPPS lues → 8 968 ophtalmologues, sans noms |
| **Chargement réel sur Snowflake** (`SVC_INGEST` / `INGEST_ROLE` / `INGEST_WH`), 02/11 | `bootstrap_bronze` OK ; historique 2 257 factures + 2 257 décomptes ; CRM 8 000 adhérents puis +20 / jour ; RPPS 8 968 ; jours 26/10 → 03/11 chargés |
| Contrôles dans BRONZE après chargement | 3 848 lignes de factures / 3 837 `id_demande` (11 renvois techniques), 3 802 décomptes, 8 180 adhérents ; SIRENE : 80 SIRET trouvés et actifs, 3 introuvables (= les faux SIRET F4) ; `LOAD_AUDIT` sans erreur |
| Incident NOEMIE du 30/10 | `NO_FILE` (avertissement, pas d'échec) le 30/10, puis 318 décomptes le 31/10 (rattrapage) |
| **Idempotence** (rejeu du 27/10 après le 03/11) | factures et NOEMIE `ALREADY_LOADED` (0 ligne), CRM `MERGE: 0 inserted, 0 updated`, SIRENE 0 appel |
| `reset_demo` (TRUNCATE + stage + CRM) | SQL relu et simulé, **pas encore exécuté** : à faire avant la première répétition |

## Pas à pas

Toutes les commandes se lancent à la racine du repo, sur la machine de démo (Mac de Lucas).

### 0. Prérequis (une fois)

```bash
# clés des comptes de service, sur la machine de démo — les clés privées ne quittent jamais ~/keys/mutuelle
mkdir -p ~/keys/mutuelle
for k in svc_ingest svc_transform; do
  openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/keys/mutuelle/$k.p8 -nocrypt
  openssl rsa -in ~/keys/mutuelle/$k.p8 -pubout -out ~/keys/mutuelle/$k.pub
done
cat ~/keys/mutuelle/*.pub            # clés PUBLIQUES à donner à Eliott (variables Terraform)
cp .env.example .env                 # SNOWFLAKE_USER=SVC_INGEST, SNOWFLAKE_PRIVATE_KEY_FILE=/secrets/svc_ingest.p8
docker build -t fraud-ingest:1.0.0 ingestion/
```

Raccourci pour lancer un job dans le conteneur (mêmes montages que dans le DAG Airflow) — à recoller dans chaque nouveau terminal :

```bash
run() { docker run --rm --env-file .env -v "$PWD/data:/data" -v "$HOME/keys/mutuelle:/secrets:ro" fraud-ingest:1.0.0 python -m "$@"; }
```

### 1. Figer les références réelles (UNE seule fois, internet, pas besoin de Snowflake)

```bash
run jobs.fetch_sirene catalogue --departements 75 92 93 94 --max 400   # vrais opticiens actifs, sans nom
run jobs.load_rpps --extract-only                                     # ~800 Mo lus en streaming, ophtalmos, sans nom
mkdir -p data_generator/ref && cp data/ref/opticiens_sirene.csv data/ref/ophtalmos_rpps.csv data_generator/ref/
git add data_generator/ref                                            # versionnés : plus besoin de les refaire
```

### 2. Générer et valider le jeu officiel

```bash
python3 data_generator/generate.py --seed 42             # 10 jours du 26/10 au 04/11 + 24 mois d'historique + incident du 30/10
python3 data_generator/validate.py --data data --each-day
```

Attendu : `Synthetic references used: {'opticiens': False, 'prescripteurs': False}` puis `VALIDATION OK`. `generate.py` refuse de tourner sans les références figées (sauf `--allow-synthetic`, réservé à la CI). `validate.py` affiche aussi l'`id_demande` de la F5 du 04/11 à ouvrir pendant la démo.

### 3. CRM Postgres (la source opérationnelle)

```bash
docker compose -f docker-compose.crm.yml up -d --wait     # --wait : attend que Postgres soit prêt (sinon « server closed the connection »)
run jobs.seed_postgres --date history                   # 8 000 adhérents, joue le rôle de l'application CRM
```

### 4. Créer la couche bronze (après le Terraform d'Eliott)

```bash
run jobs.bootstrap_bronze
```

`bootstrap_bronze` utilise `CREATE TABLE IF NOT EXISTS` : il ne modifie **jamais** une table qui existe déjà. Si `BRONZE.ADHERENTS` a été créée avant la minimisation (avec NIR, nom, etc.), la supprimer d'abord, puis relancer le bootstrap (le prochain `load_adherents_incremental` refait un chargement complet, watermark 1900-01-01) :

```sql
USE ROLE INGEST_ROLE;
DROP TABLE IF EXISTS MUTUELLE_FRAUD.BRONZE.ADHERENTS_STG;
DROP TABLE IF EXISTS MUTUELLE_FRAUD.BRONZE.ADHERENTS;
```

### 5. Charger l'historique et les références

```bash
run jobs.load_invoices --date history
run jobs.load_noemie --date history
run jobs.load_adherents_incremental       # 1er run = chargement complet (watermark 1900-01-01)
run jobs.load_rpps --reuse-extract        # charge l'extrait figé (le même que celui du générateur)
```

### 6. Charger les jours jusqu'au 03/11 inclus

**Maintenant**, à la main avec `run_day`, pour que Clément puisse développer dbt sur BRONZE :

```bash
for d in 2026-10-26 2026-10-27 2026-10-28 2026-10-29 2026-10-30 2026-10-31 2026-11-01 2026-11-02 2026-11-03; do
  run jobs.run_day --date $d --simulate-crm
done
```

Le 04/11 n'est **pas** chargé : c'est le run live de jeudi. **Plus tard**, quand le DAG et dbt sont prêts : `reset_demo --yes` (SIRENE / RPPS conservés, pas besoin de l'API), puis rechargement par le **backfill Airflow** d'Eliott (dates logiques du 27/10 au 04/11 : chaque run traite la veille), pour garder dans l'historique Airflow le run rouge du 30/10 puis le vert du 31/10. `run_day` enchaîne : activité CRM du jour → incrémental adhérents → factures → NOEMIE → vérification SIRENE des nouveaux SIRET.

Vérifications dans Snowsight :

```sql
SELECT JOB, BATCH_DATE, STATUS, FILES_LOADED, ROWS_LOADED, ENDED_AT FROM MUTUELLE_FRAUD.BRONZE.LOAD_AUDIT ORDER BY ENDED_AT DESC;
SELECT _BATCH_DATE, COUNT(*), COUNT(DISTINCT ID_DEMANDE) FROM MUTUELLE_FRAUD.BRONZE.FACTURES_OPTIQUE GROUP BY 1 ORDER BY 1;
SELECT FOUND, COUNT(*) FROM MUTUELLE_FRAUD.BRONZE.SIRENE_ETABLISSEMENTS GROUP BY 1;   -- FALSE = uniquement les faux SIRET (F4)
```

**Preuve d'idempotence** (à montrer à l'oral) : relancer `run jobs.run_day --date 2026-10-27 --simulate-crm` donne `ALREADY_LOADED`, `0 rows`, et `MERGE: 0 inserted, 0 updated`.

### 7. Les incidents (C6)

1. **Rejeu sans doublon** : relancer `ingest_factures` (ou tout le run d'un jour) → `COPY` charge 0 ligne, le `MERGE` ne change rien, le gold est identique.
2. **NOEMIE en retard** (inclus dans le jeu officiel) : le 30/10, pas de fichier NOEMIE → `load_noemie` enregistre `NO_FILE`, le test de complétude dbt échoue, le gold n'est pas publié, alerte Discord. Le 31/10, le fichier arrive avec les décomptes des deux jours → tout repasse au vert. Grâce au délai de 2 jours, aucune facture n'est marquée F2 à tort.
3. Bonus si on nous le demande : **schema drift** (`--schema-drift-from 2026-10-31` sur un jeu de test) → `load_invoices` s'arrête avec `SCHEMA_DRIFT` avant de charger.

### 8. Remise à zéro (répétitions, vidéo)

```bash
run jobs.reset_demo --yes          # TRUNCATE BRONZE (+ mémoire de chargement COPY), vide le stage, supprime la table CRM
```

Puis étapes 3, 5, 6, et `dbt build --full-refresh` côté transformation. Les tables SIRENE / RPPS sont conservées (ajouter `--with-references` pour les vider aussi).

## Commandes à donner au DAG Airflow (owner plateforme)

Dans le DAG, chaque run traite **la veille** : `B = {{ macros.ds_add(ds, -1) }}`.

| Tâche | Commande dans l'image `fraud-ingest:1.0.0` |
|---|---|
| `crm_activity` (simulation, démo uniquement) | `python -m jobs.seed_postgres --date B` |
| `ingest_adherents` | `python -m jobs.load_adherents_incremental` |
| `ingest_factures` | `python -m jobs.load_invoices --date B` |
| `ingest_noemie` | `python -m jobs.load_noemie --date B` |
| `check_sirene` (après `ingest_factures`) | `python -m jobs.fetch_sirene lookup` |
| `refresh_rpps` (hebdomadaire ; démo : `--reuse-extract`, l'extrait figé) | `python -m jobs.load_rpps --reuse-extract` |

Montages : `./data → /data`, `~/keys/mutuelle → /secrets` (lecture seule). Compte : `SVC_INGEST`. Variables : celles de `.env.example`.

## Ce que l'owner de la transformation reçoit

- les tables `BRONZE.*` décrites dans `docs/contracts.md` ;
- `data/answer_key/fraud_answer_key.csv` (seed dbt du test d'acceptation) et `data/answer_key/quarantine_key.csv` (test de la quarantaine) — déterministes, donc commitables dans `transformation/seeds/` ;
- `data_generator/validate.py`, la spécification exécutable du nettoyage, de la quarantaine, du délai F2 et des 7 règles (`--as-of` pour reproduire un matin donné).
