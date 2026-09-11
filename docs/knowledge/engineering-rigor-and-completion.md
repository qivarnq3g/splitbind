# Engineering Rigor, Safety, and Completion Guide

A comprehensive guide for technical design standards, data safety boundaries, and the Definition of Done (DoD) for AI agents.

---

## 1. High-Level Engineering Rigor

* **Best-Quality and Optimized Design:**
  * Always prefer the best-quality, most optimized design that fully satisfies verified requirements **regardless of implementation complexity**.
  * Never hard-code values, special-case outputs to fake success, weaken safeguards, bypass test cases, or conceal technical defects.
* **Inspect Before Editing:**
  * Thoroughly examine existing files and structures before making modifications. Preserve unrelated work and keep changes tightly focused.
* **Rigorous Diagnosis:**
  * Distinguish symptoms from confirmed root causes.
  * Rank plausible causes in order, starting with the safest and highest-information checks.
  * Challenge faulty problem framing when evidence supports a better approach; clearly articulate trade-offs, technical risks, and limitations.
* **Verify by Observed Execution Only:**
  * Use repository-provided scripts and documented canonical commands.
  * Never claim a check or test passed unless it was physically executed and its output observed directly.
* **Zero-Comment Invariant (Tuyệt đối không comment trừ khi người dùng yêu cầu):**
  * Tuyệt đối không tự ý viết thêm comment, docstring, giải thích hoặc chú thích khối trong mã nguồn, kịch bản, hay notebook trừ khi người dùng yêu cầu rõ ràng.
  * Viết mã nguồn sạch, tự giải thích (self-documenting) thông qua việc đặt tên hàm, biến và cấu trúc logic sáng sủa, tường minh thay vì dựa vào chú thích.
  * Khi sửa đổi mã nguồn sẵn có, chỉ bảo toàn các comment cũ không liên quan đến phạm vi thay đổi; tuyệt đối không chèn thêm chú thích mới.

---

## 2. Data Safety and Git Trust Boundaries

* **Preserve User Work and State:**
  * Never discard uncommitted work or overwrite user code merely to simplify implementation.
  * Treat all destructive operations as safety-sensitive: verify exact target paths, confirm ownership, check symlink boundaries, and prefer recoverable operations.
* **Git Trust Boundaries:**
  * Treat the working directory and the Git staging/publication set as separate trust boundaries.
  * Review exact staged paths and diff content before any commit or push; avoid broad staging (`git add .`) when local-only or unrelated files exist.
  * A rule in `.git/info/exclude` never travels with the repository and never appears in a diff, so nobody who clones can see or review it. It is the right place for a throwaway personal filter and the wrong place for any deliberate publication decision. Record those in a committed `.gitignore` with a comment stating why: an exclusion nobody can review is indistinguishable from an omission, and it silently stops being enforced for every other clone.
  * Before lifting any exclusion, scan what the change would newly expose instead of trusting the directory reputation. Grep the candidate files for live hostnames, IP addresses, cloud subscription and account identifiers, storage endpoints, administrator principals and credentials. Documentation trees accumulate deployment evidence, and the exposure is usually concentrated: one run-log file can hold every identifier while every other file is clean. Split the run-specific evidence into an excluded path and keep the generalizable lesson publishable, rather than excluding the whole directory.
* **Strict Confidentiality:**
  * Never publish or persist secrets, API keys, credentials, tokens, session cookies, personal data, or private evidence.
  * If sensitive content is detected in version history, immediately halt publication, identify affected refs, rotate credentials, and obtain explicit user authorization before rewriting history.

---

## 3. Definition of Done (DoD) & Completion Criteria

A technical task is considered **fully complete** only when all 6 criteria are met:

1. **Requested Behavior Verified:** The requested functionality or fix works correctly in practice.
2. **Objective Evidence Observed:** Applicable verification checks and test suites have been executed and observed passing.
3. **Documentation Consistency:** Code implementation and relevant documentation agree without discrepancies.
4. **Pre-Response Self-Audit & Knowledge Maintenance Complete:** Before emitting conversational output, execute the Pre-Response Self-Audit Gate. Perform immediate in-turn persistence: review all commands in the trajectory for non-zero exit codes, permission denials, or tool friction, and verify that EVERY resolved error and technical lesson is physically committed to `docs/knowledge/*.md` (and upstream `${AGENT_CONFIG_ROOT}/project-template/docs/knowledge/*.md` if platform/toolchain-generic) before reporting progress or completion. Conversational output is strictly blocked while resolved errors remain unrecorded.
5. **Clean Workspace:** All temporary files, scratch scripts (in `scratch/`), and lingering background processes or file handles have been safely removed.

6. **Transparent Reporting:**
   * Lead with the direct result, followed by supporting evidence and limitations.
   * Explicitly disclose any autonomous updates to `AGENTS.md` or `docs/knowledge/*.md` files along with the verified facts that justified them.

---

## 4. Related guides

The material formerly inlined here as "Continuous Learning & Anti-Regression Invariants" now lives with its owning topic, so it is maintained in exactly one place:

- Knowledge persistence, the quality gate, and anti-pollution rules -> [`knowledge-lifecycle-guide.md`](knowledge-lifecycle-guide.md)
- Feedback handling, anti-overcorrection, evidence freshness, authority calibration, and anti-hyperbole in reporting -> [`experimental-rigor-and-evidence.md`](experimental-rigor-and-evidence.md) (Part III)
- Cryptographic and security claim boundaries -> `optional/knowledge/infosec-crypto-verification.md`, copied into a project only when the domain applies
