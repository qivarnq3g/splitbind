# Fingerprint profile v2 evaluation

**Outcome:** No release.

## Qualified-selection decision

Task 6 produced a valid, hash-bound empty V2 qualified selection. Consequently the qualified full matrix was not run, and no V2 fingerprint profile was created.

- V2 candidate contract SHA-256: `e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4c83a97b88`.
- Corpus contract SHA-256: `e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef`.
- Attack-matrix contract SHA-256: `fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e`.
- Qualified-selection SHA-256: `709d798da2f494709f24f23a81a79ed5fcd944a7a50cb9a7fb5074f9ba5bc7b1`.
- Pre-gate plan SHA-256: `09b02268288e8d75d239b24e36830a8afe44467b1b1a3548805eb7efa8510bff`.
- Pre-gate results SHA-256: `b99a4d9fcf2e8df880d23294e31dc20887ec15bf888a83f8426a4a1afed87177`.
- Pre-gate summary SHA-256: `989f0051c634bd8c950d81ad73f7725d0ef42c211c232ecbd4d5fad0d36a3b4b`.
- Qualified candidates: 0 of 16.

The retained Task 6 evidence completed all 1,408 pre-gate rows with zero execution errors and zero false attributions, but every candidate missed the JPEG-70, resize-0.75, and geometry-eligible crop-0.25 robustness gates. That cost-control filter is not a full Gate G1 release measurement.

## Consequence

No full V2 matrix was executed because its required nonempty qualified selection does not exist. `contracts/algorithm/fingerprint-profile.v2.json` remains absent, and Rust A7 remains blocked pending a separately approved algorithm revision and new measurement evidence.

## Limitations

- The result applies only to the fixed synthetic corpus, candidate contract, attack matrix, and seed.
- Watermark matching is not proof of who leaked, edited, or distributed a document.
