# Fingerprint V2 pre-gate factual evaluation

**Outcome:** No qualified candidate; no V2 profile is released.

## Scope and reproduction

This deterministic pre-gate is a cost-control filter, not full Gate G1 release evidence. It measures the complete versioned population of 12 positive and 10 negative pages against identity, JPEG quality 70, resize 0.75, and crop 0.25. It does not change the corpus, attack matrix, candidate grid, or release thresholds.

```text
python research/python/scripts/run_v2_pregate.py --profiles contracts/algorithm/fingerprint-candidates.v2.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --output reports/fingerprint-pregate-v2
```

- Plan: 22 pages x 16 candidates x 4 attacks = 1,408 rows.
- Seed: `20260827`.
- Plan SHA-256: `09b02268288e8d75d239b24e36830a8afe44467b1b1a3548805eb7efa8510bff`.
- Results JSONL SHA-256: `b99a4d9fcf2e8df880d23294e31dc20887ec15bf888a83f8426a4a1afed87177`.
- V2 candidate contract SHA-256: `e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4c83a97b88`.
- Corpus contract SHA-256: `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`.
- Attack-matrix contract SHA-256: `fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e`.

## Observed result

- Status: `complete`; 1,408 distinct scheduled row identifiers and 1,408 completed rows.
- Execution errors: 0. False attributions: 0.
- Qualified candidates: 0 of 16. The hash-bound selection is empty, and the CLI exits `2` on this no-selection path.
- Best observed JPEG-70 decode rate: 3/12 = 0.25, below 0.95.
- Best observed resize-0.75 decode rate: 2/12 = 0.166667, below 0.95.
- Best observed geometry-eligible crop-0.25 decode rate: 1/2 = 0.50, below 0.90.
- Mean clean-watermarked quality across candidates ranged from 37.730050 to 46.018574 dB PSNR and from 0.920231 to 0.986177 SSIM. Four candidates also missed both quality thresholds.

All 16 candidates missed each JPEG-70, resize-0.75, and eligible-crop gate. The gradient fixture completed all four attacks for every candidate, so no execution failure was hidden by the pre-gate.

## Consequence and limitations

The qualified selection is fail-closed and empty. Therefore Task 7's V2 full matrix and V2 promotion must not run, `contracts/algorithm/fingerprint-profile.v2.json` must remain absent, and Rust A7 remains blocked.

These results apply only to the fixed synthetic corpus, candidates, attacks, and seed above. They are evidence about algorithm behavior, not proof of who leaked, edited, or distributed a document.
