# SplitBind Frontend Motion Art Direction Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a dedicated Motion Art Direction Pass across the SplitBind frontend to establish a coherent, memorable cryptographic motion language (`Document -> Hash -> DWT/DCT -> Signature/Verification -> Evidence -> Cryptographic Seal`) using Hallmark visual discipline and GSAP orchestration, while maintaining 100% test passing rates, accessibility, and zero backend/API changes.

**Architecture:** Build a shared cryptographic visual motif system (`CryptographicMotif`, signal decomposition lattice, hash fragments, node convergence) and integrate it into page-level workbench chambers (`IssueDocumentPage`, `VerifyDocumentPage`, `JobDetailPage`, `VerificationDetailPage`, `IssuanceDetailPage`, `MotionRoute`). Keep all form inputs fast and accessible, scope all animations to GSAP contexts with full `prefers-reduced-motion` compliance, and avoid unneeded ScrollTrigger or Three.js dependencies.

**Tech Stack:** React 19, TypeScript 5.9, GSAP 3.15 + `@gsap/react`, Lucide React, Vitest, Playwright Chromium.

**Spec:** [`docs/superpowers/specs/2026-09-08-frontend-motion-art-direction-spec.md`](../specs/2026-09-08-frontend-motion-art-direction-spec.md)

## Global Constraints

- Do not redesign the application from scratch; treat the current visual redesign as the solid foundation.
- Do not change backend behavior, API contracts, routing, authentication, business logic, or validation rules.
- Maintain 100% pass rate on all existing Vitest test suites (`design-system.test.tsx`, `evidence-copy.test.tsx`, `issuance-flow.test.tsx`, `verification-flow.test.tsx`, `runtime-assets.test.ts`, `client.test.ts`, `client.node.test.ts`).
- Enforce strict token declaration: every `var(--token)` referenced in CSS must be declared in `tokens.css` or `app.css`.
- Ensure strict accessibility: keyboard navigation, aria-live regions, focus rings, and WCAG AA contrast.
- Ensure strict performance: GSAP animations use `useGSAP()` or `gsap.context()`, clean up timelines on unmount, use transform/opacity, and respect `prefers-reduced-motion: reduce`.
- Full responsive support: mobile (< 768px), tablet (768px - 1024px), standard desktop (1024px - 1440px), and large desktop (> 1440px). No horizontal overflow.
- Strict emoji-free policy across code, UI text, and documentation.

---

### Task 1: Reusable Cryptographic Motion Motif & Signal Decomposition Primitives

