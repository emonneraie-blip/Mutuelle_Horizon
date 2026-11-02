# Data generator · Mutuelle Horizon Santé (optical claims fraud)

Standard-library Python (3.9+). Same `--seed` + same frozen references = same files, on every machine.

```bash
python3 generate.py --seed 42                       # THE official data set (10 batches 26/10 → 04/11, incident NOEMIE on 30/10)
python3 validate.py --data data --each-day           # every morning: 100 % recall on evaluable rules, 0 false positive
python3 validate.py --data data --as-of 2026-10-31   # what the pipeline must show on one morning
python3 generate.py --help                           # all options
```

| Option | Effect |
|---|---|
| `--refs-dir` | frozen real references, default `data_generator/ref/` (see `ref/README.md`). Missing → the generator stops |
| `--allow-synthetic` | CI only: synthetic SIRET / RPPS numbers when the references are missing |
| `--mess low/medium/high` | ~1 %, 4 % or 10 % of the cells damaged (dates, amounts, ids, codes, missing markers) |
| `--fraud-rate 0.07` | share of fraudulent claims drawn each day, topped up to `--min-per-rule 5` per rule |
| `--invalid-rate 0.005` | legit claims made unusable for the silver quarantine (at least 1 per day) |
| `--duplicate-rate 0.01` | technical resends (same claim twice): **noise, not fraud** |
| `--late-noemie-date 2026-10-30` | incident 2 (default): no NOEMIE file that day, delivered the day after. `none` to disable |
| `--schema-drift-from D` | bonus incident: a new column appears in the claim files from day D |

Guarantees checked by `validate.py`: ≥ 5 evaluable frauds per rule, one F5 on the last day (opened in the live demo),
quarantine found exactly, F2 evaluated only 2 days after reception.
Outputs, answer keys and fraud rules: see `../docs/contracts.md`. The seed and parameters are in
`data/answer_key/generation_manifest.json`.
