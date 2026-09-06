# Fingerprint V3 pre-gate factual evaluation

**Outcome:** Blocked. No V3 candidate qualified, and no fingerprint profile or API integration is released.

## Scope and reproduction

This deterministic V3 pre-gate is a cost-control filter, not full Gate G1 release evidence. It measures the fixed population of 12 positive and 10 negative pages for four candidates against identity, JPEG quality 70, resize 0.75, and centre crop 0.25. It does not change the frozen corpus, attack matrix, candidate grid, or gate thresholds.

```text
python research/python/scripts/run_v3_pregate.py --profiles contracts/algorithm/fingerprint-candidates.v3.json --corpus fixtures/corpus/corpus-manifest.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260905 --output reports/fingerprint-pregate-v3
```

```text
python research/python/scripts/run_v3_pregate.py --verify reports/fingerprint-pregate-v3/summary.json --profiles contracts/algorithm/fingerprint-candidates.v3.json
```

- Plan: 22 pages x 4 candidates x 4 attacks = 352 rows.
- Seed: `20260905`.
- V3 candidate contract SHA-256: `14a47ced36eede7a4342c6ee280a59758747415a3b28331cfb16ab2e4f16ea23`.
- Corpus contract SHA-256: `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`.
- Attack-matrix contract SHA-256: `fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e`.
- Plan SHA-256: `efa3b78646f340600fae07eb60fc0c861a2c5b29734173ba0974c37242c696aa`.
- Results JSONL SHA-256: `69de7db807a69217dade43426d7f9f9e021a9073cfa78fb0d9eb5df489632938`.
- Results CSV SHA-256: `e0b1ba7d90b7c5c4ca9a4212a4abe5cbf29232286eda68bdba6a4f5e543bf983`.
- Summary SHA-256: `64ec81ffd3a68ce3e11887935f97754c1b798f00a0554eda6badf0250b2ec0e8`.
- Qualified-selection SHA-256: `25b32363244ac95e4ff779708de8e383789ea032a68ae5bf1f4d13c619098711`.

## Independent population and evidence audit

The retained JSONL contains 352 rows and 352 distinct scheduled row identifiers. Independent validation rebuilt the exact plan and accepted every row with `require_complete=True`; there were zero missing and zero duplicate rows. Independent `--verify` also loaded the hash-bound summary and selection, recomputed the aggregates, and accepted the JSONL, CSV, contract, plan, summary, and selection bindings.

The run status is `complete`: 352 completed rows, zero execution errors, and zero false attributions. The qualified selection contains zero candidate identifiers. The command intentionally reports a non-zero no-selection outcome after printing this valid fail-closed result.

## Per-candidate results

Required rates are JPEG-70 >= 0.95, resize-0.75 >= 0.95, and eligible crop-0.25 >= 0.90. Required minimum quality is PSNR >= 38 dB and SSIM >= 0.95.

| Profile SHA-256 | Tile px | Repetitions | JPEG-70 | Resize 0.75 | Crop 0.25 | Min PSNR dB | Min SSIM | Errors | False attribution | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `b61bc0374a5901252d3b20fabb3c6333ffecddf29daa9d8c4dc065ece0388400` | 384 | 3 | 8/12 (0.666667) | 8/12 (0.666667) | 8/12 (0.666667) | 42.474503 | 0.957989 | 0 | 0 | blocked: all three rate gates |
| `1baf034d0a0118c335e672ce858d375521dd17f2fbfd08943122bce10510cec2` | 384 | 5 | 8/12 (0.666667) | 8/12 (0.666667) | 9/12 (0.750000) | 42.320979 | 0.953169 | 0 | 0 | blocked: all three rate gates |
| `da34231d8ae5b50c0271cd5d06a794a780c0a1c051d791d9e1d7d778ce1e9d56` | 512 | 3 | 9/12 (0.750000) | 8/12 (0.666667) | 9/12 (0.750000) | 42.467614 | 0.955410 | 0 | 0 | blocked: all three rate gates |
| `f33c8358d70199eaf8918e30ca7f9f715312a26f79116489721a7e31b81f7a99` | 512 | 5 | 10/12 (0.833333) | 9/12 (0.750000) | 8/12 (0.666667) | 42.317990 | 0.958660 | 0 | 0 | blocked: all three rate gates |

All candidates met the two measured quality minima and had no execution errors or false attributions. None reached any of the three unchanged robustness-rate thresholds, so the fail-closed qualified selection is empty.

## Gate decision and limitations

The V3 release gate is **blocked**. Do not run a V3 full benchmark, create a promoted fingerprint profile, or integrate a research candidate into the production API. A subsequent plan may use these component measurements to design and validate a further candidate revision, then repeat this pre-gate before any promotion work.

This evidence applies only to the fixed synthetic corpus, candidates, attacks, and seed above. It is evidence about algorithm behaviour and does not prove who leaked, edited, or distributed a document.
