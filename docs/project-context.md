# Project context

## Project overview

SplitBind is a text-integrity tracing system built as the term project (bài tập lớn) for the Information Security course, Nhóm 9. It issues each recipient their own fingerprinted copy of a PDF, then supports verifying which issuance a suspect document came from and whether it has been modified.

Core capabilities:

- Issue per-recipient PDFs carrying a robust fingerprint.
- Detect and help localise modification using a semi-fragile watermark.
- Authenticate the issuance record via a SHA-256 manifest signed with Ed25519.
- Return a verdict with a confidence level, an explicit evidence boundary, and an audit log entry.

Explicit non-goals, taken from `README.md`:

- A watermark is never presented as absolute proof of who leaked a document. Result copy must not attribute a modification or a leak to any person.
- PDFs never enter the message queue; the queue carries only identifiers and minimal metadata.
- Course materials, correspondence with the lecturer, and member device information stay local and outside the repository.

## Repository structure

**The two-branch layout is the most important routing fact in this project.** The repository root and the application code are different branches in different worktrees:

| Branch | Working directory | Tracked files | Contents |
|---|---|---|---|
| `main` (default) | repository root | 4 | Documentation and specification only |
| `feat/splitbind-mvp` | `.worktrees/splitbind-mvp` | 415 | The full application |

Looking for application code in the repository root will find nothing. `apps/`, `services/`, `infra/` and `contracts/` exist only on `feat/splitbind-mvp`.

Remote is `https://github.com/qivarnq3g/splitbind.git`, **visibility PRIVATE** (verified 2026-09-11 via `gh repo view`). The publication set therefore reaches collaborators, not the public internet — but it does reach them, so the content boundary below still applies.

Application layout on `feat/splitbind-mvp`:

- `apps/web` — React + TypeScript + Vite frontend, npm workspace `@splitbind/web`.
- `services/api` — Django REST Framework API and control plane.
- `contracts/{algorithm,jsonschema,openapi}` — shared contracts. Runtime containers must copy the **entire** tree; partial copies cause runtime `FileNotFoundError`.
- `infra/{caddy,compose,docker,scripts}` — reverse proxy config, Compose stack, Dockerfiles, and operational PowerShell/Python scripts.
- `research/`, `fixtures/`, `tests/` — research prototypes, test fixtures, and test suites.
- `.github/workflows/` — `release-images.yaml` (build and publish images by digest) and `smoke.yaml`.

Present in the repository root but excluded from Git by design: course PDFs and spreadsheets, `note.txt`, `docs/course/`, `docs/internal/`, `skills/`, `AGENTS.md`, `CLAUDE.md`, and `.claude/`. See `.gitignore` for the exact rules and the reason each exists.

## Knowledge routing

| Topic or task trigger | Authoritative path | What belongs there / when to read it |
|---|---|---|
| Agent behavioral rules and dispatcher | `AGENTS.md` | How agents must act; read at session start |
| Knowledge lifecycle and persistence | `docs/knowledge/knowledge-lifecycle-guide.md` | 10-step lifecycle, taxonomy, 9 triggers, capture policy |
| Workspace cleanup and resource release | `docs/knowledge/workspace-cleanup-and-lifecycle.md` | Post-task cleanup and handling locked files |
| Engineering rigor and Definition of Done | `docs/knowledge/engineering-rigor-and-completion.md` | Technical design, testing, safety checks, DoD verification |
| Evidence, experiments, claim calibration | `docs/knowledge/experimental-rigor-and-evidence.md` | Before stating an empirical conclusion or comparing runs |
| Tool and plugin registry | `docs/knowledge/agent-tools-and-plugins.md` | When a task needs specialized tools or plugins |
| Full knowledge catalog index | `docs/knowledge/_index.md` | Look up existing knowledge before creating new files |
| Deploying, CSRF/CORS/CSP boundaries, rollout evidence rules | `docs/knowledge/production-deployment-readiness.md` | Before any deployment or cross-origin debugging |
| Fingerprint V3 geometry and sync states | `docs/knowledge/fingerprint-v3-invariants.md` | When touching geometry search or evidence envelopes |
| Frontend art direction, motion, and QA | `docs/knowledge/frontend-design-and-motion.md`, `docs/knowledge/frontend-refinement-qa.md` | Before changing UI, motion, or design tokens |
| Live infrastructure identifiers and rollout evidence | `docs/internal/splitbind-rollout-evidence.md` | Local only, never committed; auditing or rolling back a deployment |
| Project overview and core routing | `docs/project-context.md` | Core facts and routing; read before substantive work |

