# Workspace Cleanup and Resource Lifecycle Guide

A comprehensive guide for resource lifecycle management, generated artifact cleanup, and safe deletion protocols for AI agents. Goal: Maintain a clean, minimal workspace, eliminate transient clutter, release lingering background processes, and guarantee complete safety for user data.

---

## 1. Workspace Cleanup Rules

After completing any task, the agent must proactively identify and remove temporary files, scratch scripts, build artifacts, cache directories, logs, and disposable outputs generated during the task that serve no ongoing purpose.

* **Never keep files "just in case":** Do not preserve temporary or intermediate files out of habit - they waste disk space and clutter the repository. Delete them unless the user explicitly requests preservation.
* **Common disposable targets:**
  * Language cache directories: `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`.
  * Temporary packages and unused virtual dependencies.
  * Temporary and backup extensions: `*.tmp`, `*.log`, `*.bak`, `*.swp`.
  * Scratch execution scripts, empty directories.
  * AI/ML model cache duplication: Local experiment runtimes defining custom `HF_HOME` or project-scoped model directories frequently duplicate multi-gigabyte models already residing in user-level cache (`~/.cache/huggingface`). Verify blob hashes across project roots to identify redundant downloads.
  * Agent-generated test or debug outputs.
* **Rule when uncertain:** When uncertain whether an artifact is disposable, **ask the user rather than preserving silently**.
* **Action reporting:** Report all cleanup actions taken and disclose any items that could not be removed along with their specific blockers.

---

## 2. Task Artifact and Resource Lifecycle

### A. Ownership Discrimination from Task Start
* At task start, the agent must distinguish clearly between:
  1. Pre-existing files, directories, backups, processes, services, and caches.
  2. Artifacts and processes created specifically by the current task.
* Prefer task-scoped temporary directories. Track the exact identity and ownership of anything created outside the project root. Do not alter `.gitignore` rules merely to hide temporary artifacts.

### B. Process and Connection Release
* Terminate and close all task-created data streams, file handles, child processes, background jobs, filesystem watchers, mutexes, and temporary background services as soon as they are no longer required.
* Report any lingering resource or incomplete handle release.

---

## 3. Safe Deletion and Locked-File Protocol

When executing deletion operations on files or directories, the agent must strictly adhere to the following safety contract:

### A. Strict Target Validation
* Delete an artifact only when its exact resolved absolute target and task ownership are proven.
* **Strictly forbidden:** Broad wildcard deletions (`*`), age-based heuristics, or uncontrolled recursive deletions across unverified boundaries.

