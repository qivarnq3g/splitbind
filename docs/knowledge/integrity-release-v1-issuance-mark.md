# What Integrity Release v1 actually puts in an issued file

## Scope

Read this before writing any user-facing copy, report text, or slide that
describes what a SplitBind issued document carries. It is the difference
between the released capability and the unreleased research capability, and
getting it wrong is an overclaim.

## Verified contract

In `integrity_release_v1` the issuance pipeline embeds **no hidden
fingerprint**. It stamps a **visible** marker and then hashes and signs.

Evidence, `services/api/splitbind/demo/issuance.py`:

- `fingerprint_key = None if integrity_mode else _load_fingerprint_key()`
- `_build_issuance_pdf(..., visible_marker=integrity_mode)`
- inside the page loop: `if visible_marker: content = apply_visible_marker(rendered, issuance_id)`,
  and `embed_fingerprint_v2(...)` is reachable only on the `else` branch, which
  is the demo/`experimental_unreleased_fingerprint_v2` path.

`services/api/splitbind/release/marker.py` shows what the visible marker is: a
high-contrast bottom-right label `SB1-<base32(issuance_id)[:20]>`, drawn per
page with OpenCV.

`services/api/splitbind/demo/capabilities.py` reports this to the browser as
`hidden_fingerprint_enabled=False` and
`transformed_attribution_available=False` whenever integrity mode is on.

## Consequences for copy

Honest descriptions of the released system:

- each recipient's copy carries a visible issuance code, so no two recipients
  hold the same bytes;
- the whole issued file is hashed with SHA-256 and recorded in a manifest;
- the manifest carries an Ed25519 signature;
- verification answers whether a suspect file is byte-identical to an issuance
  and whether that issuance record is still intact.

Claims that are **not** true of the released system:

- that a hidden watermark is embedded in the issued document;
- that a mark can be recovered after the file is compressed, resized or
  cropped;
- that a non-match proves the file was edited;
- that any result identifies who leaked a document.

A page that says "nhúng dấu vết riêng cho người nhận" without qualification
reads as a hidden watermark and therefore describes the unreleased path. Say
"mã cấp phát nhìn thấy được" instead.
