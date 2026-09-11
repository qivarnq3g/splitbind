# Agent Tools and Plugins

Registry of plugins and skills used across sessions. Agents check this file when a task would benefit from a plugin to verify availability and find install commands.

## How to use this registry

1. Before starting a task that may need a plugin, check if it's listed here.
2. Run the **verification command** for your platform to check if it's installed.
3. If missing, use the **install command** for your platform.
4. After installing a new plugin or discovering a useful one, add it to this registry.

## Skill Classification and Usage Rules

AI agents must distinguish between two fundamental categories of skills:

### 1. Process Skills (Universal Engineering Methodology)
Skills that govern software engineering rigor, problem analysis, and workflow execution (e.g., from Superpowers: `systematic-debugging`, `test-driven-development`, `writing-plans`, `executing-plans`, `verification-before-completion`, `brainstorming`).
* **Usage Principle:** When diagnosing an unexpected failure, implementing a non-trivial feature, or verifying completion, **actively follow or invoke the relevant process skill**. Do not bypass structured debugging with raw trial-and-error commands or unstructured guessing.
* **CLI/Shell Failure Scope:** `systematic-debugging` applies universally to **all command-line, script, or tool failures** (e.g. `Access is denied`, non-zero exit codes, permission denials, locked handles, missing binaries), not merely source code bugs. When a command fails, agents are strictly forbidden from executing speculative alternative CLI commands until the failure's root cause (ACL, process lock, path resolution, environment variable) has been isolated.
* **Non-Negotiable Verification:** Before declaring any task complete, apply `verification-before-completion` discipline: directly run tests, observe output, verify runtime state, and confirm clean workspace.

### 2. Domain Skills (Specialized Operational Capabilities)
Skills that provide domain-specific attack patterns, forensic procedures, protocol analysis, or specialized tool usage (e.g., `analyzing-cobalt-strike`, `detecting-kerberoasting`, `hunting-evtx-with-chainsaw`).
* **Usage Principle:** Invoke domain skills **only** when the user's task explicitly falls into that specialized domain. Never guess or invoke unrelated domain skills for standard software development, bot maintenance, or web development tasks.

---

## Plugins

### Superpowers

Complete software development methodology with composable skills: brainstorming, planning, TDD, debugging, code review, and subagent-driven development.

| Platform | Install command | Verification command |
|---|---|---|
| Antigravity | `agy plugin install https://github.com/obra/superpowers` | `agy plugin list` |
| Claude Code | `/plugin install superpowers@claude-plugins-official` | `/plugin list` |
| Codex CLI | `/plugins` → search `superpowers` → Install | `/plugins` |
| Gemini CLI | `gemini extensions install https://github.com/obra/superpowers` | `gemini extensions list` |
| Cursor | `/add-plugin superpowers` | Plugin marketplace |

**Key skills included:** brainstorming, writing-plans, subagent-driven-development, test-driven-development, systematic-debugging, verification-before-completion, requesting-code-review, finishing-a-development-branch

**Source:** https://github.com/obra/superpowers

### Google Workspace CLI (gws)

Official Google Workspace CLI tool (`@googleworkspace/cli`) for managing Google Drive, Sheets, Gmail, Docs, and cloud file sharing directly from the command line.

| Platform | Install command | Verification command |
|---|---|---|
| Windows / Node.js | `npm install -g @googleworkspace/cli` | `gws.cmd auth status` / `gws --help` |
| macOS / Linux | `npm install -g @googleworkspace/cli` | `gws auth status` / `gws --help` |

