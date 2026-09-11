# PowerShell and Patch Portability

Verified rules for safe cross-file automation on Windows:

- PowerShell cannot pipe directly from a `foreach (...) { ... }` statement. Assign its emitted values to a variable or wrap the statement in `@(...)`, then pipe the resulting collection.
- Exact-context patches are sensitive to the target file's decoded Unicode text. When a patch context containing punctuation such as an em dash does not match, read the file explicitly as UTF-8 and retry with a smaller patch anchored on stable surrounding text.
- A failed exact-context `apply_patch` verification does not apply the requested patch; verify the affected files before retrying.
- Before using `git -C <external-config-directory>`, verify that `<external-config-directory>/.git` exists. Configuration roots may be plain directories, so use file hashes and existence checks when no repository metadata is present.
- PowerShell here-strings piped to a Linux process over SSH retain Windows CRLF endings; a trailing carriage return can turn a token such as `docker` into `docker\r`. Prefer direct SSH command arguments for short operations, and do not place Linux `$(...)` command substitution inside a PowerShell double-quoted string because PowerShell expands it locally.
- Native version probes under Windows PowerShell 5.1 can emit stderr as `NativeCommandError` when `$ErrorActionPreference = "Stop"`, even when stderr is redirected. For a probe such as `tool --version`, temporarily set the preference to `Continue` inside `try/finally`, restore it immediately, discard benign diagnostics, and still enforce `$LASTEXITCODE` plus exact stdout validation.
- `Start-Process -WindowStyle` is not supported by PowerShell Core on Unix. Add `WindowStyle = "Hidden"` only when `[System.IO.Path]::DirectorySeparatorChar -eq '\'`; keep the parameter on Windows for background helpers.
- Portable containment checks must use `DirectorySeparatorChar` and `AltDirectorySeparatorChar`, case-insensitive comparison only on Windows, and both `FileAttributes.ReparsePoint` and the PowerShell `LinkType` property to recognize Windows reparse points and Unix symbolic links.
- Do not call `.Trim()` on output that may be `$null`; cast to `[string]` or test `IsNullOrWhiteSpace` first. A command that legitimately emits no stdout otherwise becomes an unrelated null-method failure.
- In PowerShell, passing script blocks via CLI arguments in double quotes (e.g. `powershell -Command "..."`) causes the calling shell to expand all variables (`$_`, `$param`, `$idx`) into null/empty tokens before passing to the child process. This mangles script blocks like `param($s)` into `param()` (syntax error) and array slicing like `$lines[($idx-20)..]` into `[(-20)..]` (causing `Missing type name after '['`). Using bash-style backslash escape `\$` fails because PowerShell escape character is the backtick (`` ` ``); `\$_.Property` causes PowerShell to parse `\` as a command/path prefix, throwing `The term '\.Property' is not recognized`. Use single quotes `'...'` for literal script blocks, backticks (`` `$_ ``) if double-quoted expansion is required, or write commands to a temporary `.ps1` script file.
- Redundant nested `powershell -Command`: When the agent shell is already PowerShell, calling `powershell.exe -Command '... "inner quotes" ...'` causes the outer PowerShell to strip internal double quotes before passing arguments to the child process. This causes operators like `-match "foo|bar"` to lose quotes and fail with `ExpectedValueExpression` or pipeline parsing errors (`|`). Execute PowerShell commands directly without wrapping in `powershell -Command`, or use a `.ps1` file.
- WSL Command Invocation Quoting: Invoking Linux tools through `wsl -- bash -c "ssh ... '...'"` from PowerShell causes PowerShell to strip inner double or single quotes before passing arguments to WSL bash, producing syntax errors like `unexpected EOF while looking for matching '''`. Pass commands directly to `wsl -d <distro> -u <user> -- <binary> [args...]` (such as `wsl ... -- ssh ...`) or base64-encode complex multi-line bash scripts.
- `Get-Command` piping to `Select-Object -ExpandProperty` and Null-Conditional Operators (`?.`): When a command does not exist, `Get-Command missing -ErrorAction SilentlyContinue` outputs `$null`. Piping `$null` directly into `Select-Object -ExpandProperty <Prop>` throws a terminating exception because the property does not exist on null/empty objects. Furthermore, do NOT use C#-style null-conditional operators like `(Get-Command <name> -ErrorAction SilentlyContinue)?.Source` or `$obj?.Prop` in scripts targeting Windows PowerShell 5.1 (`powershell.exe`); `?.` is only supported in PowerShell 7+ (`pwsh`) and throws a fatal parse error (`Unexpected token '?.Source' in expression or statement`) on PowerShell 5.1. Always use explicit variable assignment and conditional check: `$c = Get-Command <name> -ErrorAction SilentlyContinue; if ($c) { $c.Source } else { $null }`.
- `Start-Process` parameter binding: When launching background or elevated processes (`-Verb RunAs`), the executable must be explicitly passed to `-FilePath` (e.g. `Start-Process -FilePath powershell.exe ...`). Specifying the binary positionally without `-FilePath` fails with parameter binding error `A positional parameter cannot be found that accepts argument 'powershell.exe'`.
- `Get-Process -Name` missing process handling: When querying multiple process names where some may not be currently running (e.g. `Get-Process -Name cargo, rustc, docker*`), `Get-Process` throws non-terminating errors for missing names and sets exit code 1 even with `-ErrorAction SilentlyContinue`. Prefer pipeline filtering via `Get-Process | Where-Object { $_.ProcessName -match 'pattern' }` to query running processes safely without error records.
- Mock Executable Shims in Cross-Platform PowerShell (`pwsh`) on Linux: When test harnesses generate mock or shim executables to be invoked via `& $shimPath [args]`, generating a Windows batch script (`*.cmd`) fails on Linux runners because Linux does not recognize `.cmd` files as executables. `pwsh` on Linux delegates unknown extensions to desktop handlers (e.g. `/usr/bin/xdg-open`), which fails in headless CI environments with `www-browser: not found` and `The variable '$LASTEXITCODE' cannot be retrieved because it has not been set`. Harnesses must branch on `($null -ne (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows) -or ($env:OS -eq "Windows_NT")` to generate `.cmd` on Windows and a POSIX shell script (`#!/bin/sh`) with `chmod +x` on Linux.
- `Get-ChildItem` recursion depth parameter: In PowerShell (Windows PowerShell 5.1 and PowerShell Core), limiting recursion depth uses the parameter `-Depth <int>`, not `-MaxDepth` (a POSIX `find` convention). Supplying `-MaxDepth` throws a `ParameterBindingException: A parameter cannot be found that matches parameter name 'MaxDepth'`.
- Transient File Locks during Build Pipelines (Antivirus / Search Indexer): On Windows, immediately after compiling or publishing large self-contained executables (e.g. `dotnet publish` single-file bundles), Windows Defender (`MsMpEng`) or SearchIndexer temporarily acquires an exclusive or shared read lock to scan the newly created binary. Immediate high-level file operations (`Copy-Item`) can fail with `System.IO.IOException: The process cannot access the file ... because it is being used by another process`. Build automation scripts must use a bounded retry loop (e.g. 5 attempts with 1000ms delay in `try/catch`) rather than assuming immediate unshared file availability.
- Safe Path and Registry Probing with Get-Item / Get-ItemProperty: When inspecting paths or registry entries that may not exist (e.g. root system files like `C:\hiberfil.sys` or older Windows 10 vs 11 registry keys), calling `Get-Item -Path <path>` or `Get-ItemProperty -Path <path>` directly on a missing target emits an `ItemNotFoundException` error record and sets a non-zero process exit code (exit code 1) even with `-ErrorAction SilentlyContinue`. Always guard property and item queries with `if (Test-Path -Path <path>) { Get-Item -Path <path> }` to inspect existence and attributes safely without causing command or runner exit code failures.
- `Get-ChildItem -Filter` vs `-Include` parameter binding: In PowerShell, `-Filter` accepts only a single `[string]`. Supplying multiple comma-separated filters (e.g. `-Filter "*.exe", "*.dll"`) throws a terminating `ParameterBindingException: Cannot convert 'System.Object[]' to the type 'System.String' required by parameter 'Filter'`. To filter by multiple wildcard patterns, either pass `-Include <string[]>` (which requires the path to end with `\*`) or pipe the unfiltered results to `Where-Object { $_.Name -match '<regex>' }`.
- CLI Subshell Statelessness Across Executions: Each invocation of terminal commands in agent runners executes in an independent child PowerShell process. Local variables and session modifications do not persist across separate tool calls. Multi-step variable-dependent pipelines must be executed within the same command payload or written to a script file.
- WMI Battery Telemetry Limitations (`BatteryStaticData` vs `BatteryStatus`): Polling `root\wmi:BatteryStaticData` via WMI/CIM throws `HRESULT 0x80041001 (Generic failure)` on modern UEFI ACPI platforms (e.g. Lenovo, Dell, HP). To retrieve real-time power metrics, use `root\wmi:BatteryStatus` (which reliably yields `DischargeRate` in mW, `RemainingCapacity` in mWh, and charging state). For design and full-charge capacities, parse `powercfg /batteryreport /output <path>` or query `Win32_Battery`.
- Inline PowerShell Variable Premature Expansion in `-Command "..."`: In command-line tool calls or sub-shells, passing PowerShell code blocks containing variables (`$proc`, `$id`, `$hasExited`) inside double-quoted string parameters (`powershell -Command "$p = ..."`) causes the host shell to expand them to empty strings before child invocation. This mangles expressions like `$id = $p.Id; if (-not $exited)` into `= .Id; if (-not )`, producing parse errors (`Missing expression after unary operator '-not'` or `Missing statement after '='`). Always enclose script blocks in literal single quotes (`powershell -Command '$p = ...'`) or invoke a `.ps1` script file directly.
- Windows Python CLI Stdout Default Encoding (cp1252 vs UTF-8): On Windows, invoking one-line Python commands via CLI (`python -c "print(...)"`) defaults standard output to the legacy Windows console code page (e.g., `cp1252`), which throws `UnicodeEncodeError: 'charmap' codec can't encode character ...` when printing non-ASCII Unicode text (such as accented Vietnamese). To output Unicode safely from Python sub-processes, write directly to binary stdout buffer (`sys.stdout.buffer.write(text.encode('utf-8'))`) or set `$env:PYTHONIOENCODING = "utf-8"`.
- `.NET SDK Template Major Version Scoping with dotnet new`: In newer .NET SDKs (e.g. .NET 10 SDK), built-in project templates like `dotnet new xunit -f <tfm>` restrict the framework parameter (`-f`) strictly to the host SDK's major version (e.g., `net10.0`), rejecting cross-targeting flags like `-f net8.0` with `Error: Invalid option(s): -f net8.0`. When generating projects for earlier target frameworks on multi-targeting hosts, author the `.csproj` directly with `<TargetFramework>net8.0-windows</TargetFramework>` or instantiate the default template and adjust `<TargetFramework>` post-generation.
- .NET Solution Format Invariant in Modern .NET SDK (sln vs slnx): In modern .NET 8 / 9 SDKs, running `dotnet new sln` defaults to the new XML format (`--format slnx`), creating `<name>.slnx` instead of `<name>.sln`. If downstream tools, older Visual Studio versions, or legacy build scripts expect the classic Solution file format, explicitly pass `--format sln` (e.g. `dotnet new sln -n <Name> -f sln`).
- WMI Memory Manager Cmdlet Elevation Boundary (`Get-MMAgent`): Querying Windows memory manager settings via `Get-MMAgent` under non-elevated PowerShell fails with `PermissionDenied: Access is denied (Windows System Error 5)` because the underlying WMI class (`Root\Microsoft\Windows\MemoryManager:PS_MMAgent`) requires Administrator privileges. To inspect or configure memory compression and page combining without error records, run within an elevated process (`Start-Process -FilePath powershell.exe -Verb RunAs ...`) or inspect registry fallbacks directly.
- MSVC Compiler `/Fo` Directory Parameter Trailing Backslash Escaping: When passing an output directory to the MSVC compiler (`cl.exe`) for multiple source files using `/Fo"<dir>\"`, the trailing backslash directly preceding the closing quote (`\"`) is interpreted by the Windows command-line parser (`CommandLineToArgvW`) as an escaped literal quotation mark rather than a path separator. This causes MSVC to absorb all subsequent command-line flags (such as `/link`, `/DLL`, and input libraries) into the `/Fo` path, failing with `Command line error D8036: '/Fo<path>" /link /DLL ...' not allowed with multiple source files`. To specify an output directory safely in build automation scripts, terminate the directory path with a forward slash (`/Fo"<dir>/"`) or an escaped double backslash (`/Fo"<dir>\\"`).
- Windows PowerShell Nested Method Expression Interpolation: In Windows PowerShell 5.1, placing complex method invocations with arguments directly inside double-quoted string subexpressions alongside trailing literal tokens (such as `"$([math]::round($val, 1)) KB"`) can trigger syntax parse errors (`Unexpected token 'KB' in expression or statement`) due to parser ambiguity with unit prefixes (e.g. `KB`/`MB`). Always assign rounded numeric values to an intermediate variable first (e.g. `$rounded = [math]::Round($val, 1); "$rounded KB"`), or explicitly cast or format using the `-f` operator (`"{0:N1} KB" -f $val`).
- Windows PowerShell Statement Separators (`&&` vs `;`): In Windows PowerShell 5.1 (`powershell.exe`), the POSIX-style `&&` and `||` pipeline chain operators are unsupported and throw `The token '&&' is not a valid statement separator in this version` (causing a terminating parse error). Always use semicolons (`;`) or newline separation for sequential command execution in Windows PowerShell scripts and CLI invocations.
- NTFS Directory Junction Workaround for Source Path Mismatches (`mklink /J`): When an external or legacy repository defines project files (`.vcxproj` or similar) referencing source files under a folder structure that differs from physical disk layout (e.g., project references `src/...` while disk folder is named `scr/...`), MSVC fails immediately with `fatal error C1083: Cannot open source file: 'src\...': No such file or directory`. Rather than modifying hundreds of lines in tracked project files or breaking git submodule upstream tracking, create a filesystem-level directory junction via `cmd /c mklink /J "<project>\src" "<project>\scr"`. Junctions are resolved transparently at the NTFS driver level without elevated privileges on local volumes, operate seamlessly with MSBuild/cl.exe, and do not create untracked file clutter in Git.
- Standalone MSBuild Subproject Invocation and `$(SolutionDir)` Scoping: When invoking MSBuild directly on individual project files (e.g. `msbuild project.vcxproj`) without building through the top-level Solution (`.sln`), MSBuild automatically defaults the macro `$(SolutionDir)` to the current project's directory rather than the repository/solution root. Any cross-project dependencies or include paths relying on `$(SolutionDir)` (e.g. `$(SolutionDir)cheat-base/src/` or `$(OutDir)`) fail to resolve. Always replace `$(SolutionDir)` with relative paths anchored at the project (`$(ProjectDir)..\`), or explicitly pass `/p:SolutionDir="<absolute_root_path>\"` on the MSBuild command line.


