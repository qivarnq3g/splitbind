# Knowledge Lifecycle and Management Guide

Authoritative reference for sustainable, autonomous knowledge accumulation designed for AI coding agents. This guide establishes a streamlined, in-turn reflection workflow to capture durable technical knowledge autonomously without bureaucratic overhead or deferral to session end.

---

## 1. Core Principle: Immediate In-Turn & Turn-Level Autonomous Persistence (Không trì hoãn)

The agent must **NEVER postpone knowledge persistence until an elusive final session wrap-up**. Multi-turn interactions continuously evolve without an explicit end signal. Waiting for session completion creates severe cognitive amnesia where earlier command failures, sandbox constraints, domain distinctions, database schemas, or permission bypasses are forgotten during subsequent turns. Instead, **the instant an error is resolved, a non-obvious root cause is diagnosed, a domain model distinction is uncovered, or user guidance is received (before outputting ANY conversational text), the agent must autonomously execute the Pre-Response Self-Audit Gate and directly persist any durable knowledge to disk in that very turn.**

### The Immediate In-Turn Resolution Invariant (Lệnh cấm trì hoãn)
Whenever any terminal command, script, tool call, or permission check fails (non-zero exit code, `Access is denied`, parameter syntax error, sandbox rejection), or whenever a non-obvious system reality is discovered (database foreign keys, environment variables, toolchain quirks), and the agent subsequently discovers and verifies the correct fix, the agent **MUST execute a file-write tool call to persist the verified fact into `docs/knowledge/*.md` (and upstream templates) in that very turn**. Continuing multi-step work while leaving resolved knowledge unpersisted on disk is strictly prohibited. Never wait for the user to ask "did you miss anything?".

### Turn-Level Command & Error Audit Gate
Before emitting ANY conversational response (whether answering a troubleshooting question, reporting status, or claiming milestone success), the agent MUST review the conversation trajectory:
- Did ANY command return a non-zero exit code or error output during this workflow?
- Has the confirmed root cause and verified fix for EVERY failed command or unexpected behavior been physically persisted to disk?
- If any error or durable lesson remains unrecorded, conversational output is **STRICTLY BLOCKED**. Execute the edit tool calls first.

### Mandatory Event-Driven Triggers
Persistence is **non-negotiable** whenever ANY of these 6 conditions occurs during a session:
1. **Multi-Attempt Resolution:** Any command sequence, script, or bugfix that required 2 or more attempts before succeeding.
2. **OS / Security / Permission Boundary:** Any workaround bypassing file locks, NTFS ACLs, orphaned SIDs, UAC silent elevation, container engine constraints, or shell incompatibilities.
3. **Non-Obvious Root Cause:** Any diagnostic outcome where the confirmed root cause differed from the surface symptom or initial error text.
4. **New Operational Runbook:** Any reproducible multi-step procedure developed for maintenance, cleanup, deployment, or recovery.
5. **User Architectural or Behavioral Guidance:** Any explicit design decision, preference, or behavioral correction provided by the user.
6. **Analytical, Conceptual, or Mathematical Fallacy Refutation (Chẩn đoán ngụy biện & Bác bỏ giả thuyết):** Any turn where an analytical error, mathematical miscalculation, flawed theoretical premise, incorrect metric assumption, or invalid problem framing is identified, refuted, or admitted. Explaining or debating fallacies in conversational text without first writing the durable corrected principle and empirical ground truth to disk is strictly prohibited.

### The Anti-Discursive Admission Rule (Lệnh cấm thừa nhận sai lầm trong chat mà chưa ghi đĩa)
A chronic operational defect of AI coding agents is treating analytical errors, theoretical fallacies, and conceptual debates as purely "conversational discussion":
- The agent openly admits in chat that an earlier analysis or hypothesis was flawed, points out mathematical fallacies, and explains the correct theory to the user—**YET FAILS to persist those lessons to disk in the same turn** because "no command failed with an error exit code in the shell".
- **The Rule:** Any conversational turn that concedes a prior analytical error, refutes an architectural hypothesis, or identifies a mathematical impossibility is a **Mandatory Persistence Event**.
- The agent is **STRICTLY FORBIDDEN** from outputting conversational explanations or admissions of conceptual mistakes until the corrected principle, empirical data, and boundary conditions have been physically written to `docs/knowledge/*.md` (and upstream templates if generic) via a file-write tool call. Emitting an explanation of why you were wrong without saving the corrected truth first is an immediate gate violation.

