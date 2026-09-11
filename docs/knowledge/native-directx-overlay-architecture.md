# Native DirectX 11 Hook & ImGui In-Game Overlay Architecture

## Overview & Scope

Technical standard for building native in-game Head-Up Displays (HUD), radar companions, and visual overlays using C++20, DirectX 11 (D3D11), and Dear ImGui. Applicable to Windows games (including Unity IL2CPP x64 applications). Guarantees zero-latency rendering, full-screen exclusive compatibility, sub-0.1% CPU overhead, and non-blocking input handling.

## Graphics Pipeline Hook (IDXGISwapChain::Present)

To render directly on the game's swapchain backbuffer without external transparent window overhead:

1. **Virtual Method Table (VTable) Resolution:**
   - Retrieve `IDXGISwapChain` vtable via a dummy DirectX 11 device creation (`D3D11CreateDeviceAndSwapChain`) or pattern scanning.
   - Target index: `IDXGISwapChain::Present` is method index 8 in `IDXGISwapChain` vtable.
   - `IDXGISwapChain::ResizeBuffers` is method index 13 in `IDXGISwapChain` vtable.

2. **Hook Implementation Pattern (MinHook):**
   - Intercept `Present`:
     - On first execution, query `ID3D11Device` and `ID3D11DeviceContext` via `pSwapChain->GetDevice(__uuidof(ID3D11Device), ...)`.
     - Create Render Target View (`ID3D11RenderTargetView`) from `pSwapChain->GetBuffer(0, ...)`.
     - Initialize ImGui Win32 and DX11 backends: `ImGui_ImplWin32_Init(hWnd)`, `ImGui_ImplDX11_Init(pDevice, pContext)`.
     - On subsequent frames: render ImGui frame, set render target, invoke `ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData())`, then call original `Present`.
   - Intercept `ResizeBuffers`:
     - Release existing `ID3D11RenderTargetView` before calling original `ResizeBuffers`.
     - Recreate render target view on next `Present` call to prevent crash on game window resize or resolution change.

## Window Procedure Hook (Input Handling)

1. **Window Subclassing / WndProc:**
   - Hook `WndProc` via `SetWindowLongPtr(hWnd, GWLP_WNDPROC, (LONG_PTR)HookedWndProc)`.
   - Pass events to ImGui via `ImGui_ImplWin32_WndProcHandler(hWnd, msg, wParam, lParam)`.
   - When menu is open (`bShowMenu == true`): block mouse/keyboard events from reaching the game's message pump (`return 1` or consume input).
   - When menu is closed: pass all inputs to original `WndProc` to ensure game controls are unaffected.

## Spatial Indexing & World-to-Screen Projection

1. **WorldToScreen Projection:**
   - Transform 3D world coordinate vector `Vector3(x, y, z)` into screen space `Vector2(screenX, screenY)` using the game camera's View-Projection Matrix ($4 \times 4$ column-major or row-major).
   - Clip coordinate verification:
     $$\text{Clip}_w = X \cdot VP_{03} + Y \cdot VP_{13} + Z \cdot VP_{23} + VP_{33}$$
     If $\text{Clip}_w < 0.1f$, the object is behind the camera frustum and must be culled.
   - Normalized Device Coordinates (NDC) to Screen Pixels:
     $$\text{NDC}_x = \frac{X \cdot VP_{00} + Y \cdot VP_{10} + Z \cdot VP_{20} + VP_{30}}{\text{Clip}_w}$$
     $$\text{NDC}_y = \frac{X \cdot VP_{01} + Y \cdot VP_{11} + Z \cdot VP_{21} + VP_{31}}{\text{Clip}_w}$$
     $$\text{Screen}_x = (\text{NDC}_x + 1.0f) \times 0.5f \times \text{WindowWidth}$$
     $$\text{Screen}_y = (1.0f - \text{NDC}_y) \times 0.5f \times \text{WindowHeight}$$

