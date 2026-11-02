# Data generator · Mutuelle Horizon Santé (optical claims fraud)

Standard-library Python (3.9+). Same `--seed` = same files.

```bash
python3 generate.py --seed 42                     # default: 8,000 adherents, 10 daily batches from 2026-10-26, 7 % fraud
python3 validate.py --data data                    # reference rules: must print VALIDATION OK
python3 generate.py --help                         # all options
```

| Option | Effect |
|---|---|
| `--mess low/medium/high` | ~1 %, 4 % or 10 % of the cells damaged (dates, amounts, ids, codes, missing markers) |
| `--fraud-rate 0.07` | share of fraudulent claims added each day |
| `--duplicate-rate 0.01` | technical resends (same claim twice): **noise, not fraud** |
| `--late-noemie-date D` | incident: no NOEMIE file on day D (delivered the day after) |
| `--schema-drift-from D` | incident: a new column appears in the claim files from day D |
| `--refs-dir data/ref` | real SIRENE opticians / RPPS ophthalmologists (see `ingestion`), synthetic fallback otherwise |

Outputs, answer key and fraud rules: see `../docs/contracts.md`.
Write the seed and the parameters (`data/answer_key/generation_manifest.json`) in the final report: the demo is reproducible.