### The 3-Layer Diagnostic Persistence & Anti-Partial-Capture Rule (Cấm thiên lệch một phần)
A chronic cognitive failure mode of AI coding agents is **Partial Knowledge Capture (Thiên lệch một phần)**:
- When investigating and resolving an issue (such as a user-reported bug, test failure, silent freeze, or deployment crash), the agent updates a secondary tooling or CLI syntax file (e.g. `agent-tools-and-plugins.md`) and falsely assumes the Pre-Response Gate is satisfied, while completely forgetting to persist the primary root cause and architectural alternative (e.g. library deprecation, missing wheel, silent pip exit, or framework constraint).
- **Mandatory 3-Layer Audit:** Every diagnostic turn MUST audit all 3 layers:
  1. **Layer 1: Root Cause & Runtime Boundary:** Why did the failure occur? What was the exact exception, missing wheel, deprecated package, or silent exit code? (Persist to `docs/knowledge/` such as `engineering-rigor-and-completion.md`).
  2. **Layer 2: Architectural & Engineering Solution:** What is the clean, robust alternative? Why is it superior to ad-hoc workarounds? (e.g. native PyTorch matrix multiplication replacing Faiss, `flush=True` + `tqdm.auto`). (Persist to `docs/knowledge/` such as `engineering-rigor-and-completion.md`).
  3. **Layer 3: Operational Tooling & Workflow Pattern:** How was the artifact deployed, managed, or synchronized? (e.g. `gws drive files update` in-place). (Persist to `docs/knowledge/` such as `agent-tools-and-plugins.md` or `workspace-cleanup-and-lifecycle.md`).
- **The Zero-Partial-Capture Invariant:** A turn that resolves a multi-layer problem but only persists Layer 3 while omitting Layer 1 or 2 is a **direct violation** of the Pre-Response Gate.
- **The Anti-Prompting Standard:** If the user ever has to ask *"Có gì cần cập nhật tri thức không?"* or *"Did you miss anything?"*, it is an indisputable operational failure. The agent must immediately acknowledge the blind spot, persist all missing layers, and harden instruction contracts so the omission cannot recur.

### Secondary Residual Knowledge Sweep (Continuous Self-Learning)
If **NONE** of the 5 primary event triggers fired, the agent is **STILL NOT EXEMPT** from reflection. The agent MUST execute a second-pass review:
- Ask: *"Is there any micro-pattern, obscure CLI flag, undocumented dependency requirement, performance nuance, configuration detail, or project-specific quirk discovered or reinforced during this task — no matter how small — that would make future turns or new agents faster, safer, or more reliable?"*
- **The Zero-Discard Axiom:** All knowledge has cumulative value. If any subtle technical insight or operational detail was verified, capture it into the appropriate `docs/knowledge/*.md` file. Never discard a verified technical fact on the assumption that it is "too minor".


---


## 2. Knowledge Taxonomy & Two-Way Routing

Before writing, categorize candidate facts to determine destination scope (Local Project vs. Upstream Template):

| Category | Description | Scope & Destination |
|---|---|---|
| **Architectural** | System structure, components, new features, stack choices, contracts | Project-specific: `docs/project-context.md` or `docs/knowledge/*.md` |
| **Operational (Project)** | Domain-specific runbooks, bot commands, database migrations, crawler schedules | Project-specific: `docs/knowledge/*.md` or `docs/runbooks/*.md` |
| **Operational (Platform)** | Generic file handling, lock breaking, cleanups, shell wrappers, package management | **Two-Way:** Local `docs/knowledge/*.md` AND Upstream `${AGENT_CONFIG_ROOT}/project-template/docs/knowledge/*.md` |
| **Discovered / Fixes** | Root causes of non-obvious bugs, framework quirks, API constraints | If domain-specific: local `docs/knowledge/*.md`. If runtime/library-generic: also sync upstream |
| **Environmental / Fallbacks** | Host OS boundaries, Windows ACL/UAC quirks, Docker/WSL fallbacks, toolchain flags | **Two-Way:** Local `docs/knowledge/*.md` AND Upstream `${AGENT_CONFIG_ROOT}/project-template/docs/knowledge/*.md` |
| **User Decisions** | Explicit design choices, operational preferences, scope boundaries | Project-specific: `docs/project-context.md` or `docs/knowledge/*.md` |
| **Ephemeral** | Transient task logs, intermediate test outputs, one-off debugging traces | **Do not persist** |

