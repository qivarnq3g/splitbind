# SplitBind Frontend Complete Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rebuild the entire frontend UI of SplitBind from the ground up into a modern, distinctive, responsive, and art-directed cryptographic workstation using Hallmark design principles and GSAP motion orchestration, while preserving all existing application logic, API contracts, and tests.

**Architecture:** Redesign the presentation layer across design tokens (`tokens.css`), responsive layout shell (`AppShell`, mobile navigation drawer, header), atomic presentation components (`CompactIdentifier`, `DocumentFileInput`, `StatusBadge`, `WorkflowSteps`, `EmptyState`), motion infrastructure (`MotionRoute`, GSAP timeline entrances, hover/micro-interactions), and page-level workbenches (`LoginPage`, `IssueDocumentPage`, `JobDetailPage`, `IssuanceDetailPage`, `VerifyDocumentPage`, `VerificationDetailPage`, `EvidenceSummary`, `IntegrityMap`). Remove the restrictive `min-width: 64rem` constraint to support full responsive fidelity across mobile, tablet, and desktop viewports.

**Tech Stack:** React 19, TypeScript 5.9, Vite 8, GSAP 3.15 + `@gsap/react`, Lucide React, TanStack Query 5, React Router 7, Vitest + React Testing Library.

**Spec:** [`docs/superpowers/specs/2026-09-08-frontend-redesign-spec.md`](../specs/2026-09-08-frontend-redesign-spec.md)

## Global Constraints

- Preserve all API contracts, schemas, React Query mutations/queries, authentication session handling, and validation rules.
- Maintain 100% pass rate on all existing Vitest test suites (`design-system.test.tsx`, `evidence-copy.test.tsx`, `issuance-flow.test.tsx`, `verification-flow.test.tsx`, `runtime-assets.test.ts`, `client.test.ts`, `client.node.test.ts`).
- Enforce strict token declaration: every `var(--token)` referenced in CSS must be declared in `tokens.css` or `app.css`.
- Ensure strict accessibility: keyboard navigation, aria labels, role attributes, focus rings, and WCAG AA color contrast.
- Ensure strict performance and reduced-motion compliance: all GSAP animations must use `gsap.context()` / `useGSAP`, clean up properly on unmount, use transform/opacity, and respect `prefers-reduced-motion: reduce`.
- Full responsive support: mobile (< 768px), tablet (768px - 1024px), standard desktop (1024px - 1440px), and large desktop (> 1440px). No horizontal overflow.
- Strict emoji-free policy across code, UI text, and documentation.

---

### Task 1: Design Tokens and Responsive Base Architecture

**Files:**
- Modify: `apps/web/tokens.css`
- Modify: `apps/web/src/styles/app.css:1-120`
- Test: `apps/web/src/test/design-system.test.tsx`

**Interfaces:**
- Consumes: Existing token definitions, font families (`Manrope Variable`, `Inter Variable`, `Cascadia Mono`).
- Produces: Enhanced design tokens including responsive breakpoints, elevation layers, subtle glass/surface tokens, brand accent shifts, and container widths.

- [x] **Step 1: Expand `tokens.css` with responsive container tokens and polished surface colors**
- [x] **Step 2: Update base reset and viewport constraints in `app.css`**
- [x] **Step 3: Run design token test**

---

### Task 2: Shared UI Components and Empty States

**Files:**
- Create: `apps/web/src/components/EmptyState.tsx`
- Modify: `apps/web/src/components/DocumentFileInput.tsx`
- Modify: `apps/web/src/components/CompactIdentifier.tsx`
- Modify: `apps/web/src/components/StatusBadge.tsx`
- Modify: `apps/web/src/components/WorkflowSteps.tsx`
- Test: `apps/web/src/test/design-system.test.tsx`

**Interfaces:**
- Consumes: Lucide icons, React props.
- Produces: Reusable `EmptyState`, elevated `DocumentFileInput` with drag-and-drop visual states, interactive copy button in `CompactIdentifier`, modern animated `StatusBadge`, and responsive step indicator `WorkflowSteps`.

- [x] **Step 1: Implement `EmptyState` component**
- [x] **Step 2: Redesign `DocumentFileInput` with enhanced dropzone visuals**
- [x] **Step 3: Elevate `StatusBadge`, `CompactIdentifier`, and `WorkflowSteps`**
- [x] **Step 4: Run component tests**

---

### Task 3: AppShell, Responsive Navigation & GSAP Motion Infrastructure

**Files:**
- Modify: `apps/web/src/components/AppShell.tsx`
- Modify: `apps/web/src/components/MotionRoute.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/design-system.test.tsx`

- [x] **Step 1: Refactor `AppShell.tsx` for responsive navigation**
- [x] **Step 2: Enhance `MotionRoute.tsx` with GSAP page choreography**
- [x] **Step 3: Verify AppShell and navigation tests**

---

### Task 4: Redesign Login Page

**Files:**
- Modify: `apps/web/src/pages/LoginPage.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/design-system.test.tsx`

- [x] **Step 1: Elevate `LoginPage.tsx` layout and styling**
- [x] **Step 2: Verify Login test**

---

### Task 5: Redesign Issuance & Verification Workbenches

**Files:**
- Modify: `apps/web/src/pages/IssueDocumentPage.tsx`
- Modify: `apps/web/src/pages/VerifyDocumentPage.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/issuance-flow.test.tsx`
- Test: `apps/web/src/test/verification-flow.test.tsx`

- [x] **Step 1: Redesign `IssueDocumentPage.tsx`**
- [x] **Step 2: Redesign `VerifyDocumentPage.tsx`**
- [x] **Step 3: Verify issuance and verification test suites**

---

### Task 6: Redesign Job & Record Detail Pages with Evidence Visualizer

**Files:**
- Modify: `apps/web/src/pages/JobDetailPage.tsx`
- Modify: `apps/web/src/pages/IssuanceDetailPage.tsx`
- Modify: `apps/web/src/pages/VerificationDetailPage.tsx`
- Modify: `apps/web/src/features/evidence/EvidenceSummary.tsx`
- Modify: `apps/web/src/features/evidence/IntegrityMap.tsx`
- Modify: `apps/web/src/styles/app.css`
- Test: `apps/web/src/test/evidence-copy.test.tsx`

- [x] **Step 1: Redesign `JobDetailPage.tsx` and `IssuanceDetailPage.tsx`**
- [x] **Step 2: Redesign `VerificationDetailPage.tsx` and `EvidenceSummary.tsx`**
- [x] **Step 3: Enhance `IntegrityMap.tsx` SVG visualizer**
- [x] **Step 4: Run evidence copy tests**

---

### Task 7: Full Verification, Production Build & E2E Validation

**Files:**
- All modified frontend files in `apps/web`

- [x] **Step 1: Run complete Vitest suite**
- [x] **Step 2: Run TypeScript typecheck**
- [x] **Step 3: Run production Vite build**
- [x] **Step 4: Verify responsive layout and interactions**