2. **Spatial Hash Grid for Point-of-Interest (POI) Query:**
   - Teyvat world features 10,000+ markers (chests, oculi, puzzles). Brute-force Euclidean distance checking every frame causes frame-time spikes.
   - Partition 2D world coordinates $(X, Z)$ into grid cells of size $S = 64.0\text{ meters}$.
   - Store POIs in `std::unordered_multimap<uint64_t, MarkerData>` where grid key is `Hash(floor(X / S), floor(Z / S))`.
   - Querying POIs within radius $R = 100\text{m}$ requires checking only $3 \times 3$ adjacent grid cells ($O(1)$ constant time complexity).

## Safety & Crash Prevention Invariants

- Never invoke DirectX draw calls without verifying that `pDeviceContext` and `pRenderTargetView` are valid and active.
- Mutex lock or double-buffer dynamic POI state updates if background threads fetch state from server API.
- Always cleanly unhook MinHook (`MH_DisableHook`, `MH_Uninitialize`) and restore original `WndProc` during `DLL_PROCESS_DETACH`.

## Stealth Launcher & Process Injection Patterns

1. **Parent Process ID (PPID) Spoofing:**
   - To bypass parent-process inspection and heuristic anti-cheat monitors, the launcher must not be registered as the parent of the game process.
   - Acquire `TOKEN_ALL_ACCESS` on current process token via `OpenProcessToken`.
   - Obtain a handle to `explorer.exe` using `OpenProcess(PROCESS_ALL_ACCESS, FALSE, explorerPid)`.
   - Allocate and initialize a `PROC_THREAD_ATTRIBUTE_LIST`, setting `PROC_THREAD_ATTRIBUTE_PARENT_PROCESS` pointing to the `explorer.exe` handle.
   - Spawn target game process via `CreateProcessAsUserA` or `CreateProcessW` with flag `EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED`.

2. **Suspended DLL Injection & Thread Resumption:**
   - Write DLL path into target memory via `VirtualAllocEx` and `WriteProcessMemory`.
   - Execute injection routine (`LoadLibraryW` or manual mapping) while the target process threads remain in suspended state.
   - Clean up thread attribute lists and remote allocations before invoking `ResumeThread(pi.hThread)`.

## Unity IL2CPP In-Game State Synchronization & Entity Management

1. **Entity & Camera Retrieval:**
   - Locate game module `UserAssembly.dll` dynamically.
   - Resolve `MoleMole_EntityManager` singleton to obtain active entity lists and local avatar instance (`MoleMole_EntityManager_GetLocalAvatarEntity`).
   - Extract player 3D coordinates via `MoleMole_BaseEntity_GetAbsolutePosition`.
   - Retrieve main camera via `Camera_get_main` or `MoleMole_EntityManager_GetMainCameraEntity` and invoke `Camera_WorldToScreenPoint` or project via camera View-Projection matrix to ensure perfect visual alignment with Unity's internal frustum.

2. **Handle-Based Anti-Cheat Neutralization (Mhyprot2):**
   - Utilize native NT APIs (`NtQuerySystemInformation` with `SystemHandleInformation`, `NtDuplicateObject`, `NtQueryObject`) to iterate process handles.
   - Locate the object path matching `\Device\mhyprot2` and invoke `CloseHandle` on the duplicate/target handle, unlinking kernel monitoring without triggering watchdog alarms.
   - Intercept `Unity_RecordUserData` and `CrashReporter` to prevent integrity reporting back to telemetry servers.

3. **Waypoint Redirection Teleportation Pattern:**
   - To teleport arbitrarily without triggering server rejection, initiate a legitimate teleport request via `MoleMole_LoadingManager_RequestSceneTransToPoint` towards the nearest unlocked waypoint (`MoleMole_MapModule`).
   - Intercept `MoleMole_LoadingManager_NeedTransByServer` and `MoleMole_LoadingManager_PerformPlayerTransmit`.
   - Overwrite the landing coordinates in `MoleMole_BaseEntity_SetAbsolutePosition` with the target custom coordinates $(X, Y, Z)$ immediately upon stage transition.