**Files:**
- Create: `apps/web/src/components/CryptographicMotif.tsx`
- Modify: `apps/web/tokens.css`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/design-system.test.tsx`

**Interfaces:**
- Consumes: Design tokens, Lucide icons.
- Produces: `<CryptographicMotif stage="idle" | "hashing" | "decomposing" | "signing" | "verifying" | "sealed" | "tampered" />` component with SVG frequency wavelets, coordinate axes, hash fragments, and converging nodes.

- [ ] **Step 1: Define motion tokens and SVG filter assets in `tokens.css` and `app.css`**
- [ ] **Step 2: Implement `CryptographicMotif.tsx` component with GSAP orchestrated states**
- [ ] **Step 3: Run design system tests to verify zero regressions**
- [ ] **Step 4: Commit Task 1 changes**

---

### Task 2: Issue Document Signature Experience - Cryptographic Ingestion & Signing Chamber

**Files:**
- Modify: `apps/web/src/pages/IssueDocumentPage.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/issuance-flow.test.tsx`

**Interfaces:**
- Consumes: `useIssueDocumentMutation`, `CryptographicMotif`.
- Produces: Coordinated 5-step issuance motion sequence: Intake -> SHA-256 Hashing -> DWT Frequency Decomposition -> Ed25519 Signing Nodes Convergence -> Artifact Sealed Handoff.

- [ ] **Step 1: Enhance `IssueDocumentPage.tsx` with dedicated cryptographic chamber and stage telemetry**
- [ ] **Step 2: Orchestrate issuance timeline in `IssueDocumentPage.tsx` using `useGSAP`**
- [ ] **Step 3: Add supporting CSS styles for decomposition layers and node convergence**
- [ ] **Step 4: Run issuance flow unit tests**
- [ ] **Step 5: Commit Task 2 changes**

---

### Task 3: Verify Document Signature Experience - Coordinated Multi-Pass Inspection Chamber

**Files:**
- Modify: `apps/web/src/pages/VerifyDocumentPage.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/verification-flow.test.tsx`

**Interfaces:**
- Consumes: `useVerifyDocumentMutation`, `CryptographicMotif`.
- Produces: Coordinated verification sequence: Intake -> Multi-pass Laser Scanner -> Frequency Signal Layer Reveal -> Signal Comparison -> Resolution Handoff.

- [ ] **Step 1: Elevate `VerifyDocumentPage.tsx` with inspection chamber and synchronized scanning telemetry**
- [ ] **Step 2: Orchestrate verification timeline using `useGSAP` with distinct scanning passes**
- [ ] **Step 3: Add CSS for multi-pass beam, frequency grid comparison, and phase indicators**
- [ ] **Step 4: Run verification flow unit tests**
- [ ] **Step 5: Commit Task 3 changes**

---

### Task 4: Job Lifecycle Spatial Progression & Flow Visualization

**Files:**
- Modify: `apps/web/src/pages/JobDetailPage.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/issuance-flow.test.tsx`

**Interfaces:**
- Consumes: `useJobQuery`, OpenAPI schema job status.
- Produces: Spatial progression track (`created` -> `queued` -> `processing` -> `succeeded` / `failed`), geometric pulse, live telemetry stream.

- [ ] **Step 1: Refactor `JobDetailPage.tsx` lifecycle track into a spatial progression pipeline**
- [ ] **Step 2: Add subtle GSAP state interpolation and signal pulse for active job polling**
- [ ] **Step 3: Add CSS for spatial progression track and telemetry pulse**
- [ ] **Step 4: Run tests to verify job polling and navigation contracts**
- [ ] **Step 5: Commit Task 4 changes**

---

### Task 5: Authoritative Result Payoff & Cryptographic Seal Construction

**Files:**
- Modify: `apps/web/src/pages/VerificationDetailPage.tsx`
- Modify: `apps/web/src/pages/IssuanceDetailPage.tsx`
- Modify: `apps/web/src/features/evidence/EvidenceSummary.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/evidence-copy.test.tsx`

**Interfaces:**
- Consumes: Issuance & Verification evidence data, integrity status.
- Produces: Authoritative seal construction sequence for intact verifications and distinct failure discrepancy isolation for tampered documents.

- [ ] **Step 1: Enhance `VerificationDetailPage.tsx` with seal construction animation**
- [ ] **Step 2: Implement distinct failure discrepancy isolation for tampered/modified results**
- [ ] **Step 3: Refine `EvidenceSummary.tsx` and `IssuanceDetailPage.tsx` with progressive evidence reveal**
- [ ] **Step 4: Run evidence copy tests**
- [ ] **Step 5: Commit Task 5 changes**

---

### Task 6: Page Transition Continuity, ScrollTrigger Restraint & Accessibility Guardrails

**Files:**
- Modify: `apps/web/src/components/MotionRoute.tsx`
- Modify: `apps/web/src/components/AppShell.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/design-system.test.tsx`

**Interfaces:**
- Consumes: React Router location, browser `prefers-reduced-motion`.
- Produces: Restrained spatial transitions between workflow stages, guarded ScrollTrigger registration, zero-transform fallback for reduced-motion.

- [ ] **Step 1: Refine `MotionRoute.tsx` for spatial continuity across cryptographic pipeline stages**
- [ ] **Step 2: Audit ScrollTrigger usage to ensure no scroll-jacking and headless JSDOM safety**
- [ ] **Step 3: Verify complete `prefers-reduced-motion` compliance across all components**
- [ ] **Step 4: Run complete Vitest suite**
- [ ] **Step 5: Commit Task 6 changes**

---

### Task 7: Full Browser Visual Inspection (4 Viewports), Verification & Comprehensive Reporting

**Files:**
- All modified frontend files in `apps/web`

- [ ] **Step 1: Run TypeScript typecheck**
- [ ] **Step 2: Run Vitest complete suite**
- [ ] **Step 3: Run production Vite build**
- [ ] **Step 4: Perform interactive Chromium browser QA across 4 viewports (1920x1080, 1280x800, 768x1024, 375x667)**
- [ ] **Step 5: Run `git diff --check` and verify clean workspace**
- [ ] **Step 6: Deliver comprehensive technical evaluation report**