## Symbolic links on Windows without elevation

Windows PowerShell 5.1's `New-Item -ItemType SymbolicLink` fails with `NewItemSymbolicLinkElevationRequired` / "Administrator privilege required for this operation" **even when Developer Mode is enabled**. It does not pass `SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE` to the underlying `CreateSymbolicLink` call.

`cmd.exe`'s `mklink` does pass the flag and succeeds unelevated on Windows 10 1703+ with Developer Mode on. PowerShell 7+ (`pwsh`) also works; 5.1 does not.

Verified on Windows 11 Pro 26200, Developer Mode on, non-elevated shell:

```powershell
# fails
New-Item -ItemType SymbolicLink -Path $link -Target $target

# succeeds
$a = @('/c', 'mklink')
if (Test-Path -LiteralPath $target -PathType Container) { $a += '/D' }   # /D for directories
$a += @($link, $target)
& cmd.exe @a
if ($LASTEXITCODE -ne 0) { throw "mklink failed: $link" }
```

Check Developer Mode before attempting either:

```powershell
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -ErrorAction SilentlyContinue).AllowDevelopmentWithoutDevLicense -eq 1
```

Related: prefer a symlink over a copy whenever one file must serve two consumers. A copy plus a "keep them in sync" instruction is not a synchronisation mechanism; it is a drift generator.

