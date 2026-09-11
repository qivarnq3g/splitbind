# Windows UAC Elevation, Error 740, and Native Process Interop Patterns

## 1. Problem Description & Root Cause (Error 740)

When invoking native Windows applications via standard Win32 process creation APIs (`CreateProcessW`, `CreateProcessA`), the call may fail with error code `740` (`ERROR_ELEVATION_REQUIRED` / `0x000002E4`).

### Root Causes:
1. **Embedded Application Manifest:** The target binary contains an embedded XML manifest declaring `<requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>` or `highestAvailable`.
2. **Unelevated Parent Inability:** `CreateProcess` cannot elevate a child process across the Windows User Account Control (UAC) security boundary. When called from a medium-integrity (non-elevated) token, the kernel refuses creation.
3. **Cross-Integrity Privilege Block:** Even if an elevated process is started independently, an unelevated caller cannot call `OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_CREATE_THREAD, ...)` on it due to User Interface Privilege Isolation (UIPI) and integrity levels (Medium cannot write to High).

## 2. Engineering Remediation & Best Practices

To handle process launching and runtime interop seamlessly across administrative boundaries:

### Pattern A: Dual-Tier Launching with `ShellExecuteEx` Fallback
When `CreateProcessW` fails specifically with `ERROR_ELEVATION_REQUIRED` (740):
```cpp
DWORD err = GetLastError();
if (err == 740) { // ERROR_ELEVATION_REQUIRED
    SHELLEXECUTEINFOW sei{ sizeof(SHELLEXECUTEINFOW) };
    sei.cbSize = sizeof(SHELLEXECUTEINFOW);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = L"runas"; // Requests elevation prompt
    sei.lpFile = targetExecutablePath;
    sei.lpDirectory = targetWorkingDirectory;
    sei.nShow = SW_SHOWNORMAL;

    if (ShellExecuteExW(&sei)) {
        DWORD targetPid = GetProcessId(sei.hProcess);
        // Target process started elevated with valid process handle
        CloseHandle(sei.hProcess);
    }
}
```

### Pattern B: Embedded MSVC UAC Manifest Linking
Ensure the launcher application itself is recognized by Windows as requiring administrative privileges upon launch:
- MSVC Linker Arguments:
  ```powershell
  /MANIFEST:EMBED /MANIFESTUAC:"level='requireAdministrator' uiAccess='false'"
  ```
- Result: Double-clicking the executable automatically displays the Windows UAC consent dialog and grants High Integrity level, allowing full `OpenProcess` and debugging access.

### Pattern C: Programmatic Integrity Level Check
Verify whether current process token belongs to the Administrators group:
```cpp
bool IsRunningAsAdmin() {
    BOOL isAdmin = FALSE;
    PSID adminGroup = nullptr;
    SID_IDENTIFIER_AUTHORITY ntAuthority = SECURITY_NT_AUTHORITY;
    if (AllocateAndInitializeSid(&ntAuthority, 2, SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &adminGroup)) {
        CheckTokenMembership(nullptr, adminGroup, &isAdmin);
        FreeSid(adminGroup);
    }
    return isAdmin == TRUE;
}

### Pattern D: Suspended Process Creation Pattern (`CREATE_SUSPENDED`)
When attaching or loading dynamic modules into graphics-intensive or game client binaries:
- Waiting 5+ seconds after full launch often encounters race conditions where driver protection handles (`\Device\mhyprot2`) or anti-tamper threads have already locked remote process handles or hooked `LoadLibraryW`.
- **Solution:** Create the target process with the `CREATE_SUSPENDED` flag via `CreateProcessW`:
  ```cpp
  CreateProcessW(..., CREATE_SUSPENDED, ..., &si, &pi);
  // Re-use pi.hProcess directly without requiring a secondary OpenProcess
  LoadModuleIntoProcess(pi.hProcess, dllPath);
  // Resume main execution thread
  ResumeThread(pi.hThread);
  ```
- This ensures the helper runtime module is linked before security threads lock handle creation and avoids mid-stream attachment race conditions.

### Pattern E: Parent Process ID (PPID) Spoofing via `STARTUPINFOEXW`
When game processes implement parent-process heuristics (e.g. self-terminating if spawned directly from non-system consoles):
- **Remedy:** Reparent the child process under `explorer.exe`:
  ```cpp
  DWORD explorerPid = FindProcessId(L"explorer.exe");
  HANDLE hExplorer = OpenProcess(PROCESS_CREATE_PROCESS, FALSE, explorerPid);

  STARTUPINFOEXW siEx{};
  siEx.StartupInfo.cb = sizeof(STARTUPINFOEXW);
  SIZE_T attrSize = 0;
  InitializeProcThreadAttributeList(nullptr, 1, 0, &attrSize);
  std::vector<BYTE> attrBuffer(attrSize);
  siEx.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attrBuffer.data());
  InitializeProcThreadAttributeList(siEx.lpAttributeList, 1, 0, &attrSize);
  UpdateProcThreadAttribute(siEx.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_PARENT_PROCESS, &hExplorer, sizeof(HANDLE), nullptr, nullptr);

  CreateProcessW(nullptr, cmd, nullptr, nullptr, FALSE, EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED, nullptr, dir, &siEx.StartupInfo, &pi);
  DeleteProcThreadAttributeList(siEx.lpAttributeList);
  CloseHandle(hExplorer);
  ```

## 3. Windows Native Console UTF-16 Diacritic Encoding Pattern

When building native Windows C++ CLI tools or launchers that support full diacritics (e.g. Vietnamese, East Asian scripts, Unicode symbols):
- Standard `SetConsoleOutputCP(CP_UTF8)` often fails or causes distorted text/mojibake if the console raster font does not support UTF-8 multi-byte rendering.
- Standard `std::cout` will mangle multi-byte non-ASCII characters.

### Verified Architecture Solution:
1. Include `<io.h>` and `<fcntl.h>`.
2. Configure wide-character mode at process entry:
   ```cpp
   _setmode(_fileno(stdout), _O_U16TEXT);
   _setmode(_fileno(stdin), _O_U16TEXT);
   ```
3. Use wide strings and streams exclusively: `std::wcout`, `std::wcin`, `std::wstring`, and wide literals (`L"..."`).
### Pattern F: Console TrueType Font Configuration via `SetCurrentConsoleFontEx`
On default Windows Command Prompt / Conhost, legacy raster fonts fail to render Vietnamese Unicode diacritics even under `_O_U16TEXT` mode.
- **Solution:** Programmatically enforce a vector TrueType font (e.g. `Consolas` or `Lucida Console`) at startup:
  ```cpp
  HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
  CONSOLE_FONT_INFOEX cfi;
  cfi.cbSize = sizeof(CONSOLE_FONT_INFOEX);
  cfi.nFont = 0;
  cfi.dwFontSize.X = 0;
  cfi.dwFontSize.Y = 18;
  cfi.FontFamily = FF_DONTCARE;
  cfi.FontWeight = FW_NORMAL;
  wcscpy_s(cfi.FaceName, L"Consolas");
  SetCurrentConsoleFontEx(hOut, FALSE, &cfi);
  ```



```
