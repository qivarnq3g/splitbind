# Task 6: Fingerprint V2 pre-gate

## Factual evaluation

The retained deterministic V2 pre-gate completed all 1,408 scheduled rows
(22 pages x 16 candidates x 4 attacks) with seed `20260827`. It recorded zero
execution errors and zero false attributions. No candidate qualified: the
hash-bound selection is empty, so Task 7's V2 full matrix and V2 promotion
remain blocked.

- Plan SHA-256: `09b02268288e8d75d239b24e36830a8afe44467b1b1a3548805eb7efa8510bff`
- Results SHA-256: `b99a4d9fcf2e8df880d23294e31dc20887ec15bf888a83f8426a4a1afed87177`
- Summary SHA-256: `989f0051c634bd8c950d81ad73f7725d0ef42c211c232ecbd4d5fad0d36a3b4b`

## Review hardening

The public V2 full-matrix path now requires a nonempty, independently
validated pre-gate selection before image work or result-output creation.
Unselected V2 `--plan-only` inspection is explicitly non-executable. The
pre-gate loader reconstructs completion/error state only from validated rows,
requires the complete canonical 16-by-88 score population, rejects unknown
row fields and Python boolean/numeric type coercion in reconstructed
provenance, rechecks row provenance and metric ranges, and rechecks crop
eligibility even for execution-error rows. The retained evidence above was
validated under these checks without regenerating attacks or changing hashes.

## Fix loop round 2

The loader now constrains V2 payload evidence to the producer's vote model:
decoded rows require two or more independent votes, no row can exceed its
candidate repetition count, and the vote/bit-error-rate shape must match the
reported evidence status. It reconstructs each row's tamper ground truth and
removed-area fraction from the source and attack provenance, allowing only a
`1e-12` absolute tolerance for JSON floating-point serialization. Row
limitations are the exact ordered producer prefix, with exactly one structured
diagnostic only for an execution error. A generic execution diagnostic has no
persisted stage field, so it may match only the exact no-artifact or
post-attack provenance state; arbitrary field values remain rejected. The
retained 1,408-row evidence revalidated with its original hashes, without
regenerating attacks.

## Fix loop round 3

For a positive V2 pre-gate crop row that fails before an image artifact exists,
the producer now derives the direct-crop retained geometry, removed-area
fraction, and complete-tile eligibility from the frozen attack contract and
canonical layout. The row therefore remains an eligible crop miss in the
0-of-1 denominator and records the global execution error, which keeps the
selection empty. Its tamper ground truth remains source-only (after canvas
fit), rather than fabricating an applied crop artifact; limitations remain the
exact structured pre-artifact error form. Forced embedding and attack failures
cover this path. The retained 1,408-row evidence and its published hashes were
revalidated without regenerating attacks.