4. **Combat & Damage Immunity Mechanics:**
   - Attack Immunity: Hook `Miscs_CheckTargetAttackable` and return `false` whenever `target` corresponds to `avatarEntity`.
   - Fall Damage Negation: Hook `VCHumanoidMove_NotifyLandVelocity` to clamp downward vertical velocity $V_y$ above threshold (e.g. $-8\text{ m/s}$) and reset `reachMaxDownVelocityTime = 0`.
   - Environmental Damage Immunity: Intercept `MoleMole_ActorAbilityPlugin_HanlderModifierThinkTimerUp` and suppress tick evaluations for hazard modifiers (`BlackMud`, `SERVER_ClimateAbility`, `ElectricWater`, `UNIQUE_DynamicAbility_DeathZone_LoseHp`).

## 5. Modern Packed Unity Loader & Robust In-Game HUD Standards

1. **Modern Packed Unity Loader (Bypass Suspended Deadlocks):**
   - In modern game clients where Unity IL2CPP is packed directly into `GenshinImpact.exe` (~430 MB) rather than standalone `UserAssembly.dll`, invoking `CreateRemoteThread(LoadLibraryW)` on a `CREATE_SUSPENDED` process causes an `ntdll` loader lock deadlock or triggers early integrity termination.
   - **Remedy:** Launch the game process with standard creation flags (0), allow the Unity engine and DirectX 11 pipeline to complete initialization (10s countdown or window polling), then load the module into the active PID. If the game is already running, detect PID and inject directly without respawning.

2. **Virtual Camera Matrix Fallback for 3D Markers:**
   - When game-internal camera matrices are not yet exported or live memory reads are offline, an identity View-Projection matrix projects all coordinates outside the screen boundaries ($X, Y > 10^5\text{ px}$).
   - **Remedy:** Synthesize a Virtual Camera Matrix from player position $(X, Y, Z)$ and azimuth rotation $\text{Yaw}$ using left-handed LookAt (camera offset 3.5m back, 1.8m up) and Perspective FOV 60°. This guarantees 3D in-game POI markers and distance labels render flawlessly on the screen.

3. **HUD Compass Ribbon & Non-Obstructive Layout:**
   - Position the Nearest POI Tracker at upper-right ($Y \ge 80\text{px}$) strictly beneath the game's native Ping and Co-op widget.
   - Implement a Top-Center Compass Ribbon (FOV 90°) showing cardinal orientations ($N, E, S, W$) and angular azimuth dots with distance meters. This allows players to orient directly towards chests and oculi using either the in-game minimap or horizon line.

4. **Bypassing Kernel Driver Callback Restrictions (Error 5 VirtualAllocEx via Native Windows Hooking):**
   - When injecting into an already-running game with active kernel protection drivers, process handle access masks are stripped via kernel `ObRegisterCallbacks`, causing `VirtualAllocEx` and `WriteProcessMemory` to abort with `ERROR_ACCESS_DENIED (5)`.
   - **Remedy:** Utilize Native Windows Subsystem Message Hooking (`SetWindowsHookExW` with `WH_GETMESSAGE`) targeting the game's top-level window (`UnityWndClass`). Export a light hook procedure (`StellaMsgHook`) and trigger `PostMessageW(hWnd, WM_NULL, 0, 0)`. The Windows subsystem automatically maps the DLL into the target process's address space without invoking `VirtualAllocEx` or `CreateRemoteThread`. Combine with `GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN, ...)` in `MainThread` to permanently pin the module, allowing safe unhooking while preserving the overlay runtime.

