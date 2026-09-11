# Windows Hybrid GPU and Display Routing

Comprehensive reference for diagnosing and tuning dual-GPU (iGPU + dGPU) Windows laptops (Lenovo LOQ/Legion, ASUS ROG/TUF, Dell Alienware, Acer Nitro) running NVIDIA Optimus / MSHybrid.

## Architecture & Differences: dGPU-Only vs Hybrid (Optimus)

| Architecture | Display Connection (eDP) | Desktop Compositor (DWM) | Frame Latency & Smoothness | Battery Life |
|---|---|---|---|---|
| **dGPU-Only (Discrete Only / MUX)** | Directly wired to NVIDIA dGPU | Rendered directly on NVIDIA VRAM | Zero PCIe copy delay, no micro-stutter, lowest input lag | Short (~1.5-2.5 hrs) |
| **Hybrid Mode (MSHybrid / Optimus)** | Directly wired to Intel/AMD iGPU | Rendered on iGPU using shared system RAM | +1-3 frames cross-adapter copy latency; D3Cold wake freezes | Long (~3.5-5 hrs) |

## Root Causes of Lag & Micro-Stutter in Hybrid Mode

1. **iGPU Execution Unit (EU) Saturation**:
   - Processors like Intel Core i5-12450HX feature basic **Intel UHD Graphics with only 16 EUs** (contrasted with 80-96 EUs on Iris Xe or Radeon 780M).
   - Driving a 1080p @ 144Hz display, Windows 11 Acrylic/Mica translucency, and heavy 3D/video wallpapers (e.g. Wallpaper Engine at Ultra/MSAA) overwhelms the 16 EUs and saturates shared system RAM bandwidth, causing dropped desktop frames and mouse lag.
2. **PCIe D3Cold Power State Wake-Up Hitching**:
   - In Hybrid mode, the dGPU powers down into PCIe `D3Cold` (0W) or low-power `P8` state to conserve energy.
   - When background utilities or Electron/Chromium apps (Discord, web browsers, ShellHost) poll or invoke the dGPU, the system freezes for 500-1500 ms while the dGPU spins up its clocks and VRAM.
3. **Cross-Adapter Copy Engine Overhead**:
   - Applications running on dGPU must copy completed frames across the PCIe bus to the iGPU framebuffer for scanning out to the panel. Under high memory bus contention, this produces rhythmic micro-stuttering.
4. **Wallpaper Engine on Hybrid Laptops**:
   - Running Wallpaper Engine on the dGPU creates severe cross-adapter composition conflicts with DWM.
   - Running Wallpaper Engine on the iGPU requires lowering presets (MSAA Off, Shadows/Post-processing Medium, FPS capped at 30/60) and setting "Other application focused / maximized" to `Pause` to prevent starving DWM.

## Per-App GPU Routing via Windows Registry

Windows 10 (1803+) and Windows 11 manage per-application GPU routing through DirectX Graphics Kernel (DXGKRNL):
- Registry Path: `HKCU:\Software\Microsoft\DirectX\UserGpuPreferences`
- Value Name: Absolute path to the executable (e.g. `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`)
- Value Type: `REG_SZ` (String)
- Value Data:
  - `GpuPreference=1;` - **Power Saving** (Routes to iGPU / Card On)
  - `GpuPreference=2;` - **High Performance** (Routes to dGPU / Card Rời)

### Optimal Assignment Strategy

- **Assign to Power Saving (`GpuPreference=1;` / Card On)**:
  - Web browsers: Chrome, Edge, Firefox, Brave (hardware decode uses Intel QuickSync; avoids dGPU wake).
  - Communication & Office: Discord, Zalo, Teams, Slack, VS Code, Word, Excel.
  - Background Utilities: PowerToys.
  - Wallpaper Engine (Lightweight mode): Only suitable if running simple 2D/30fps wallpapers or on capable iGPUs (e.g. Iris Xe 80-96 EUs or Radeon 680M/780M).
- **Assign to High Performance (`GpuPreference=2;` / Card Rời)**:
  - 3D Games: Valorant (`VALORANT-Win64-Shipping.exe`), Genshin Impact (`GenshinImpact.exe`), Steam titles.
  - Creative & Production: Adobe Photoshop, Premiere Pro, After Effects, Media Encoder.
  - Media Transcoding & Streaming: OBS Studio (`obs64.exe`), HandBrake.
  - Wallpaper Engine (Constrained iGPU fallback): On chips with weak iGPUs (e.g. Intel UHD 16 EUs on i5-12450HX) running 2K/4K scenes with post-processing, assign Wallpaper Engine (`wallpaper64.exe`, `wallpaperui.exe`, `webwallpaper64.exe`) to dGPU (`GpuPreference=2;`) to prevent iGPU EU choking, at the trade-off of maintaining active dGPU power draw (~5-9W).

## Task Manager GPU Telemetry & Thermal Sensor Semantics

- **`Temperature: N/A` on iGPU is Expected Behavior**: In Windows 10/11 Task Manager (WDDM 2.4+), Intel integrated GPUs (Intel UHD / Iris Xe) invariably display `Temperature: N/A`. This represents "Not Applicable / Not Available", not a hardware failure. The iGPU resides on the shared CPU silicon die and shares package power/thermal diodes; Intel graphics drivers do not expose an independent GPU temperature diode to Windows Task Manager.
- **dGPU Temperature Reporting**: Dedicated GPUs (such as NVIDIA GeForce RTX 3050) possess dedicated on-die thermal diodes exposed via NVAPI to WDDM, displaying exact temperatures (e.g. `43 °C`). A reading of 40-50°C at idle or light load is optimal.
- **ACPI WMI Thermal Polling Limitations**: Polling `root\wmi:MSAcpi_ThermalZoneTemperature` via non-elevated PowerShell fails with non-zero exit code on modern OEM laptops (Lenovo, ASUS, Dell) because raw ACPI thermal zones require Administrator elevation and vendor-specific WMI namespaces.

## Hardware MUX Switch Recommendation

If the laptop is primarily used plugged into AC power at a desk:
- Switch Lenovo Vantage / Lenovo Legion Toolkit to **dGPU Mode** (Discrete GPU only).
- Bypassing the iGPU eliminates all cross-adapter overhead, D3Cold wake latency, and iGPU EU bottlenecks.
