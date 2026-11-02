# Frozen reference extracts (real public data, no names)

| File | Source | Columns | Produced by (once) |
|---|---|---|---|
| `opticiens_sirene.csv` | API Recherche d'entreprises (SIRENE), active shops NAF 47.78A, Paris + petite couronne | siret, siren, code_postal, commune, etat_administratif, activite_principale | `python -m jobs.fetch_sirene catalogue --departements 75 92 93 94 --max 400` |
| `ophtalmos_rpps.csv` | Annuaire Santé (RPPS) open data, ophthalmologists | rpps, code/libellé profession, code/libellé savoir-faire, code_postal, commune | `python -m jobs.load_rpps --extract-only` |

Why frozen: the API answers and the RPPS file change every week. Versioning a dated extract makes `generate.py --seed 42`
give exactly the same data on every machine (Lucas, Eliott, CI) and on the day of the oral.
Refresh = re-run the two commands, copy from `data/ref/`, open a pull request, regenerate the official data set.