Do not symlink a file the owning application rewrites. Many applications save by writing a temporary file and renaming it over the target, which replaces the link with a regular file and silently ends the sharing. Merge such files key by key instead.

## Keep `.ps1` files ASCII-only

Windows PowerShell 5.1 reads a `.ps1` with no byte-order mark as **ANSI**, not UTF-8. A single non-ASCII character in a UTF-8-encoded script is therefore decoded as mojibake, and if it sits inside a double-quoted string the file stops parsing.

Verified failure: an em dash in a string literal produced

```
Unexpected token '$(' in expression or statement.
The string is missing the terminator: ".
Missing closing '}' in statement block or type definition.
```

The reported line was correct but the reported *cause* was not — the parser had already lost its place. A cascade of "missing terminator / missing closing brace" errors in a script that looks balanced is the signature of an encoding problem, not a syntax problem.

Two fixes, in order of preference:

1. Keep scripts ASCII-only. Use `-` rather than `—`, straight quotes rather than typographic ones. Put non-ASCII in data files, not in code.
2. If a script genuinely needs non-ASCII, save it as UTF-8 **with** BOM so 5.1 decodes it correctly.

Detect before shipping:

```bash
grep -lP '[^\x00-\x7F]' *.ps1
```

This differs from Markdown and JSON in the same repository, which are read as UTF-8 by the tools that consume them and may contain any character.