5. **Dual-Process Safety & DllMain Process Filtering:**
   - When the launcher loads the DLL via `LoadLibraryW` to retrieve the `HOOKPROC` export for `SetWindowsHookExW`, `DllMain(DLL_PROCESS_ATTACH)` fires inside the launcher process itself.
   - If the DLL immediately spawns graphics threads, creates dummy DirectX devices, or attaches MinHook, calling `FreeLibrary` or closing the launcher unmaps the DLL memory while threads are running, triggering an immediate crash (`EXCEPTION_ACCESS_VIOLATION` 0xC0000005) of the launcher.
   - **Remedy:** In `DllMain(DLL_PROCESS_ATTACH)`, strictly inspect the hosting process executable name via `GetModuleFileNameW`. If the process is NOT the target game executable (`GenshinImpact.exe` or `YuanShen.exe`), return `TRUE` immediately without spawning any background threads or initializing graphics hooks. Furthermore, preserve the DLL handle in the launcher as a static variable and NEVER call `FreeLibrary` on it.

6. **Unhook Race Condition & Target Module Pinning:**
   - When `UnhookWindowsHookEx(hHook)` is invoked shortly after `SetWindowsHookExW`, Windows decrements the reference count of the injected DLL in the target game process. If initialization is still underway, Windows unloads the DLL while its initialization thread is active, causing the game to crash.
   - **Remedy:** In the target game process, call `GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, reinterpret_cast<LPCWSTR>(DllMain), &hSelf)` immediately upon entry in `DllMain`. This locks the module in target memory permanently, making it completely immune to subsequent `UnhookWindowsHookEx` calls.

7. **Anti-Watchdog Heartbeat Preservation:**
   - Modern game protection architectures (Genshin 4.x/5.x) maintain an active IOCTL heartbeat between the game engine threads and the kernel driver. Forcefully closing the driver handle (`\Device\mhyprot2`) via `CloseHandle` causes the next heartbeat IOCTL to fail, signaling tampering and causing the game's watchdog thread to instantly terminate the process (`ExitProcess`).
   - **Remedy:** When using Native Windows Message Hooking, DLL mapping is completely transparent and benign to the operating system. Do NOT forcefully close the kernel driver handle; only adjust error modes (`SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX)`) to maintain stability.

8. **MSVC Error C2712 & SEH Separation from Object Unwinding:**
   - MSVC throws `error C2712: Cannot use __try in functions that require object unwinding` when Structured Exception Handling (`__try __except`) is placed in a function containing C++ objects with destructors (`std::vector`, `std::wstring`, `std::filesystem::path`).
   - **Remedy:** Isolate all SEH blocks into dedicated `static void Safe...()` helper functions that do not declare C++ objects with destructors. Use standard C++ `try { ... } catch (...)` for all C++ container and smart pointer operations.

9. **3D Ground Navigation Path Tracing & Pulsating Flow:**
   - Rendering direct line-of-sight tracers to chests can cause visual clutter and disorient players when terrain occludes the destination.
   - **Remedy:** Interpolate $N = 20$ intermediate 3D waypoints along the vector $P(t) = P_{\text{player}} + t \cdot (P_{\text{target}} - P_{\text{player}})$. Project each segment to screen coordinates via `WorldToScreen`. Render a two-pass polyline: an outer glow layer (width 5.0px, alpha 120) and a core bright golden line (width 2.5px, alpha 240). Superimpose animated flowing photon pulses ($t_{\text{pulse}} = (t \cdot 0.8) \pmod 1$) to clearly guide the player along the ground towards the target chest.

10. **Procedural Chest Icon & Beacon Pillar Rendering:**
    - Small circular dots are difficult to distinguish against dynamic 3D game terrain.
    - **Remedy:** Render procedural chest emblem boxes ($24 \times 18\text{px}$) with lid lines and golden center locks, colored according to chest rarity (Golden for Luxurious/Precious, Cyan for Exquisite, White/Silver for Common). Project a vertical beacon light pillar (70px height) upwards from the chest origin with a pulsing halo ($R = 14 + 3 \cdot \sin(4t)$) to ensure immediate spatial recognition from several hundred meters away.