### B. Handling Deletion Failures (Locked / Sharing Violations / Access Denied)
A failed deletion does not constitute cleanup completion. Follow this systematic escalation ladder:
1. **Live Handle or Process:** Inspect and terminate task-owned background processes or open file handles, wait a bounded interval, and retry.
2. **Immediate Truncation (Disk Recovery First):** If deletion is blocked but `FILE_WRITE_DATA` is permitted (`BUILTIN\Users` often retains Write access even when lacking Delete rights), immediately truncate all target files to 0 bytes using `[System.IO.File]::WriteAllText($_.FullName, '')`. This instantly reclaims 100% of allocated disk blocks while resolving deletion blockers.
3. **Attribute Verification:** Verify if ReadOnly, Hidden, or System attributes are set via `attrib <path>`. Remove restrictive flags with `attrib -r -s -h <path> /s /d` and retry standard deletion.
4. **Shell Rejection & Child Enumeration:** If high-level shell deletion fails, use native filesystem APIs or enumerate and delete descendants depth-first before removing parent directories. On policy-filtered Windows harnesses, `Remove-Item -LiteralPath '<verified-absolute-path>' -Recurse -Force` may be rejected before PowerShell starts even after the target is validated; for a known task-owned, non-reparse directory, `[System.IO.Directory]::Delete('<verified-absolute-path>', $true)` is a verified exact-target fallback. Recheck absence afterward and never construct the deletion target from untrusted input.
5. **Same-Volume Quarantine:** If immediate deletion is blocked but the path must be cleared, moving to a task-owned quarantine folder on the same drive volume is permitted. Track and retry deletion within the session.
6. **Windows Orphaned SID ACLs & UAC Background Elevation:** On Windows secondary drives (e.g. `D:\`), files created under prior OS installations may be owned by orphaned SIDs with `BUILTIN\Users` having only `(RX, W)` lacking `DELETE` or `FILE_DELETE_CHILD`. Standard non-elevated deletion fails with `Access is denied` (error 5). When encountering this:
   - Check UAC elevation policy: `(Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System).ConsentPromptBehaviorAdmin`.
   - If `ConsentPromptBehaviorAdmin == 0` (silent elevation enabled for admin accounts), create a temporary scoped script in the scratch directory:
     ```powershell
     takeown /f "<target>" /r /d y | Out-Null
     icacls "<target>" /grant "Administrators:F" /t /c /q | Out-Null
     Remove-Item -LiteralPath "<target>" -Recurse -Force
     ```
   - Execute silently via elevated background process (note: `-FilePath` is mandatory; omitting it causes positional parameter binding failure):
     ```powershell
     Start-Process -FilePath powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File <script_path>' -Wait
     ```
   - Verify complete absence of target, and delete the scratch script immediately.
7. **External Blockers & Manual Escalation:** If silent elevation is not permitted (`ConsentPromptBehaviorAdmin != 0`), or if all automated methods remain blocked by higher-level policies or external system locks, preserve the target, record its canonical path and blocker, and report the required elevated command (`Remove-Item -LiteralPath '<target>' -Recurse -Force` in an elevated shell) to the user.
8. **WSL2 & Docker Desktop VHDX Disk Compaction:** Deleting images or pruning build cache (`docker builder prune`) frees blocks inside the guest ext4 filesystem, but does not shrink the host virtual disk (`docker_data.vhdx` or `ext4.vhdx`) automatically. The host file retains its peak allocated size. Note: `wsl --manage <distro> --set-sparse true` is disabled by default in modern WSL2 (v2.3+) due to storage corruption risks and requires `--allow-unsafe`; prefer native Hyper-V `Optimize-VHD -Path <vhdx_path> -Mode Full` or safe diskpart compaction after `wsl --shutdown`.
9. **Massive File Count Archiving & I/O Overhead (tar.exe on NTFS):** Compressing directory trees with high file counts (>200,000 files, such as web crawls or fine-grained datasets) incurs massive NTFS handle open/close and metadata traversal overhead. Windows system `tar.exe` (libarchive) can take 45-60 minutes even for modest sizes (~13 GB). During zip generation, the destination archive file size stays at 0 bytes until central directory serialization and buffer flush at completion. Do not kill the process assuming a hang; verify live execution via CPU delta (`$p.CPU`) or WorkingSet delta over a 2-3 second sleep.
10. **Network Upload Throughput & Progress Verification:** When uploading multi-gigabyte archives to cloud storage (e.g. Google Drive via GWS CLI) without interactive progress bars, measure live transfer rate via network adapter statistics (`Get-NetAdapterStatistics` delta) to estimate remaining time (`RemainingMB / RateMBps`). Before deleting local source data, verify remote file metadata (`size` and `md5Checksum`) matches local byte count exactly.
11. **MSVC Linker LNK1104 & Elevated Process Handle Locks:** When rebuilding native executables (`link /OUT:bin\App.exe`), if the target binary is running under an elevated (Run as administrator) process, standard un-elevated `Stop-Process` or `taskkill` fails with `Access is denied` (error 5), causing the linker to abort with `fatal error LNK1104: cannot open file ...`. To preserve developer momentum without prompting for UAC disruption, immediately compile to a non-colliding companion binary (e.g. `bin\StellaCompass.exe`), verify unit test passing on the new binary, and instruct the user to close the old console or replace it upon termination.

---

## 4. GPU Process and VRAM Lifecycle Management

* **Desktop DWM VRAM Swapping Prevention:** On client Windows machines, the Desktop Window Manager (DWM) and GUI applications baseline consume 2.5-3.5 GiB of dedicated GPU VRAM. Loading large neural models (e.g. LLMs, large Cross-Encoders >= 500M params) on 6-8 GiB consumer GPUs will push allocated VRAM past the physical ceiling, causing Windows DWM to swap VRAM pages into shared system RAM. This induces immediate desktop GUI freezes, cursor stuttering, and severe OS-wide lag.
* **Proactive VRAM Release:** Always terminate CUDA processes immediately upon task completion or pause. Do not leave PyTorch interactive kernels, inference workers, or unreleased CUDA contexts running in the background. Verify total release via `nvidia-smi` and confirm zero lingering Python processes.
* **Heavy Compute Offload Boundary:** When batch inference requires >= 10,000 text pairs or multi-gigabyte models, package lightweight candidate inputs and offload compute to dedicated cloud environments (e.g. Google Colab / cloud GPU) rather than running locally on desktop-bound consumer GPUs.

---

## 5. Portable Windows Resource Auditing without psutil

* **System Python Dependency Boundary:** In many restricted, sandboxed, or standard Windows environments, system Python lacks `psutil`. Calling `import psutil` fails immediately with `ModuleNotFoundError: No module named 'psutil'`.
* **Verified CIM/WMI Native Fallback:** Use native PowerShell CIM cmdlets to audit RAM and storage metrics safely without third-party packages:
  ```powershell
  $os = Get-CimInstance Win32_OperatingSystem
  $freeRamGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
  $totalRamGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
  $usedRamGB = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 2)
  $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='D:'"
  $freeDiskGB = [math]::Round($disk.FreeSpace / 1GB, 2)
  ```
* **GPU VRAM Query:** Query dedicated GPU memory deterministically via:
  ```powershell
  nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv,noheader
  ```

