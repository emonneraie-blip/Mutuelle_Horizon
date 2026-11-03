# Mutuelle Horizon Santé · Brief d'équipe (à donner tel quel à votre Claude)

> **Pour Claude** : ce document est la source de vérité du projet. Respecte les noms, les contrats et la répartition ci-dessous. Reste dans la stack vue en TD (Snowflake, dbt, Docker, Airflow, Terraform, GitHub Actions). Fais simple et démontrable en live : pas de composant décoratif. Ne mets **jamais** de secret dans Git. Réponds en français.

---

## 0. Le cadre

| | |
|---|---|
| Cours | Data Engineering & Cloud Infrastructure (Albert School, Laura Belmond) |
| Groupe 1 | **Lucas Stefani** (ingestion) · **Clément Badalucco** (transformation) · **Eliott Monneraie** (plateforme) |
| Rendu | **mercredi 4 novembre, 23h30**, sur la plateforme : slides + lien Git + vidéo. L'assignment est « Individual » : **les 3 déposent** |
| Oral | **jeudi 5 novembre, 17h00**, 15 min = **10 min de présentation (avec démo live) + 5 min de questions** |
| Notation du projet | livrable Git 40 % · oral 40 % · délibération individuelle 10 % · évaluation par les pairs 10 % · **historique de commits exigé** |
| Repo | https://github.com/emonneraie-blip/Mutuelle_Horizon |

La grille de l'oral (/80) est la suivante :

| Critère | Pts | Qui le porte |
|---|---|---|
| C1 entreprise crédible | 10 | tous |
| C2 cas d'usage et valeur | 10 | Clément |
| **C3 pipeline de bout en bout** | **20** | Lucas et Clément |
| C4 outils justifiés | 10 | tous |
| C5 vrai usage du cloud + Terraform | 10 | Eliott |
| C6 fiabilité, tests, 2 incidents | 10 | Clément et Eliott |
| C7 sécurité et coûts | 5 | Eliott |
| C8 slides et oral | 5 | tous |

---

## 1. Le sujet (cadrage validé)

**Mutuelle Horizon Santé** est une complémentaire santé **fictive** : 300 000 adhérents, environ 250 M€ de cotisations par an, dont environ 80 % reversés en remboursements.

**Le problème.** En France, 112 M€ de fraude à la complémentaire santé ont été détectés en 2025, dont **53 % en optique**. Pour Horizon, on fait l'**hypothèse** d'environ 1 % de remboursements frauduleux non détectés, soit environ 2 M€ par an, dont environ 1 M€ en optique si on applique la part nationale de 53 %. L'objectif est d'en bloquer la moitié, soit environ **0,5 M€ par an, avant paiement**.

**Le cas d'usage.** Chaque matin, le **gestionnaire anti-fraude** reçoit la liste des **factures optique à contrôler** avant de les payer.

| | |
|---|---|
| Décision | bloquer et contrôler la facture, ou la payer |
| Grain de la métrique | une ligne par facture (`id_demande`) |
| Score | nombre de règles de fraude déclenchées (0 à 7), plus la liste des règles et le montant à risque |
| Fréquence | **batch quotidien** à 06:00 Europe/Paris. La mutuelle paie après contrôle : dès J+1 pour les 6 règles immédiates, à partir de J+3 pour F2 (le lot J+2 tourne le matin de J+3). Le streaming serait inutile |
| Test d'acceptation | sur nos données de test, **au moins 80 % des fraudes injectées** sont dans la liste à contrôler, et **0 faux positif** |

**Les 7 règles de fraude**