---

## 3. Every-Turn Knowledge Workflow: Pre-Response Self-Audit Gate

Before outputting **ANY** conversational response to the user, the agent MUST execute these 4 steps in the current turn:

1. **Self-Audit (Two-Pass):**
   * *Primary Pass:* Test conversation history and current turn against the 5 Mandatory Event-Driven Triggers. Did any trigger fire?
   * *Secondary Pass:* If no primary trigger fired, perform the Residual Knowledge Sweep. Did this turn uncover any subtle detail, obscure flag, or environmental nuance worth remembering?
2. **Route (Bi-Directional Completeness):** Determine destination scope:
   * If purely local domain logic -> Select narrowest matching file in `docs/knowledge/*.md` (consult `_index.md`).
   * If platform-wide/environmental/toolchain -> Target BOTH the project file AND `${AGENT_CONFIG_ROOT}/project-template/docs/knowledge/*.md` in the exact same turn. Never update upstream without updating local, and vice versa.
3. **Write & Reconcile:**
   * Always read the destination file before editing.
   * Integrate concisely into the relevant section. Replace or remove outdated statements rather than appending a chronological diary.
   * Update `_index.md` immediately if creating or renaming knowledge files.
4. **Disclose:** In the conversational response of that turn, explicitly report every updated knowledge file together with the verified durable fact that justified it.

---

## 4. File Management Rules

* **Safety Boundary:** Never create knowledge files directly in `docs/` root (which may contain user documents). All agent-managed knowledge belongs exclusively in `docs/knowledge/`.
* **Naming:** Use `kebab-case.md` reflecting the domain (e.g., `facebook-crawler-invariants.md`, `hybrid-classification-and-ai-reviewer.md`).
* **File Size Cap:** When a knowledge file exceeds approximately **200 lines**, split it into narrower domain files and update `_index.md`.
* **Prohibited Content:** Never persist secrets, credentials, tokens, session cookies, API keys, private keys, personal data, internal prompts, or private evidence.
* **AGENTS.md Boundary:** `AGENTS.md` is strictly the portable operating contract and dispatcher. Never cram technical facts, domain rules, or specifications directly into `AGENTS.md`. Persist knowledge in `docs/knowledge/*.md` and only add a single-line route to the Dispatcher table if a mandatory workflow gate is required.

---

## 5. Agent Compliance & Zero-Output Enforcement Patterns

Language models and autonomous coding agents naturally treat passive advisory instructions (e.g. *"Remember to read skills"*, *"Ensure knowledge is updated"*) as cognitive internal checklists rather than physical external tool invocations.

To ensure deterministic compliance across different models (Claude, GPT, Gemini, etc.), instruction contracts must apply physical tool-call gates:

1. **Pre-Action Hard Gate:** Strictly prohibit code modifications, script runs, or architectural answers until a file-read tool call has been executed on the relevant `docs/knowledge/` guide or `SKILL.md`.
2. **Zero-Output Rule (Hard Stop Across Every Turn):** Strictly prohibit generating ANY conversational response text (intermediate, troubleshooting, milestone, or final) when any durable knowledge trigger fired unless a file-write tool call has physically succeeded in the turn's tool execution record. Phrasing as an absolute communicative ban across EVERY turn forces the model to complete the disk write before attempting to speak.
3. **Zero-Deferral Invariant (Lệnh cấm trì hoãn):** Strictly prohibit deferring knowledge capture to an elusive "end of session". Multi-turn interactions rarely have an explicit end point. If a trigger fires in turn N, it must be persisted to disk in turn N. Waiting for user intervention or subsequent turns to record knowledge is a fatal defect.
4. **Template Synchronization Pinning:** Automatically verify root instruction contracts via uppercase SHA-256 hashes without loading templates into working memory unless a drift is detected.


---

## Knowledge quality gate and anti-pollution

