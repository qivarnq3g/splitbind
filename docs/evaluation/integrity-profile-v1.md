# SplitBind integrity profile v1 factual evaluation

## Scope and binding limitation

This is an integrity-only measurement over the versioned synthetic corpus and tamper matrix. It does not require, create, or synthesize `fingerprint-profile.v1.json`. The combined fingerprint-plus-integrity interaction benchmark remains deferred until a fingerprint profile legitimately passes Gate G1; A7 remains blocked.

Localization IoU is research evidence, not a fingerprint release gate. Limited and failed rows contribute zero to the all-scheduled aggregate; poor results are preserved.

## Reproduction

```text
python research/python/scripts/run_integrity_benchmark.py --corpus fixtures/corpus/corpus-manifest.v1.json --profile contracts/algorithm/integrity-profile.v1.json --matrix contracts/algorithm/attack-matrix.v1.json --seed 20260827 --output reports/integrity-baseline-v1 --evaluation docs/evaluation/integrity-profile-v1.md
```

- Seed: `20260827`
- Corpus SHA-256: `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`
- Integrity profile SHA-256: `ece9203b3b3098c87d60e61beda75e8e049cc5c926fd0f300dd42df536d401ea`
- Tamper matrix SHA-256: `fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e`

## Observed result

- Status: `complete`
- Corpus pages: 12
- Tamper definitions: 4
- Scheduled denominator: 48
- Aggregate Localization IoU (all scheduled): 0.089981
- Execution failures: 0
- Limited/indeterminate rows: 38

| Tamper | Scheduled denominator | Aggregate IoU | Failures | Limited |
| --- | ---: | ---: | ---: | ---: |
| `replace_text` | 12 | 0.054687 | 0 | 9 |
| `cover_region` | 12 | 0.000000 | 0 | 12 |
| `copy_move` | 12 | 0.187500 | 0 | 8 |
| `insert_object` | 12 | 0.117736 | 0 | 9 |

## Limitations and failures

Stable limitation counts: `{"integrity.geometry_failure": 6, "integrity.strong_compression": 32}`.

No execution failures were observed.

The research target is Localization IoU at least 0.50. This document reports the observed result without changing fixtures, tamper regions, denominators, or promotion gates.
