# transformation/ · owner Clément

Projet dbt `mutuelle_dbt` : BRONZE → SILVER → GOLD, plus `OPS.DBT_RESULTS` pour l'historique des runs.
Contrat avec l'ingestion : `docs/contracts.md`.

| Couche | Modèle | Rôle |
|---|---|---|
| silver | `int_factures_controlees` | typage, dédoublonnage, NIR haché, raison de rejet |
| silver | `slv_factures`, `slv_factures_quarantaine` | bonnes lignes d'un côté, rejets de l'autre |
| silver | `slv_noemie`, `slv_adherents`, `slv_opticiens_sirene`, `slv_prescripteurs_rpps` | sources nettoyées |
| gold | `fct_factures_optique` | une ligne par facture, indicateurs F1 à F7 |
| gold | `mart_factures_a_controler` | score, règles, montant à risque, décision |
| gold | `kpi_fraude_quotidien` | KPI par lot, seule table lisible par `ANALYST_ROLE` |

## Lancer

```bash
cd transformation
export SNOWFLAKE_ACCOUNT=<voir .env> SNOWFLAKE_USER=CLEMENT SNOWFLAKE_PRIVATE_KEY_FILE=~/keys/rsa_key.p8
export DBT_PROFILES_DIR=. NIR_SALT=<valeur partagée, jamais dans Git>
dbt debug                                        # teste la connexion
dbt build --vars '{batch_date: 2026-11-03}'      # construit et teste tout pour ce lot
dbt docs generate && dbt docs serve              # le graphe de lineage
```

## Décisions à savoir expliquer

1. **Renvoi technique :** même `id_demande` deux fois. On garde le premier reçu : ce n'est pas une fraude.
2. **Quarantaine :** une ligne dont la date est impossible ou le montant négatif n'entre pas dans silver. Au-delà de 15 % de rejets, le run échoue.
3. **F2 :** évaluée 2 jours après la réception, uniquement avec les décomptes déjà reçus. Avant, la facture est `EN_ATTENTE`.
4. **Pas de quoi conclure n'est pas OK :** une facture sans alerte mais avec F2 en attente n'est pas payable.
5. **Incident NOEMIE :** `assert_lot_noemie_present` échoue, dbt ne construit pas gold, et le gold de la veille reste en place.
6. **Vie privée :** NIR haché avec un sel, aucune identité d'adhérent, SIRET masqué dans la liste.

## Avant le premier run officiel

Remplacer `seeds/fraud_answer_key.csv` par le corrigé du jeu officiel de Lucas (`data/answer_key/fraud_answer_key.csv`). Tant qu'il est vide, le test `assert_corrige_charge` échoue volontairement : en attendant, lancer `dbt build --exclude tag:acceptation`.
