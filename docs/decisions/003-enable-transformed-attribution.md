# ADR-003: Enable transformed attribution as an off-by-default capability

Date: 2026-09-12

## Status

Accepted. It amends one guardrail of [ADR-002](002-integrity-release-python-worker.md) and leaves the rest of that decision standing.

## Context

ADR-002 fixed `SPLITBIND_RELEASE_MODE=integrity_v1` as the only production processing mode and stated that transformed-file source attribution is unavailable. That was the right call at the time: no fingerprint profile had passed Gate G1, and shipping an unreleased decoder as a product capability would have made the system claim more than it could support.

The measurements that gate rests on all come from the research harness. Nothing had ever exercised the fingerprint path through the shipped pipeline, where issuance and verification are separate jobs against real documents. The operator asked for the capability on production, and the question of what the algorithm actually does outside the harness was worth answering with evidence rather than argument.

## Decision

Transformed attribution becomes an explicit capability controlled by `SPLITBIND_FINGERPRINT_ENABLED`, defaulting to false.

When false, which is the default and what the entire existing test suite exercises, behaviour is exactly as ADR-002 describes: issuance writes the visible pseudonymous marker, verification answers from the exact file hash and the signed manifest.

When true, issuance embeds the V2 fingerprint instead of the visible marker and verification runs the decoder in addition to the hash comparison. The capability is a separate switch rather than a change to `integrity_v1`, so the existing guard test that fails if integrity mode ever runs the fingerprint decoder still passes unchanged and now proves the capability is off unless someone turns it on.

Two boundaries are non-negotiable while it is on. The decoder may only ever add a positive identification; it can never contradict the hash result and never attribute behaviour to a person. And the result copy must state the real limit rather than a convenient one: the limitation identifier is `fingerprint.recall_below_release_gate`, not the older `fingerprint.transformed_attribution_unavailable`, which would be false while the decoder is running.

## Consequences

What the capability delivered, measured on production across five trials and recorded in the report at Mục 4.2.3: no transformed copy was attributed. The one success was a byte-identical artifact at a narrow page geometry, where the exact hash already answers. An untouched A4 artifact, which is the real document format, did not decode at all.

Precision held throughout. Every failure returned zero valid votes and no attribution, consistent with the zero false-attribution rate measured over 352 V3 rows, so the capability cannot accuse anyone. It simply does not answer.

The exercise produced a second root-cause diagnosis that the benchmark could not have produced. A text page is close to the worst carrier this design can be given: it is mostly white with sparse high-contrast glyph edges and almost no mid-frequency texture, which is where the QIM payload lives. A gradient carrier retained payload evidence through a 0.50 rescale while a text page produced nothing even unattacked. Every document this product issues is a text page, so a robustness rate measured on gradient and vector corpora is not a product capability. That finding redirects V4: choose the carrier and embedding domain for text pages first, and normalise the frame second.

A refuted hypothesis is recorded with it. Supplying the decoder the issuance-time ORB sync template, which the harness does and production cannot, changes nothing: thirty cells across three carriers and five attack conditions returned identical status with and without it.

## Guardrails

- The capability ships off. Turning it on is an explicit operational act through `infra/scripts/enable_fingerprint_capability.ps1`, and the same script turns it off.
- The fingerprint key is generated on the VM and never leaves it. Rotating it makes every document issued while the capability was on undecodable, so the script warns and requires an explicit flag.
- While the capability is on, the report must say so. ADR-002's statement that production runs exact-file integrity only is amended by this ADR, and Mục 4.2.3 of the report carries the measured outcome.
- This ADR does not promote any fingerprint profile. V1, V2 and V3 remain unreleased, Gate G1 is unchanged, and no number measured here may be presented as a released capability.

## Replacement condition

ADR-003 is superseded when a fingerprint profile passes the unchanged benchmark gates **on a corpus of text pages rendered from real PDFs**, which is the corpus change this decision's evidence requires.