11. **Regional Spatial Coordinate Alignment (Mondstadt Origin Default):**
    - Raw game map databases (e.g. Kongying Tavern / Yuanshen.site exports) use positive coordinates for Mondstadt ($X \approx 1550, Z \approx 1650$) rather than negative or far-distant regional origins (Fontaine $Z > 5000$).
    - **Remedy:** Ensure the default initial player anchor aligns with the primary starting region ($X = 1550, Y = 200, Z = 1650$) where over 270 chests and oculi are within 1000m radius. Provide an `Auto-Snap` function to instantly bind coordinates to the nearest non-empty POI cluster if live memory synchronization is deferred.

12. **Live Input Movement Synchronization & Off-Screen Waypoint Edge Indicators:**
    - When player coordinates remain static, moving in-game causes markers to drift out of spatial sync, and frustum culling hides all objects behind the camera.
    - **Remedy:**
      - Continuously sample input vectors ($W, A, S, D, \text{Shift}$) during non-menu gameplay and integrate displacement ($\Delta X, \Delta Z$) scaled to real in-game character velocities (5.8 m/s walk, 9.2 m/s sprint) relative to camera azimuth $Yaw$.
      - Provide keyboard camera rotation (Left/Right) and a snap hotkey (F10) that automatically aligns the camera azimuth directly towards the nearest POI target.
      - When the target marker is culled behind the camera plane (clip_w < 0.1 or off-screen), project its relative angular offset onto an elliptical boundary at the screen edge (Rx = 0.44 * W, Ry = 0.40 * H) and render an oriented golden triangle pointer with target name and distance, eliminating disorientation.

13. **3D Chest Bounding Box (8 Vertices, 12 Edges) & Direct Player Tracer Line:**
    - Flat 2D billboard icons fail to convey depth, physical dimensions, and world orientation of in-game collectibles, causing users to misjudge whether a chest is in front or occluded behind terrain.
    - **Remedy:** Construct an exact 3D Bounding Box around the chest origin ($X, Y, Z$) using physical game dimensions ($W = 1.4\text{m}, D = 1.0\text{m}, H = 0.85\text{m}$).
      - Calculate 8 World Space vertices: 4 bottom vertices ($Y = \text{base}$) and 4 top vertices ($Y = \text{base} + H$).
      - Project all 8 vertices onto the 2D viewport using `Math::WorldToScreen`.
      - Fill top and bottom quads with translucent rarity-matched tint ($\alpha \approx 20\%$) to generate a 3D volumetric feel.
      - Render 12 bounding edges with dual-pass lines: a 4px black shadow stroke under a 2.5px glowing gold/rarity stroke.
      - Anchor a direct high-visibility tracer line from the bottom-center of the screen (representing the player character's feet) directly to the projected base center of the 3D bounding box $\frac{1}{4} \sum_{i=0}^3 S_i$.

14. **Live Mouse Delta Yaw Tracking & MSVC C2445 Conditional Type Ambiguity:**
    - *Mouse Tracking:* Third-person game cameras pivot via mouse movement rather than keys. Intercepting `WM_MOUSEMOVE` in `HookedWndProc` while `!isMenuOpen` allows computing $\Delta X = X_{\text{current}} - X_{\text{prev}}$. Adding $\Delta X \cdot \text{sensitivity}$ directly updates camera azimuth $Yaw$, guaranteeing that 3D projected bounding boxes and navigation lines smoothly rotate alongside the player's in-game view.
    - *MSVC C2445 Ambiguity:* In C++20, the ternary operator `isTarget ? ImColor(...) : uint32_t` triggers compile-time `error C2445: result type of conditional expression is ambiguous` because both `ImColor` and `uint32_t` possess user-defined conversion operators. Always explicitly cast `ImColor` to `uint32_t` (`static_cast<uint32_t>(ImColor(...))`) when mixed with unsigned integer types.