| Code | Règle |
|---|---|
| F1 | Renouvellement d'équipement en moins de 2 ans (730 jours), même adhérent |
| F2 | Facture sans décompte de la Sécurité sociale (NOEMIE) correspondant (même NIR, SIRET et date de soins). **Évaluée seulement 2 jours après la réception** (un décompte peut arriver jusqu'à J+2, donc la décision tombe le matin de J+3, quand tourne le lot J+2) ; avant, F2 est « EN_ATTENTE » et le paiement attend |
| F3 | Classe B et part mutuelle demandée > min(plafond du contrat responsable, garantie de la formule) |
| F4 | SIRET de l'opticien inconnu ou fermé dans SIRENE (opticien fantôme) |
| F5 | Même numéro de facture du même opticien déjà remboursé à un **autre** adhérent |
| F6 | RPPS du prescripteur absent de l'annuaire des ophtalmologues |
| F7 | Date de soins postérieure à la fin du contrat de l'adhérent |

Les données de référence pour ces règles :
- **plafonds du contrat responsable** : simple 420 €, mixte 560 €, complexe 700 €, très complexe 800 € ;
- **garanties optique par formule** : Essentiel 150 €, Confort 300 €, Premium jusqu'au plafond.

---

## 2. L'architecture

```
 SOURCES (5)                         INGESTION (Docker, owner Lucas)          SNOWFLAKE (compte DPNIFMK-WG18146)
 ─────────────────────────           ───────────────────────────────          ───────────────────────────────────────────
 Factures optique (CSV/jour)   ──►   batch PUT + COPY INTO          ──┐
 Décomptes NOEMIE (JSON/jour)  ──►   batch COPY INTO (VARIANT)       ──┤      stage BRONZE.LANDING
 CRM adhérents (Postgres)      ──►   incrémental watermark + MERGE   ──┼──►   BRONZE (brut + _source_file, _loaded_at, _run_id)
 SIRENE (API publique, réelle) ──►   appel API, SIRET non vérifiés   ──┤             │  dbt (Docker, owner Clément)
 Annuaire RPPS (open data réel) ─►   référentiel, rechargement total ──┘             ▼
                                                                              SILVER (typé, nettoyé, dédoublonné, NIR haché, quarantaine)
                                                                                     ▼
                                                                              GOLD (factures + 7 règles, liste à contrôler, KPI)
                                                                                     ▼
                                                                              Dashboard Streamlit in Snowflake (gestionnaire anti-fraude)

 PLATEFORME (owner Eliott) : Airflow (DAG quotidien, retries, alerte Discord) · Terraform (entrepôts, rôles, comptes,
 grants, state distant HCP) · GitHub Actions (terraform plan + tests sur chaque PR) · FinOps (XSMALL, auto-suspend, resource monitor)
```

**Les choix à défendre (C4)**

| Brique | Choix | Pourquoi | Alternative crédible |
|---|---|---|---|
| Entrepôt | Snowflake | séparation stockage/calcul, déjà maîtrisé en TD, paiement à la seconde | BigQuery |
| Ingestion | jobs Python en Docker | une méthode adaptée à chaque source, code déjà testé en TD | Airbyte, dlt |
| Transformation | dbt | médaillon, tests, lineage, comme au TD dbt | SQL dans des Snowflake Tasks |
| Orchestration | Airflow + DockerOperator | retries, backfill, alertes (TD Airflow) | Snowflake Tasks, Dagster |
| Infra as Code | Terraform + state distant (HCP Terraform, gratuit) | reproductible, relu en PR, détection de dérive (TD Terraform) | Pulumi ; scripts SQL lancés à la main (plus simple, mais sans détection de dérive) |
| Fréquence | batch quotidien | la décision est quotidienne | streaming : coût et complexité inutiles |

---

## 3. Snowflake : les noms (à ne pas changer)

| Objet | Nom | Créé par |
|---|---|---|
| Base | `MUTUELLE_FRAUD` | Terraform (Eliott) |
| Schéma brut | `BRONZE` | rôle `INGEST_ROLE`, job `bootstrap_bronze` (Lucas) |
| Schémas nettoyé / métier | `SILVER`, `GOLD`, plus `OPS` pour les logs dbt | rôle `TRANSFORM_ROLE`, dbt (Clément) |
| Entrepôts (XSMALL, auto-suspend 60 s) | `INGEST_WH`, `TRANSFORM_WH`, `BI_WH` | Terraform |
| Rôles | `INGEST_ROLE` (écrit BRONZE) · `TRANSFORM_ROLE` (lit BRONZE, écrit SILVER/GOLD/OPS) · `ANALYST_ROLE` (lit uniquement les KPI agrégés) | Terraform |
| Accès de la prof | rôle `REDGRAVE_GRADER` (existe déjà depuis le TD ingestion) : lecture sur `SILVER`, `GOLD`, `OPS` — **pas sur BRONZE** (NIR en clair) | Terraform |

`ANALYST_ROLE` = la direction : uniquement les KPI agrégés (c'est la démo « accès refusé »). Le dashboard du gestionnaire est une app Streamlit **possédée par `TRANSFORM_ROLE`** avec USAGE sur `BI_WH` : elle tourne avec les droits de son propriétaire.

Principe : **chaque rôle possède sa couche**. Le rôle propriétaire d'une couche donne la lecture à la couche suivante : BRONZE donne la lecture à `TRANSFORM_ROLE`, et GOLD donne la lecture des KPI à `ANALYST_ROLE`.

---

## 4. Comptes, clés et secrets

### Les comptes

| Compte | Type | Rôles | Utilisé pour |
|---|---|---|---|
| `LSTEFANI@ALBERTSCHOOL.COM` (Lucas) | humain, **propriétaire du compte** | ACCOUNTADMIN (exceptionnel), `INGEST_ROLE` | bootstrap une fois, développement de l'ingestion |
| `CLEMENT` | humain | `TRANSFORM_ROLE`, `ANALYST_ROLE` | développement dbt, Snowsight |
| `ELIOTT` | humain | SYSADMIN, SECURITYADMIN | Terraform en local, Snowsight |
| `SVC_TERRAFORM` | **service** (clé RSA uniquement, pas de mot de passe) | SYSADMIN, SECURITYADMIN | Terraform en CI (GitHub Actions) |
| `SVC_INGEST` | service | `INGEST_ROLE` | tâches d'ingestion lancées par Airflow |
| `SVC_TRANSFORM` | service | `TRANSFORM_ROLE` | tâche dbt lancée par Airflow |

Ce qu'on dira à l'oral : **les humains et les machines ont des comptes séparés. Chaque tâche du pipeline tourne avec un compte de service limité à sa couche, authentifié par clé RSA, sans mot de passe.**

### Les secrets : où ils vivent, et jamais dans Git

| Secret | Où | Qui |
|---|---|---|
| Clé privée personnelle `rsa_key.p8` | `~/keys/` sur le Mac de chacun | chacun |
| Clés `svc_ingest.p8`, `svc_transform.p8` | `~/keys/mutuelle/` sur la **machine de démo** (Mac de Lucas), montées **en lecture seule** dans les conteneurs | Lucas |
| Clé `svc_terraform.p8` | Mac d'Eliott + **GitHub Secret** `SF_PRIVATE_KEY` | Eliott |
| `.env` (utilisateurs, mot de passe Postgres local, webhook Discord) | racine du repo, **gitignoré**. Seul `.env.example` est commité | chacun |
| `terraform.tfvars`, `*.tfstate` | Mac d'Eliott (gitignorés), le state est stocké sur HCP Terraform | Eliott |
| GitHub Secrets | `SF_ORGANIZATION_NAME`, `SF_ACCOUNT_NAME`, `SF_USER`, `SF_PRIVATE_KEY`, `TF_API_TOKEN` | Eliott |
| API SIRENE / données RPPS | **pas de clé** (open data) | — |

Générer une clé (chacun pour lui, ou sur la machine de démo pour les services) :
```bash
mkdir -p ~/keys && openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/keys/rsa_key.p8 -nocrypt
openssl rsa -in ~/keys/rsa_key.p8 -pubout -out ~/keys/rsa_key.pub     # seule la clé PUBLIQUE est partagée
```

---

## 5. GitHub

```
Mutuelle_Horizon/
├── README.md                  ← pitch, schéma, "lancer la démo en 6 commandes"     (tous)
├── .github/
│   ├── CODEOWNERS             ← qui relit quoi
│   └── workflows/ci.yml       ← terraform plan + tests Python sur chaque PR        (Eliott)
├── .gitignore  .env.example  docker-compose.crm.yml
├── data_generator/            ← données réalistes + fraudes + corrigé + validate   (Lucas)
├── ingestion/                 ← jobs Python, SQL bronze, Dockerfile → fraud-ingest:1.0.0   (Lucas)
├── transformation/            ← projet dbt mutuelle_dbt + Dockerfile → fraud-dbt:1.0.0     (Clément)
├── dashboard/                 ← Streamlit in Snowflake                              (Clément)
├── airflow/                   ← docker-compose, Dockerfile, dags/                    (Eliott)
├── terraform/                 ← main.tf, modules/warehouse, bootstrap_admin.sql      (Eliott)
└── docs/                      ← architecture, contracts, security, finops, incidents, demo   (tous)
```

**Règles :**
1. Eliott invite Lucas et Clément comme **collaborateurs**, et **la prof** au moment du rendu, puisque le repo est privé.
2. **Personne ne pousse directement sur `main`.** On travaille sur une branche `feat/<sujet>`, on ouvre une **pull request** relue par un autre membre, puis on merge.
3. Chacun commite **depuis son propre compte GitHub**, avec des messages clairs (`ingestion: add NOEMIE loader`). L'historique compte dans la note.
4. Le dossier `data/` n'est jamais commité : il se régénère avec la seed 42.

---

## 6. Le travail de chacun

### Étape 1 · Lucas · Sources → BRONZE (le code est déjà écrit et testé : `data_generator/`, `ingestion/`)

1. ✅ Squelette du repo et code de la partie 1 sur `main`. PR `fix/part1-review` : corrections de la review du 02/11 (délai F2, minimisation, noms fictifs, quarantaine, quotas, reset).
2. Figer les références réelles **une seule fois** : `fetch_sirene catalogue` (opticiens actifs de Paris et petite couronne) et `load_rpps --extract-only` (ophtalmologues), copiées sans noms dans `data_generator/ref/` et versionnées.
3. Générer le **jeu officiel** : `generate.py --seed 42` (incident NOEMIE du 30/10 inclus), puis `validate.py --each-day` → `VALIDATION OK`. Les corrigés `fraud_answer_key.csv` et `quarantine_key.csv` vont dans les seeds dbt de Clément.
4. Construire l'image `fraud-ingest:1.0.0`, lancer le CRM Postgres (`docker-compose.crm.yml`), faire `seed_postgres --date history`.
5. **Après le Terraform d'Eliott** : `bootstrap_bronze`, puis charger l'historique et les références, puis les jours **jusqu'au 03/11 inclus** avec `run_day`, tout de suite, pour que Clément développe dbt. Le 04/11 est réservé au run live. Quand le DAG et dbt sont prêts : `reset_demo` (garde SIRENE / RPPS) puis rechargement par le backfill Airflow.
6. Prouver l'idempotence : relancer un jour donne `ALREADY_LOADED` et `MERGE 0/0`. Livrer `jobs.reset_demo` (remise à zéro par `TRUNCATE`) pour les répétitions.

**C'est fini quand** : les 6 tables BRONZE sont remplies, `LOAD_AUDIT` est propre, et Eliott a la liste des commandes Docker pour le DAG (voir `docs/part1_sources_bronze.md`).

### Étape 2 · Clément · BRONZE → SILVER → GOLD + dashboard (`transformation/`, `dashboard/`)

Projet dbt `mutuelle_dbt`, sur la même base que le TD dbt (profiles.yml avec variables d'environnement, macro de log dans `OPS.DBT_RESULTS`).

| Couche | Modèle | Rôle |
|---|---|---|
| silver | `slv_factures` | typage (3 formats de date, montants « 1 234,50 € », codes en majuscules, identifiants sans espaces), **dédoublonnage** des renvois techniques sur `id_demande`, `nir_hash = SHA2(nir)` |
| silver | `slv_factures_quarantaine` | lignes inexploitables (date impossible, montant négatif ou manquant), avec la raison. Exclues des règles **et** de l'historique F1/F5. Liste attendue : seed `quarantine_key` |
| silver | `slv_noemie` | aplatissement du VARIANT |
| silver | `slv_adherents`, `slv_opticiens_sirene`, `slv_prescripteurs_rpps` | référentiels nettoyés (`ADHERENTS` est minimisée : identifiant, formule, dates de contrat, statut ; ni NIR ni coordonnées) |
| gold | `fct_factures_optique` | une ligne par facture, avec les **7 indicateurs F1 à F7** ; F2 seulement si `date_reception <= batch_date - 2`, sinon `f2_statut = 'EN_ATTENTE'` |
| gold | `mart_factures_a_controler` | score, liste des règles, montant à risque, décision `A_CONTROLER` / `OK` |
| gold | `kpi_fraude_quotidien` | par jour : nombre de factures, nombre de suspectes, montant bloqué. **Seule table visible par `ANALYST_ROLE`** |

**Tests :**
- **clé** : `unique` et `not_null` sur `id_demande` ;
- **règle métier** : `accepted_values` sur canal, classe et catégorie, plus un test singulier « montant ≥ 0 » ;
- **complétude** : le lot NOEMIE du `batch_date` est bien présent. C'est ce test qui déclenche l'incident 2 ;
- **test d'acceptation** : seed `fraud_answer_key` + test singulier `assert_recall_80pct` (hors F2 encore en attente), 0 faux positif ; seed `quarantine_key` pour la quarantaine.

La **spécification exécutable** de chaque règle, de chaque nettoyage, de la quarantaine et du délai F2 est dans `data_generator/validate.py` : il faut reproduire exactement ses résultats en SQL. `validate.py --as-of AAAA-MM-JJ` donne le résultat attendu pour un matin donné.

**Image `fraud-dbt:1.0.0`, avec le projet dbt COPIÉ dans l'image.** C'était le bug de l'image fournie au TD Airflow. Versions figées : dbt-core 1.11.x et dbt-snowflake 1.11.x, comme au TD.

**Dashboard** Streamlit in Snowflake, sur `GOLD` uniquement :
- la liste des factures à contrôler aujourd'hui, avec les règles déclenchées ;
- les KPI du jour ;
- la date de fraîcheur des données.

**C'est fini quand** : `dbt build` est vert, le rappel est d'au moins 80 % avec 0 faux positif, et le dashboard affiche le 03/11 (puis le 04/11 après le run live).

### Étape 3 · Eliott · Plateforme (`terraform/`, `airflow/`, `.github/`, docs sécurité / FinOps / incidents)

1. **Aujourd'hui, en priorité, parce que tout le monde en dépend :**
   - Lucas exécute `terraform/bootstrap_admin.sql`, l'étape manuelle : utilisateurs `ELIOTT`, `CLEMENT`, `SVC_TERRAFORM` et le resource monitor ;
   - Eliott fait le **Terraform**, en reprenant le TD (module warehouse) : base, 3 entrepôts, 3 rôles, 2 comptes de service (`snowflake_service_user`, avec les clés publiques de Lucas), grants (usage, `CREATE SCHEMA` pour INGEST et TRANSFORM, rôles rattachés à SYSADMIN), et lecture pour `REDGRAVE_GRADER` sur SILVER / GOLD / OPS seulement (aucun rôle hors INGEST / TRANSFORM ne lit BRONZE) ;
   - **state distant sur HCP Terraform** (gratuit, verrouillé).
2. **CI** `ci.yml` sur chaque PR : `terraform fmt -check`, `validate`, `plan`. ⚠️ Reprendre le workflow **corrigé** du TD : la clé est écrite dans l'étape, via `$GITHUB_ENV`, et pas dans le bloc `env:` du job. Plus un job Python qui lance `generate.py` puis `validate.py`.
3. **DAG Airflow `mutuelle_fraud_daily`** (copie adaptée du TD) :
   - planification `0 6 * * *` Europe/Paris, `max_active_runs=1`, `retries=2`, alerte Discord après le dernier échec ;
   - chaque tâche est un `DockerOperator` qui traite **le lot de la veille** (`{{ macros.ds_add(ds, -1) }}`) :
     `crm_activity` → `ingest_adherents` + `ingest_factures` + `ingest_noemie` (en parallèle) → `check_sirene` → `dbt_build` (`dbt build --vars '{batch_date: …}'`) ;
   - montages : `./data` → `/data`, `~/keys/mutuelle` → `/secrets` (lecture seule) ;
   - comptes : `SVC_INGEST` pour l'ingestion, `SVC_TRANSFORM` pour dbt ;
   - préchargement par **backfill** (dates logiques du 27/10 au 04/11 = lots du 26/10 au 03/11) : l'historique Airflow garde le run rouge du 30/10 et le vert du 31/10 ;
   - script de démo : `jobs.reset_demo --yes` puis rechargement, pour les répétitions et la vidéo.
4. **Sécurité (C7)** : la démo « accès refusé » (`USE ROLE ANALYST_ROLE; USE SECONDARY ROLES NONE; USE WAREHOUSE BI_WH; SELECT * FROM MUTUELLE_FRAUD.GOLD.MART_FACTURES_A_CONTROLER;` → erreur, alors que `KPI_FRAUDE_QUOTIDIEN` passe) et `docs/security.md`.
5. **FinOps (C7)** :
   - coût réel du prototype : `ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`, par entrepôt ;
   - projection mensuelle avec ses hypothèses ;
   - resource monitor ;
   - procédure d'arrêt et de nettoyage (`terraform destroy` après la note).
6. **Les 2 incidents, testés et documentés** dans `docs/incidents.md` :
   - **incident 1, rejeu sans doublon** : la tâche `ingest_factures` est relancée après un retry, `COPY` charge 0 ligne, et le gold ne change pas ;
   - **incident 2, NOEMIE en retard** : inclus dans le jeu officiel (30/10, défaut de `generate.py`), le test de complétude échoue, le gold n'est pas publié, l'alerte Discord part. On relance une fois le fichier arrivé, et tout repasse au vert.

**C'est fini quand** : le DAG tourne seul de bout en bout sur la machine de démo, et les 2 incidents ont été rejoués.

---

## 7. Qui livre quoi à qui, et quand

| Quand | Livraison |
|---|---|
| **Lun 2, 14h** | Eliott : repo + collaborateurs + CODEOWNERS · Lucas : bootstrap admin exécuté |
| **Lun 2, 18h** | Eliott : Terraform appliqué (rôles, entrepôts, comptes de service) · Lucas : PR partie 1 mergée, données générées |
| **Mar 3, 12h** | Lucas : BRONZE rempli → Clément · Clément : silver qui tourne |
| **Mar 3, 20h** | Clément : gold + tests + image `fraud-dbt` → Eliott · Eliott : DAG qui tourne avec les deux images |
| **Mer 4, 14h** | Pipeline complet sur la machine de démo, incidents rejoués, dashboard OK |
| **Mer 4, 20h** | Slides finales + vidéo enregistrée → **les 3 déposent avant 23h30** |
| **Jeu 5, matin** | 2 répétitions chronométrées. Oral à 17h00 |

---

## 8. La démo live (environ 3 min dans les 10 min)

Préparation la veille : la base est chargée jusqu'au **03/11 inclus**, Airflow est démarré, le DAG est en pause depuis mercredi soir (aucun run en file), le dashboard est ouvert.

1. **Airflow** : **retirer la pause** du DAG, sans cliquer sur « Déclencher » (le run planifié du 5/11 traite le lot du **04/11**, voir `docs/demo.md`), puis montrer le graphe (ingestion en parallèle → SIRENE → dbt) qui passe au vert (Eliott).
2. **Snowsight** : `LOAD_AUDIT` du jour. **Airflow** : relancer `ingest_factures` (Clear) → `ALREADY_LOADED`, avant de remettre la pause. C'est l'idempotence (Lucas).
3. **Dashboard** : les factures du 04/11 à contrôler, avec les règles déclenchées. Ouvrir **la F5 du 04/11** (« facture réutilisée », son `id_demande` est affiché par `validate.py`) et l'expliquer (Clément). Les F2 du jour sont « en attente » : c'est normal, et ça se défend (décision F2 et paiement à J+3).
4. **Accès refusé** avec `ANALYST_ROLE` (Eliott).

**Plan B** : si le réseau ou le wifi tombe, on passe la **vidéo** enregistrée mercredi.

## 9. Les slides (10 min)

| # | Contenu | Qui | Durée |
|---|---|---|---|
| 1 | Horizon Santé, le problème chiffré, le cas d'usage | Clément | 1 min 15 |
| 2 | Architecture + choix d'outils et alternatives | Eliott | 1 min 15 |
| 3 | Sources et ingestion : 5 sources, 4 méthodes, idempotence, éthique des données | Lucas | 1 min 30 |
| 4 | Transformation : nettoyage, 7 règles, tests, rappel mesuré | Clément | 1 min 30 |
| 5 | **Démo live** | les 3 | 3 min |
| 6 | Fiabilité et incidents, sécurité, coûts et projection | Eliott | 1 min |
| 7 | Limites et prochaines étapes (CDC, ML, autres postes : dentaire, audio) | Lucas | 0 min 30 |

## 10. Checklist du rendu (mercredi soir)

- [ ] README : comment tout relancer de zéro, et le schéma d'architecture
- [ ] Aucun secret dans le repo (`git log -p | grep -i "private"` ne renvoie rien)
- [ ] La prof est invitée sur le repo (ou le repo est public, s'il ne contient aucun secret)
- [ ] Slides en PDF, avec la vidéo de démo
- [ ] **Chacun des 3** a déposé slides + lien Git + vidéo sur la plateforme