**Key CLI commands & patterns:**
- **Status & Auth:** `gws auth status` (checks current authenticated user, token validity, enabled APIs, and scopes).
- **Create Folder:** `gws.cmd drive files create --json "{\"name\": \"<folder_name>\", \"mimeType\": \"application/vnd.google-apps.folder\"}"`
- **Upload File:** `gws.cmd drive files create --json "{\"name\": \"<name>\", \"parents\": [\"<folder_id>\"]}\" --upload <local_path>`
- **Update Existing File In-Place:** `gws.cmd drive files update --upload <path> --params "{\"fileId\": \"<id>\"}"` (preserves original Drive File ID and Colab link).
- **Share / Permissions:** `gws.cmd drive permissions create --params "{\"fileId\": \"<id>\", \"sendNotificationEmail\": true}" --json "{\"role\": \"writer\", \"type\": \"user\", \"emailAddress\": \"<email>\"}"`
- **Windows CLI Quirks:** Under Windows PowerShell/subprocess, invoke `gws.cmd` (or via Python `shell=True`) to handle `.cmd` batch dispatch properly and avoid `FileNotFoundError`.
- **Upload Path Sandbox Constraint:** `gws` validates that `--upload <path>` must resolve inside the current working directory (`Cwd`); passing an external absolute path produces `validationError: ... which is outside the current directory`. Move or stage files into the active workspace directory before invoking `gws drive files create --upload`.
- **PowerShell JSON Argument Escaping:** In PowerShell CLI arguments, passing `--json` or `--params` with raw double quotes strips them upon child process invocation, yielding `error[validation]: Invalid --json body: key must be a string at line 1 column 2`. Explicitly escape inner quotes as `\"` (e.g., `'$jsonBody = \"{\\\"name\\\": \\\"val\\\", \\\"parents\\\": [\\\"id\\\"]}\"'`) or store payload in a `.json` file.
- **Python Subprocess Automation Pattern:** To bypass Windows shell quoting edge cases entirely when constructing complex JSON queries (e.g. folder queries with single quotes in `--params` or nested objects), invoke `gws.cmd` via Python script or `subprocess.run(["gws.cmd", "drive", ...], shell=True)` with `json.dumps(payload)`. This guarantees 100% compliant JSON string serialization without shell-level escaping failures.
- **PowerShell `python -c` Quoting & UTF-8 Encoding:**
  - Running inline `python -c "..."` from PowerShell strips unescaped double quotes inside the string, causing Python `SyntaxError: unterminated string literal`. Use single quotes for the outer string (`python -c '...'`) or write a dedicated `.py` scratch script.
  - On Windows console, Python stdout defaults to legacy `cp1252` encoding. Printing Vietnamese characters without explicit stream re-encoding causes `UnicodeEncodeError: 'charmap' codec can't encode character`. Add `import sys; sys.stdout.reconfigure(encoding='utf-8')` at script entry, set environment variable `PYTHONIOENCODING=utf-8`, or use `open(..., encoding='utf-8')` for all I/O.
