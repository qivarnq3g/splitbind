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

## Two claims in the submitted report contradict this

Found 2026-09-12 while auditing `docs/project/Nhom9_TruyVetToanVenVanBan.md` in the parent repository against source. The report is otherwise careful and repeatedly correct on this boundary - it labels every claim with an evidence tier, states at line 294 that production "chưa kích hoạt bộ trích xuất thủy vân tự động trên server", and concludes that the robust-watermark subsystem is held at the research tier. Two lines break that record:

- line 537: "Phiên bản đang chạy trên production vẫn là Integrity Release 0.1 dùng V2."
- line 633: "Production vẫn chạy V2 với xác thực toàn vẹn tệp chính xác."

Both read as "production embeds with the V2 algorithm". The code refutes it. `_build_issuance_pdf` branches strictly:

```python
if visible_marker:
    content = apply_visible_marker(rendered, issuance_id)
else:
    embedded = embed_fingerprint_v2(...)
```

`visible_marker` is `integrity_mode`, so the two paths are mutually exclusive and `embed_fingerprint_v2` is unreachable in production. The honest phrasing is that production runs the visible-marker path and performs no fingerprint embedding at all; V2 is the generation the research codec belongs to, not something the running release executes.

The distinction matters because these two lines are the ones a reader reaches for when asking "so what is actually deployed", and they say the opposite of the rest of the document.