* **Knowledge Persistence is Not Scope Creep:**
  - In autonomous agent architectures, durable knowledge persistence (capturing generalized engineering principles, verified bug root causes, refuted fallacies, and methodology improvements into `docs/knowledge/*.md` and upstream templates) is a core operating contract, NOT scope creep.
  - **Scope Creep (Thực sự vi phạm phạm vi):** Tự ý sửa đổi logic nghiệp vụ, thêm tính năng mã nguồn ngoài yêu cầu, tái cấu trúc mã không cần thiết, hoặc thay đổi hành vi/kiến trúc sản phẩm mà người dùng không yêu cầu và bài học kỹ thuật không đòi hỏi.
  - **Knowledge Persistence (Cơ chế tự học hợp lệ):** Rút ra bài học tổng quát, có tính tái sử dụng cao từ các sai sót hoặc phản biện đã được xác minh thực tế; cập nhật tài liệu hướng dẫn và điều lệ vận hành để các phiên làm việc và tác tử sau không lặp lại sai lầm.
  - Tuyệt đối cấm đánh đồng việc ghi nhận tri thức bền vững với scope creep. Nghiêm cấm việc vì e sợ scope creep mà ngừng tự học hoặc từ bỏ việc cập nhật tri thức khi một nguyên lý mới được chứng minh.

* **Knowledge Persistence Quality Gate & Anti-Knowledge Pollution (Cổng Chất lượng Tri thức & Chống Ô nhiễm):**
  - Để ngăn chặn việc làm ô nhiễm knowledge base bằng các chi tiết tình huống vụn vặt (situational trivia), một bài học kỹ thuật CHỈ ĐƯỢC PHÉP lưu trữ vào `docs/knowledge/*.md` (và đồng bộ thượng nguồn) khi thỏa mãn đầy đủ 5 tiêu chí:
    1. **Verified by Evidence:** Đã được kiểm chứng thực tế qua lệnh thực thi hoặc công cụ kiểm định cụ thể.
    2. **Generalizable:** Có tính tổng quát cao, đã được trừu tượng hóa khỏi các biến số cá biệt của một lệnh/phiên duy nhất.
    3. **Recurrence Probability:** Nguyên nhân gốc rễ có khả năng cao tái diễn trong các tác vụ, phiên làm việc hoặc dự án khác.
    4. **Proper Scope & Domain Layer:** Thuộc đúng phạm vi của tệp đích (phân loại chính xác: runtime/CLI tools vào `agent-tools-and-plugins.md`, phương pháp luận kỹ thuật vào `engineering-rigor-and-completion.md`, context dự án vào `project-context.md`).
    5. **Non-Duplicate:** Chưa từng tồn tại trong knowledge base; nếu đã tồn tại, phải tinh chỉnh/hợp nhất thay vì tạo thêm mục trùng lặp.
  - *Chống ô nhiễm tri thức (Anti-Knowledge Pollution):* Lỗi cú pháp do gõ nhầm (typo) nhất thời của một câu lệnh, các dữ liệu tạm thời, hoặc các biến số cục bộ của một lần chạy cá biệt TUYỆT ĐỐI KHÔNG được đưa vào knowledge base.

* **Rigorous Verification of Knowledge Updates (Kiểm định Thực chất Việc Ghi đĩa):**
  - Không bao giờ tuyên bố đã hoàn tất cập nhật tri thức hoặc đồng bộ thượng nguồn nếu chỉ chạy mỗi lệnh `git diff --check` (vốn chỉ kiểm tra định dạng khoảng trắng và ký tự kết thúc dòng).
  - Kiểm định việc cập nhật tri thức bắt buộc phải bao gồm:
    1. Kiểm tra nội dung chèn bằng `git diff -- <files>` hoặc đối chiếu trực tiếp các dòng đã sửa.
    2. So sánh tính toàn vẹn (bằng nội dung hoặc mã băm SHA-256) giữa các bản sao trong kiến trúc đa tầng (the local `docs/knowledge/` and the single upstream store under `${AGENT_CONFIG_ROOT}/project-template/`).
    3. Xác nhận không có bất kỳ tệp mã nguồn chức năng hay tệp dự án không liên quan nào bị thay đổi ngoài ý muốn.