## Content boundary

`docs/knowledge/` is part of the Git publication set and reaches every collaborator. A fact that names a live host, IP address, cloud subscription, storage bucket, account principal, or credential does **not** belong there — it goes to `docs/internal/`, which `.gitignore` excludes. This boundary was established on 2026-09-11 by splitting run-specific evidence out of `docs/knowledge/production-deployment-readiness.md`.

## Environment and compatibility

Verified from pinned manifests on `feat/splitbind-mvp`:

- Node `>=24.18.0 <25`, pinned to `24.18.0` in `.nvmrc`; npm `>=12 <13`, `packageManager` is `npm@12.0.1`.
- Python `3.11.9` (`.python-version`).
- Rust `1.97.1`, `profile = "minimal"`, components `clippy` and `rustfmt` (`rust-toolchain.toml`).
- npm workspaces resolve `apps/*`.
- Development host is Windows 11 with PowerShell; operational scripts under `infra/scripts/` are a mix of `.ps1` and `.py`.
- Production target is Debian 13 on an Azure Linux VM running Caddy plus Docker Compose, with external managed PostgreSQL (Neon) and S3-compatible object storage (Cloudflare R2).

## Canonical commands

All paths are relative to `.worktrees/splitbind-mvp` unless stated otherwise.

| Purpose | Command | Working directory | Preconditions |
|---|---|---|---|
| Lint every workspace | `npm run lint` | worktree root | `npm install` completed |
| Typecheck every workspace | `npm run typecheck` | worktree root | `npm install` completed |
| Unit and component tests | `npm run test` | worktree root | `npm install` completed |
| Formatting check | `npm run format:check` | worktree root | `npm install` completed |
| Regenerate the API client | `npm run generate:api` | worktree root | OpenAPI contract current |
| Frontend dev server | `npm run dev -w @splitbind/web` | worktree root | Backend reachable or proxied |
| Frontend production build | `npm run build -w @splitbind/web` | worktree root | Runs `tsc --noEmit` first |
| Browser E2E suite | `npm run e2e -w @splitbind/web` | worktree root | Playwright browsers installed |
| Full research smoke plan | `python infra/scripts/run_smoke.py` | worktree root | May require locally generated benchmark reports |
| Release smoke gate | `python infra/scripts/run_smoke.py --release` | worktree root | Excludes the unreleased fingerprint benchmark suite |

These commands were read from `package.json`, `apps/web/package.json`, and `infra/scripts/`. **They were not executed in the session that wrote this file**, so none of them is recorded here as currently passing. Run one and observe its output before claiming it green.

## Engineering conventions

- Runtime container images are referenced as `name@sha256:<digest>`. Mutable tags are not acceptable deployment inputs.
- The build plane is GitHub Actions; the production VM only pulls and runs. Do not build images on the VM or on the workstation for a release.
- Migrations do not run at API startup. A dedicated one-shot migration entrypoint and a fail-closed, idempotent bootstrap command handle schema and first-principal setup.
- Secrets are materialised outside Git and mounted read-only. Document environment variable *names*, never values.
- Evidence language is calibrated: a merged pull request is source publication evidence, not deployment evidence; an authenticated smoke that timed out is an unverified postcondition, not a successful rollout.

## Maintenance

During every substantive task, update this file automatically when a new durable, verified core fact or routing entry is established; no separate documentation request is required. Read the current file before editing, integrate facts into the appropriate section rather than appending a diary, replace or remove stale facts, and reconcile routing entries when a destination changes.
