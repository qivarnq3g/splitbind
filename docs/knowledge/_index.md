# Knowledge Index

Auto-maintained catalog of accumulated project knowledge. The agent updates this file in the same turn that it creates, renames, merges, splits, or deletes any file in this directory. An entry that no longer matches a file on disk is a defect, not a stale note.

Check this index before creating a new knowledge file: if an existing file already owns the topic, revise it in place rather than adding a near-duplicate.

## Core (shipped with every project)

- [engineering-rigor-and-completion.md](engineering-rigor-and-completion.md) - Technical rigor standards, data safety and Git trust boundaries, Definition of Done, and knowledge-persistence invariants.
- [experimental-rigor-and-evidence.md](experimental-rigor-and-evidence.md) - Response quality and reasoning discipline, the A-T evidence and controlled-experiment rules, and epistemic calibration when handling feedback.
- [knowledge-lifecycle-guide.md](knowledge-lifecycle-guide.md) - In-turn persistence rules (zero-deferral), taxonomy and routing, the quality gate that keeps the knowledge base from bloating, and file management.
- [workspace-cleanup-and-lifecycle.md](workspace-cleanup-and-lifecycle.md) - Cleanup rules, task artifact lifecycle, background process release, and locked-file safe deletion.
- [agent-tools-and-plugins.md](agent-tools-and-plugins.md) - Registry of plugins and skills with per-platform install and verification commands (Antigravity, Claude, Codex, Gemini, Cursor).
- [powershell-and-patch-portability.md](powershell-and-patch-portability.md) - PowerShell collection piping, parameter quoting, cross-platform CI shims, Unicode-safe exact patching, and unelevated Windows symlink creation.
- [git-bash-and-windows-process-control.md](git-bash-and-windows-process-control.md) - MSYS path conversion mangling non-path arguments, native-process termination from Git Bash, and duplicate loopback listeners on Windows.
- [docker-build-and-compose-secrets.md](docker-build-and-compose-secrets.md) - Dockerfile build-argument scope, non-root Compose secret handling, capabilities, and container metadata retrieval.
- [vietnamese-writing-conventions.md](vietnamese-writing-conventions.md) - Vietnamese capitalization and typography for project documents: why Vietnamese has no Title Case, the five groups in Appendix II of Decree 30/2020/ND-CP, organization and work-title rules, and a pre-submission checklist.
- [docx-report-assembly.md](docx-report-assembly.md) - Assembling a DOCX report with pandoc and OOXML patching: the two schema violations that make Word refuse to open a file, page-size and theme-font defects that survive a valid file, a diagnosis order for table borders that will not render, and self-verification regex traps.
- [windows-uac-elevation-and-launcher-patterns.md](windows-uac-elevation-and-launcher-patterns.md) - Windows UAC elevation, error 740 resolution, `ShellExecuteEx` runas fallback, and integrity level verification.
- [windows-gui-automation.md](windows-gui-automation.md) - Driving a Windows desktop GUI from an agent: extracting an NSIS installer to run an app without UAC, why a Vietnamese IME corrupts synthetic keystrokes, focus-preserving window capture, stale modal dialogs that make menu navigation fail with a misleading error, volatile UIA selectors, MDI child activation traps, and how capture width decides on-page legibility.

## Optional packs copied into this project

Each of these also exists upstream in `${AGENT_CONFIG_ROOT}/project-addons/`. Fix a universal fact in both places or neither.

- [browser-fixture-routing.md](browser-fixture-routing.md) - Playwright `route.fetch` capture before navigation invalidates a response body, Windows `gh --jq` quote stripping, and browser evidence verification.
- [native-directx-overlay-architecture.md](native-directx-overlay-architecture.md) - Native D3D11 `IDXGISwapChain::Present` hook and Dear ImGui in-application overlay architecture.
- [windows-hybrid-gpu-and-display-routing.md](windows-hybrid-gpu-and-display-routing.md) - dGPU-only (MUX) versus Hybrid/Optimus display routing, cross-adapter copy latency, and battery trade-offs.

## Project-specific

- [fingerprint-v3-invariants.md](fingerprint-v3-invariants.md) - SplitBind V3 design invariants: geometry evidence envelope, crop-resilient tile ordering, verification boundary.
- [fingerprint-robustness-experiments.md](fingerprint-robustness-experiments.md) - Robustness investigation: V3-versus-V1 on the identical corpus, four refuted or retracted tuning claims, the first full attack-envelope measurement, and the root cause - robustness is bounded by the geometry hypothesis set, not the watermark. Opens with a reading guide.
- [frontend-design-and-motion.md](frontend-design-and-motion.md) - Frontend art direction and motion budget; the historical section is superseded by `frontend-refinement-qa.md`.
- [frontend-refinement-qa.md](frontend-refinement-qa.md) - Dynamic ETA and elapsed timer, full-UUID display, and multi-tenant scoped job history.
- [production-deployment-readiness.md](production-deployment-readiness.md) - Deployment architecture invariants, CSRF/CSP/CORS boundaries, container packaging traps, account-model distinctions, and evidence discipline for rollouts.
- [container-metadata-backup.md](container-metadata-backup.md) - `docker compose cp` reporting file-not-found on a tmpfs backup, and the verified `exec -T cat` streaming fallback.
- [benign-terminology-and-filter-safety.md](benign-terminology-and-filter-safety.md) - Neutral, academic framing for systems-level technical writing. Deliberately not an upstream pack: the conventions were written for one game-interoperability project and would distort how an agent describes unrelated work.

## Maintenance rules

- One topic per file. The split criterion is topic, not size; passing roughly 20 KB is the signal to check whether a second topic has crept in. Update this index in the same turn as any split.
- Never let the same rule live in two files. If a fact belongs in two places, put it in one and link from the other.
- Domain knowledge belongs here, never in `AGENTS.md`.
- Project-specific facts (dataset paths, model names, business rules) stay in this repository and are never promoted upstream.
- This directory is part of the Git publication set. A fact that names a live host, IP address, cloud subscription, storage bucket, account principal, or credential does not belong here: route it to `docs/internal/`, which `.gitignore` excludes. See `production-deployment-readiness.md` for the split that established this boundary.