- **PowerShell Nested CLI Command Variable Expansion (`powershell -Command "..."`):**
  - When executing commands inside an existing PowerShell host (such as `run_command` or nested child sessions), passing double-quoted strings like `powershell -Command "$f.Count"` causes the outer PowerShell to interpolate `$f` *before* launching the nested process. Because `$f` is undefined in the outer scope, it expands to an empty string, transforming the command into `.Count` and crashing with `ParserError: Unexpected token '.Count' in expression or statement`.
  - **Universal Invariant:** Do not nest `powershell -Command` within an existing PowerShell session; run statements directly. If nested invocation is strictly required, use single quotes (`powershell -Command '$f.Count'`) or escape the dollar sign with a backtick (`` `$f.Count ``) to prevent premature variable expansion.


### Playwright (Browser Automation & Visual QA)

Headless browser automation tool used for end-to-end testing, visual QA auditing, responsive layout checks, and screenshot capture across viewports.

| Platform | Install command | Verification command |
|---|---|---|
| Windows / Node.js | `npm install playwright` / `npx playwright install` | `npx playwright --version` |
| macOS / Linux | `npm install playwright` / `npx playwright install` | `npx playwright --version` |

**Host & Execution Quirks:**
- **Pre-installed Chromium Path on Windows Host:** If Playwright fails with `Executable doesn't exist at C:\Users\<user>\AppData\Local\ms-playwright\chromium_headless_shell-<rev>\...`, inspect `C:\Users\<user>\AppData\Local\ms-playwright` for installed browser revisions (e.g., `chromium-1234\chrome-win64\chrome.exe`) and pass `executablePath: "C:/Users/<user>/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe"` into `chromium.launch({ headless: true, executablePath: ... })`.

### Claude in Chrome (MCP browser control)

Browser automation driven through the user's real Chrome profile (`mcp__claude-in-chrome__*`). Unlike Playwright it reuses the live browser session, so authenticated production pages can be inspected without re-login and without handling credentials.

**Host & Execution Quirks:**
- **`resize_window` silently fails on a maximized window:** The tool returns `Successfully resized window containing tab <id> to <w>x<h> pixels` while the page viewport never changes. Observed 2026-09-11 on Windows 11: two consecutive calls (400x860, then 420x900) both reported success, yet `window.innerWidth` stayed `1680`, `outerWidth` stayed `1920`, and screenshots kept the desktop layout. The success message is not evidence of a viewport change. Always read `innerWidth` from the page before treating any screenshot as a responsive-breakpoint check. Probable cause, not confirmed in session: Chrome's `windows.update` ignores `width`/`height` while the window `state` is `maximized`. For reliable multi-viewport QA use Playwright with an explicit `viewport`, or have the user unmaximize the window first.
- **Console capture starts at first read, not at page load:** `read_console_messages` returns `No console messages found for this tab` when the page loaded before the first call, because tracking begins when the tool is first invoked. Call it once, then reload the page, then read again to capture load-time errors.
- **Screenshot frame is not the CSS viewport:** the returned image dimensions (and the reported coordinate frame) can differ from `innerWidth`/`clientWidth`. Measure layout with `getBoundingClientRect()` through `javascript_tool` rather than estimating pixel positions off a screenshot.

### Windows Dev Skills (WinUI & Windows App SDK)

Official Microsoft plugins and skills for Windows application development (WinUI 3, Windows App SDK, packaging, MSIX, and Win32 modernization).

| Platform | Install command | Verification command |
|---|---|---|
| Antigravity | `agy plugin install <cloned_repo_path>/plugins/winui/agent-plugin` | `agy plugin list` |
| Claude Code | `claude plugin marketplace add microsoft/win-dev-skills` && `claude plugin install winui@win-dev-skills` | `claude plugin list` |
| GitHub Copilot CLI | `gh copilot plugin install winui@awesome-copilot` | `gh copilot plugin list` |

**Key skills included:**
- `winui-setup`: Set up dev environment for Windows App SDK and WinUI 3 (winget, .NET, SDK probes).
- `winui-dev-workflow`: End-to-end development workflow (build, run, test, debug).
- `winui-design`: Fluent design system guidelines, XAML styles, and accessibility.
- `winui-packaging`: MSIX packaging, sparse packages, package identity, certificates, and code signing.
- `winui-code-review`: Code quality and pattern audits for modern Windows apps.
- `winui-ui-testing`: Automated UI testing for WinUI 3 / desktop applications.
- `winui-wpf-migration`: Guidance for migrating WPF/WinForms code to WinUI 3 / Windows App SDK.
- `winui-session-report`: Summarize development progress and architectural decisions.

**Build and Test Invariants:**
- **Windows App SDK 1.6+ PublishSingleFile Requirement:** When configuring `<PublishSingleFile>true</PublishSingleFile>` in an unpackaged WinUI 3 project (`<UseWinUI>true</UseWinUI>`), `Microsoft.WindowsAppSDK.SingleFile.targets` enforces that `<EnableMsixTooling>true</EnableMsixTooling>` must also be added to `<PropertyGroup>`. Otherwise, compilation fails with `error: PublishSingleFile requires EnableMsixTooling for embedded resources.pri generation`.
- **CommunityToolkit.Mvvm Async RelayCommand Test Execution:** When invoking an async `[RelayCommand]` method in unit tests or programmatic runners, calling standard `ICommand.Execute(null)` returns synchronously while the task continues in the background. Downstream checks that inspect state or call other methods with `if (IsBusy) return;` will observe intermediate state or get rejected. Always cast to `CommunityToolkit.Mvvm.Input.IAsyncRelayCommand` and call/await `ExecuteAsync(null)` to verify full execution.

### Scientific Agent Skills (K-Dense)

164 research skills for science and technical writing: figures, schematics, statistics, scientific writing, literature lookup, plus domain libraries for biology and chemistry. MIT licensed. Source: https://github.com/K-Dense-AI/scientific-agent-skills

| Platform | Install command | Verification command |
|---|---|---|
| Claude Code | see the two-step workaround below | `claude plugin list` |
| Any platform with an Agent Skills loader | copy `skills/<name>/` into the platform's skills directory | platform skill list |

**The repository is a plugin, not a marketplace.** It ships `plugin.json` at the root but no
`.claude-plugin/marketplace.json`, so `claude plugin marketplace add K-Dense-AI/scientific-agent-skills`
fails with `Marketplace file not found`. Two further failure modes appear before that one:

1. `marketplace add <owner/repo>` clones over **SSH** and fails with `Host key verification failed`
   when GitHub is not in `known_hosts`. Pass the full HTTPS URL instead.
2. The clone then exceeds the default 120 s git timeout. Raise it:
   `CLAUDE_CODE_PLUGIN_GIT_TIMEOUT_MS=900000`.

Working install: clone the plugin, wrap it in a local marketplace, then install from that path.

```bash
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/K-Dense-AI/scientific-agent-skills.git
git sparse-checkout set skills     # 39 MB instead of the full repo with docs/images
# write .claude-plugin/marketplace.json in the PARENT directory, with
#   "plugins": [{"name": "scientific-agent-skills", "source": "./scientific-agent-skills", ...}]
claude plugin marketplace add <parent directory>
claude plugin install scientific-agent-skills@<marketplace name>
```

**Cost before installing:** `claude plugin details scientific-agent-skills` reports the always-on
token cost. This plugin adds about **26.5k tokens to every session** because all 164 skill
descriptions load. Disable it (`claude plugin disable`) in sessions that do not need it.

**Skills that earned their place in this project:**
- `scientific-visualization`: network-free CLIs that are useful on their own, independent of any
  model - `palette_audit.py` (WCAG contrast against the background plus pairwise CIE L\* grayscale
  separation), `image_metadata.py` (effective DPI at a stated print width, alpha, ICC),
  `figure_export.py`, and `assets/publication.mplstyle` with Okabe-Ito cycles.
- `scientific-schematics`: **generates diagrams with an image model through OpenRouter**. It needs
  `OPENROUTER_API_KEY`, sends the prompt and the generated image off the machine, returns raster PNG
  only, and its own documentation warns that misspelled labels are the most common failure. Not
  usable for Vietnamese figure labels, and not usable at all without explicit consent to send the
  content to a third party. Check which skills call out to a network service before using them.

### Antigravity CLI Tool Invariants

- **`write_to_file` Artifact Scope Invariant:** In Antigravity CLI, `ArtifactMetadata` is strictly reserved for user-facing artifacts located within the conversation brain directory (`<appDataDir>\brain\<conversation-id>/...`). Supplying `ArtifactMetadata` for regular repository files, source code, or documentation files in the workspace causes an immediate tool failure: `... is not a valid artifact path; artifacts must be in <appDataDir>\brain\<conversation-id>/`. For workspace files, omit `ArtifactMetadata` entirely.

**Source:** https://github.com/microsoft/win-dev-skills



### Agent shell-tool invariants (harness-independent)

- **Large command payloads are mangled in transit, independent of the shell.** Writing a file by piping a large heredoc through an agent's shell/command tool can fail with a shell parse error pointing at a line in the middle of the content (observed: `unexpected EOF while looking for matching '''` reported at line 37 of a roughly 20 KB command). The shell is not the cause. The same heredoc construct, the same content and the same quoting succeed at small size, and `bash` reading a 37 KB generated heredoc from a script file completes with exit 0. The failure is in the tool layer's command transport, which truncates or reshapes very long command strings. Do not debug the quoting and do not retry with different escaping: switch to the harness's dedicated file-write tool for any file content beyond a few kilobytes, and reserve shell heredocs for short files and small appends.
