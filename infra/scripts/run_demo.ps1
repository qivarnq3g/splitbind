[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$TestLibraryOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DemoProjectName = "splitbind-demo"
$DemoMinioImage = "minio/minio:RELEASE.2025-09-07T16-13-09Z"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "infra\compose\compose.local.yaml"
$DemoRoot = Join-Path $RepoRoot "artifacts\demo"
$MinioDataPath = Join-Path $DemoRoot "minio-data"
$EnvironmentFile = Join-Path $DemoRoot "demo.env"
$StateFile = Join-Path $DemoRoot "process-state.json"
$LogDirectory = Join-Path $DemoRoot "logs"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Node = $null
$ViteEntry = Join-Path $RepoRoot "node_modules\vite\bin\vite.js"
$StopCommand = "powershell -ExecutionPolicy Bypass -File infra/scripts/run_demo.ps1 -Stop"

function Assert-RepositoryRoot {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "services\api\manage.py")) -or
        -not (Test-Path -LiteralPath (Join-Path $RepoRoot "package.json")) -or
        -not (Test-Path -LiteralPath $ComposeFile)) {
        throw "Repository layout is incomplete. Restore the SplitBind checkout before running the demo."
    }
    if ((Get-Location).Path -ne $RepoRoot) {
        throw "Run this command from the repository root: $RepoRoot"
    }
}

function Assert-ContainedNonReparsePath([string]$Path, [string]$Root) {
    $separatorChars = @(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd($separatorChars)
    $candidatePath = [System.IO.Path]::GetFullPath($Path)
    $prefix = $rootPath + [System.IO.Path]::DirectorySeparatorChar
    $pathComparison = if ([System.IO.Path]::DirectorySeparatorChar -eq '\') {
        [System.StringComparison]::OrdinalIgnoreCase
    }
    else {
        [System.StringComparison]::Ordinal
    }
    if ($candidatePath -ne $rootPath -and
        -not $candidatePath.StartsWith($prefix, $pathComparison)) {
        throw "Demo path escapes its trusted root: $candidatePath"
    }
    $rootItem = Get-Item -Force -LiteralPath $rootPath -ErrorAction SilentlyContinue
    if ($null -ne $rootItem -and ($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Demo path root cannot be a reparse point: $rootPath"
    }
    $relative = $candidatePath.Substring($rootPath.Length).TrimStart($separatorChars)
    $current = $rootPath
    foreach ($component in @($relative.Split($separatorChars, [System.StringSplitOptions]::RemoveEmptyEntries))) {
        $current = Join-Path $current $component
        $item = Get-Item -Force -LiteralPath $current -ErrorAction SilentlyContinue
        if ($null -eq $item) {
            break
        }
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Demo path cannot traverse a reparse point: $current"
        }
    }
    return $candidatePath
}

function Assert-DemoRuntimePaths {
    foreach ($path in @(
        (Join-Path $RepoRoot "artifacts"),
        $DemoRoot,
        $MinioDataPath,
        $LogDirectory,
        $EnvironmentFile,
        $StateFile,
        (Join-Path $DemoRoot "db.sqlite3"),
        (Join-Path $LogDirectory "api.stdout.log"),
        (Join-Path $LogDirectory "api.stderr.log"),
        (Join-Path $LogDirectory "worker.stdout.log"),
        (Join-Path $LogDirectory "worker.stderr.log"),
        (Join-Path $LogDirectory "vite.stdout.log"),
        (Join-Path $LogDirectory "vite.stderr.log")
    )) {
        Assert-ContainedNonReparsePath -Path $path -Root $RepoRoot | Out-Null
    }
}

function New-RandomHex([int]$ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return (-join ($bytes | ForEach-Object { $_.ToString("x2") }))
}

function Write-Utf8NoBom([string]$Path, [string[]]$Lines) {
    Assert-ContainedNonReparsePath -Path $Path -Root $RepoRoot | Out-Null
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $temporaryPath = "$Path.$([Guid]::NewGuid().ToString('N')).tmp"
    Assert-ContainedNonReparsePath -Path $temporaryPath -Root $RepoRoot | Out-Null
    try {
        [System.IO.File]::WriteAllLines($temporaryPath, $Lines, $encoding)
        Assert-ContainedNonReparsePath -Path $Path -Root $RepoRoot | Out-Null
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Assert-ContainedNonReparsePath -Path $temporaryPath -Root $RepoRoot | Out-Null
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Import-DemoEnvironment {
    if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
        return
    }
    Assert-ContainedNonReparsePath -Path $EnvironmentFile -Root $RepoRoot | Out-Null
    $allowedEnvironmentKeys = @{
        DEMO_MINIO_IMAGE = $true
        DEMO_MINIO_ROOT_USER = $true
        DEMO_MINIO_ROOT_PASSWORD = $true
        DJANGO_SECRET_KEY = $true
        SPLITBIND_DEMO_FINGERPRINT_KEY_HEX = $true
        SPLITBIND_DEMO_LOGIN_PASSWORD = $true
    }
    $seen = @{}
    foreach ($line in Get-Content -LiteralPath $EnvironmentFile) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }
        $parts = $line.Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2 -or
            -not $allowedEnvironmentKeys.ContainsKey($parts[0]) -or
            $seen.ContainsKey($parts[0]) -or
            [string]::IsNullOrWhiteSpace($parts[1])) {
            throw "The retained demo environment file is malformed: $EnvironmentFile"
        }
        $seen[$parts[0]] = $true
        [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
    if ($seen.Count -ne $allowedEnvironmentKeys.Count -or $env:DEMO_MINIO_IMAGE -ne $DemoMinioImage) {
        throw "The retained demo environment file is incomplete or names the wrong MinIO image: $EnvironmentFile"
    }
}

function Initialize-DemoEnvironment {
    Assert-DemoRuntimePaths
    New-Item -ItemType Directory -Force -Path $DemoRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    New-Item -ItemType Directory -Force -Path $MinioDataPath | Out-Null
    Assert-DemoRuntimePaths
    if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
        $lines = @(
            "DEMO_MINIO_IMAGE=$DemoMinioImage",
            "DEMO_MINIO_ROOT_USER=splitbind_demo",
            "DEMO_MINIO_ROOT_PASSWORD=synthetic-minio-$(New-RandomHex 18)",
            "DJANGO_SECRET_KEY=synthetic-django-$(New-RandomHex 32)",
            "SPLITBIND_DEMO_FINGERPRINT_KEY_HEX=$(New-RandomHex 32)",
            "SPLITBIND_DEMO_LOGIN_PASSWORD=synthetic-login-$(New-RandomHex 12)"
        )
        Write-Utf8NoBom -Path $EnvironmentFile -Lines $lines
    }
    Import-DemoEnvironment
}

function Set-CommonRuntimeEnvironment {
    $env:ENVIRONMENT = "local"
    $env:SPLITBIND_DEMO_MODE = "true"
    $env:SPLITBIND_DEMO_DATABASE_PATH = Join-Path $DemoRoot "db.sqlite3"
    $env:DJANGO_SETTINGS_MODULE = "config.settings_demo"
    $env:OBJECT_STORAGE_ENDPOINT = "http://127.0.0.1:9000"
    $env:OBJECT_STORAGE_BUCKET = "splitbind-demo"
    $env:OBJECT_STORAGE_ACCESS_KEY = $env:DEMO_MINIO_ROOT_USER
    $env:OBJECT_STORAGE_SECRET_KEY = $env:DEMO_MINIO_ROOT_PASSWORD
    $env:DEMO_MINIO_DATA_PATH = $MinioDataPath
    $env:PYTHONPATH = Join-Path $RepoRoot "research\python\src"
}

function Resolve-NodeExecutable {
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Node.js is missing. Install the repository-pinned Node 24 release and retry."
    }
    return $command.Source
}

function Assert-Prerequisites {
    $priorErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($PSVersionTable.PSVersion.Major -lt 5) {
            throw "PowerShell 5.1 or newer is required. Start Windows PowerShell 5.1+ and retry."
        }
        $script:Node = Resolve-NodeExecutable
        if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw "Python virtualenv is missing. Create .venv with Python 3.11, then install: .venv\Scripts\python.exe -m pip install -c services/api/constraints-py311.txt '.\services\api[demo,test]'"
        }
        $pythonVersion = (& $Python --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.11\.') {
            throw "The demo requires the repository .venv to use Python 3.11. Recreate .venv with Python 3.11."
        }
        $priorPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = Join-Path $RepoRoot "research\python\src"
        try {
            & $Python -c "import boto3, cv2, django, numpy, pypdfium2, splitbind_ref" 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "Required Python demo packages are missing. Install locally: .venv\Scripts\python.exe -m pip install -c services/api/constraints-py311.txt '.\services\api[demo,test]'"
            }
        }
        finally {
            $env:PYTHONPATH = $priorPythonPath
        }
        $nodeVersion = (& $Node --version 2>&1 | Out-String).Trim()
        $npmVersion = (& npm --version 2>&1 | Out-String).Trim()
        if ($nodeVersion -notmatch '^v24\.' -or $npmVersion -notmatch '^12\.') {
            throw "The demo requires Node 24 and npm 12. Activate the pinned toolchain and retry."
        }
        if (-not (Test-Path -LiteralPath $ViteEntry -PathType Leaf)) {
            throw "Workspace dependencies are missing. Run npm ci from the repository root using the local package cache, then retry."
        }
        & npm ls --workspace '@splitbind/web' --depth=0 *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Workspace dependencies are incomplete. Run npm ci from the repository root using the local package cache, then retry."
        }
        if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "Docker CLI is missing. Install a local Docker engine with Compose support and retry."
        }
        & $Python (Join-Path $RepoRoot "infra\scripts\check_compose_capabilities.py") *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose lacks required config capabilities. Upgrade the local Compose plugin and retry."
        }
        & docker info --format '{{.ServerVersion}}' *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker daemon is unavailable. Start Docker Desktop (Linux containers) and retry."
        }
        & docker image inspect $DemoMinioImage --format '{{.Id}}' *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "The exact MinIO demo image is absent. Load $DemoMinioImage from an approved local image archive with docker load, then retry."
        }
        $env:DEMO_MINIO_IMAGE = $DemoMinioImage
        $env:DEMO_MINIO_ROOT_USER = "splitbind_preflight"
        $env:DEMO_MINIO_ROOT_PASSWORD = "synthetic-preflight-only-not-a-secret"
        $env:DEMO_MINIO_DATA_PATH = $MinioDataPath
        & docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo config --quiet *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "The demo Compose profile is invalid. Run docker compose -f infra/compose/compose.local.yaml --profile demo config and inspect the local error."
        }
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
}

function Test-ApiReadinessResponse($Response) {
    if ($null -eq $Response -or $Response.StatusCode -ne 200) {
        return $false
    }
    try {
        $payload = $Response.Content | ConvertFrom-Json
        $properties = @($payload.PSObject.Properties)
        return $properties.Count -eq 1 -and
            $properties[0].Name -eq "status" -and
            $payload.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-ViteReadinessResponse($Response) {
    return $null -ne $Response -and
        $Response.StatusCode -eq 200 -and
        $Response.Content -match '<div\s+id=["'']root["'']\s*>\s*</div>' -and
        $Response.Content -match '<script\s+type=["'']module["'']\s+src=["'']/src/main\.tsx["'']'
}

function Test-MinIOReadinessResponse($Response) {
    return $null -ne $Response -and
        $Response.StatusCode -eq 200 -and
        [string]::IsNullOrWhiteSpace([string]$Response.Content)
}

function Get-LocalHttpResponse([string]$Uri, [int]$TimeoutSeconds = 2) {
    try {
        return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
    }
    catch {
        return $null
    }
}

function Test-ApiReadiness {
    return Test-ApiReadinessResponse (Get-LocalHttpResponse "http://127.0.0.1:8000/health/live")
}

function Test-ViteReadiness {
    return Test-ViteReadinessResponse (Get-LocalHttpResponse "http://127.0.0.1:5173")
}

function Test-MinIOReadiness {
    return Test-MinIOReadinessResponse (Get-LocalHttpResponse "http://127.0.0.1:9000/minio/health/live")
}

function Test-LocalHttp([string]$Uri, [int]$TimeoutSeconds = 2) {
    $response = Get-LocalHttpResponse -Uri $Uri -TimeoutSeconds $TimeoutSeconds
    switch ($Uri) {
        "http://127.0.0.1:8000/health/live" { return Test-ApiReadinessResponse $response }
        "http://127.0.0.1:5173" { return Test-ViteReadinessResponse $response }
        "http://127.0.0.1:9000/minio/health/live" { return Test-MinIOReadinessResponse $response }
        default { return $false }
    }
}

function Wait-LocalHttp([string]$Uri, [int]$TimeoutSeconds, [string]$Component) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-LocalHttp -Uri $Uri -TimeoutSeconds 2) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Component did not become ready within $TimeoutSeconds seconds. Inspect $LogDirectory."
}

function Test-DemoComposeRunning {
    $priorErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = (& docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo ps --status running --format json minio-demo 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($output)) {
            return $false
        }
        $items = @($output | ConvertFrom-Json)
        return $items.Count -eq 1 -and
            $items[0].Service -eq "minio-demo" -and
            $items[0].State -eq "running" -and
            ([string]$items[0].Name).StartsWith("$DemoProjectName-")
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
}

function Test-TrackedProcessIdentity($Entry) {
    return (Get-TrackedProcessStatus $Entry).Status -eq "matched"
}

function Get-TrackedProcessStatus($Entry) {
    try {
        $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction Stop
        $expectedPath = [System.IO.Path]::GetFullPath([string]$Entry.expected_executable)
        $actualPath = [System.IO.Path]::GetFullPath($process.Path)
        $expectedStart = [DateTime]::Parse(
            [string]$Entry.start_time_utc,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).ToUniversalTime()
        if ($actualPath -eq $expectedPath -and
            $process.StartTime.ToUniversalTime().Ticks -eq $expectedStart.Ticks) {
            return [pscustomobject]@{ Status = "matched"; Process = $process }
        }
        return [pscustomobject]@{ Status = "mismatch"; Process = $process }
    }
    catch {
        return [pscustomobject]@{ Status = "missing"; Process = $null }
    }
}

function Request-TrackedProcessStop($Process) {
    Stop-Process -InputObject $Process
}

function Wait-TrackedProcessExit($Process, [int]$TimeoutMilliseconds) {
    return $Process.WaitForExit($TimeoutMilliseconds)
}

function Save-ProcessState([object[]]$Processes) {
    $payload = [ordered]@{
        schema_version = 1
        compose_project = $DemoProjectName
        processes = @($Processes)
    } | ConvertTo-Json -Depth 5
    Write-Utf8NoBom -Path $StateFile -Lines @($payload)
}

function Read-ProcessState {
    if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) {
        return $null
    }
    try {
        $state = Get-Content -Raw -LiteralPath $StateFile | ConvertFrom-Json
        if ($state.schema_version -ne 1 -or $state.compose_project -ne $DemoProjectName) {
            throw "identity mismatch"
        }
        return $state
    }
    catch {
        throw "The demo process-state record is invalid. Preserve $StateFile for inspection and repair it before retrying."
    }
}

function Stop-DemoProcesses($State) {
    $remaining = @()
    $errors = @()
    if ($null -eq $State) {
        return [pscustomobject]@{ Remaining = @(); Errors = @() }
    }
    foreach ($entry in @($State.processes)) {
        $status = Get-TrackedProcessStatus $entry
        if ($status.Status -eq "missing") {
            continue
        }
        if ($status.Status -ne "matched") {
            $remaining += $entry
            $errors += "PID $($entry.pid) ($($entry.name)) no longer matches its recorded identity and was not stopped"
            continue
        }
        try {
            Request-TrackedProcessStop $status.Process
            if (-not (Wait-TrackedProcessExit $status.Process 5000)) {
                $remaining += $entry
                $errors += "PID $($entry.pid) ($($entry.name)) did not stop within five seconds"
            }
        }
        catch {
            $remaining += $entry
            $errors += "PID $($entry.pid) ($($entry.name)) could not be stopped safely"
        }
    }
    return [pscustomobject]@{ Remaining = @($remaining); Errors = @($errors) }
}

function Save-RemainingProcessState([object[]]$Entries) {
    if (@($Entries).Count -gt 0) {
        Save-ProcessState $Entries
        return
    }
    if (Test-Path -LiteralPath $StateFile -PathType Leaf) {
        Assert-ContainedNonReparsePath -Path $StateFile -Root $RepoRoot | Out-Null
        Remove-Item -LiteralPath $StateFile -Force
    }
}

function Stop-DemoCompose {
    if ([string]::IsNullOrWhiteSpace($env:DEMO_MINIO_IMAGE)) {
        $env:DEMO_MINIO_IMAGE = $DemoMinioImage
    }
    if ([string]::IsNullOrWhiteSpace($env:DEMO_MINIO_ROOT_USER)) {
        $env:DEMO_MINIO_ROOT_USER = "splitbind_demo"
    }
    if ([string]::IsNullOrWhiteSpace($env:DEMO_MINIO_ROOT_PASSWORD)) {
        $env:DEMO_MINIO_ROOT_PASSWORD = "synthetic-stop-placeholder"
    }
    if ([string]::IsNullOrWhiteSpace($env:DEMO_MINIO_DATA_PATH)) {
        $env:DEMO_MINIO_DATA_PATH = $MinioDataPath
    }
    & docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo down --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop the dedicated Compose project. Start Docker, then rerun: $StopCommand"
    }
}

function Test-DemoComposeExists {
    $identifiers = (& docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo ps -aq minio-demo 2>$null | Out-String).Trim()
    return $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($identifiers)
}

function Stop-Demo {
    Import-DemoEnvironment
    $state = Read-ProcessState
    $processResult = [pscustomobject]@{ Remaining = @(); Errors = @() }
    $errors = @()
    try {
        $processResult = Stop-DemoProcesses $state
        $errors += @($processResult.Errors)
    }
    finally {
        try {
            Save-RemainingProcessState @($processResult.Remaining)
        }
        catch {
            $errors += $_.Exception.Message
        }
        finally {
            try {
                Stop-DemoCompose
            }
            catch {
                $errors += $_.Exception.Message
            }
        }
    }
    if ($errors.Count -gt 0) {
        throw ($errors -join "; ")
    }
    Write-Output "Stopped only the SplitBind demo processes and Compose project."
    Write-Output "Retained synthetic credentials and SQLite state: $DemoRoot"
}

function Test-HealthyDemoState($State) {
    if ($null -eq $State -or @($State.processes).Count -ne 3) {
        return $false
    }
    $names = @($State.processes | ForEach-Object { $_.name } | Sort-Object)
    if (($names -join ",") -ne "api,vite,worker") {
        return $false
    }
    foreach ($entry in @($State.processes)) {
        if ((Get-TrackedProcessStatus $entry).Status -ne "matched") {
            return $false
        }
    }
    return (Test-DemoComposeRunning) -and
        (Test-MinIOReadiness) -and
        (Test-ApiReadiness) -and
        (Test-ViteReadiness)
}

function New-TrackedEntry([string]$Name, $Process, [string]$ExpectedExecutable) {
    return [ordered]@{
        name = $Name
        pid = $Process.Id
        expected_executable = (Resolve-Path -LiteralPath $ExpectedExecutable).Path
        start_time_utc = $Process.StartTime.ToUniversalTime().ToString("o")
    }
}

function Start-DemoProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [hashtable]$Environment
) {
    Assert-ContainedNonReparsePath -Path $LogDirectory -Root $RepoRoot | Out-Null
    $stdout = Join-Path $LogDirectory "$Name.stdout.log"
    $stderr = Join-Path $LogDirectory "$Name.stderr.log"
    Assert-ContainedNonReparsePath -Path $stdout -Root $RepoRoot | Out-Null
    Assert-ContainedNonReparsePath -Path $stderr -Root $RepoRoot | Out-Null

    $snapshot = @{}
    foreach ($entry in [System.Environment]::GetEnvironmentVariables().GetEnumerator()) {
        $snapshot[[string]$entry.Key] = [string]$entry.Value
    }
    $systemNames = @(
        "COMSPEC", "NUMBER_OF_PROCESSORS", "OS", "PATH", "PATHEXT",
        "PROCESSOR_ARCHITECTURE", "SystemDrive", "SystemRoot", "TEMP", "TMP", "WINDIR"
    )
    $childEnvironment = @{}
    foreach ($name in $systemNames) {
        $value = [System.Environment]::GetEnvironmentVariable($name, "Process")
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $childEnvironment[$name] = $value
        }
    }
    foreach ($entry in $Environment.GetEnumerator()) {
        $childEnvironment[[string]$entry.Key] = [string]$entry.Value
    }
    try {
        foreach ($name in @($snapshot.Keys)) {
            [System.Environment]::SetEnvironmentVariable($name, $null, "Process")
        }
        foreach ($entry in $childEnvironment.GetEnumerator()) {
            [System.Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
        return Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    }
    finally {
        foreach ($name in @([System.Environment]::GetEnvironmentVariables().Keys)) {
            [System.Environment]::SetEnvironmentVariable([string]$name, $null, "Process")
        }
        foreach ($entry in $snapshot.GetEnumerator()) {
            [System.Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
    }
}

function Get-ApiChildEnvironment {
    return @{
        ENVIRONMENT = "local"
        SPLITBIND_DEMO_MODE = "true"
        SPLITBIND_DEMO_DATABASE_PATH = $env:SPLITBIND_DEMO_DATABASE_PATH
        DJANGO_SETTINGS_MODULE = "config.settings_demo"
        DJANGO_SECRET_KEY = $env:DJANGO_SECRET_KEY
        OBJECT_STORAGE_ENDPOINT = $env:OBJECT_STORAGE_ENDPOINT
        OBJECT_STORAGE_BUCKET = $env:OBJECT_STORAGE_BUCKET
        OBJECT_STORAGE_ACCESS_KEY = $env:OBJECT_STORAGE_ACCESS_KEY
        OBJECT_STORAGE_SECRET_KEY = $env:OBJECT_STORAGE_SECRET_KEY
        PYTHONPATH = $env:PYTHONPATH
        PYTHONIOENCODING = "utf-8"
    }
}

function Get-WorkerChildEnvironment {
    $environment = Get-ApiChildEnvironment
    $environment["SPLITBIND_DEMO_FINGERPRINT_KEY_HEX"] = $env:SPLITBIND_DEMO_FINGERPRINT_KEY_HEX
    return $environment
}

function Get-ViteChildEnvironment {
    return @{
        NODE_ENV = "development"
    }
}

function Rollback-Startup([object[]]$Processes, [bool]$ComposeStarted) {
    $state = [ordered]@{ processes = @($Processes) }
    $processResult = [pscustomobject]@{ Remaining = @(); Errors = @() }
    $errors = @()
    try {
        $processResult = Stop-DemoProcesses $state
        $errors += @($processResult.Errors)
    }
    finally {
        try {
            Save-RemainingProcessState @($processResult.Remaining)
        }
        catch {
            $errors += $_.Exception.Message
        }
        finally {
            if ($ComposeStarted) {
                try {
                    Stop-DemoCompose
                }
                catch {
                    $errors += $_.Exception.Message
                }
            }
        }
    }
    if ($errors.Count -gt 0) {
        throw ($errors -join "; ")
    }
}

function Write-ReadySummary {
    Write-Output "Browser: http://127.0.0.1:5173"
    Write-Output "Username: demo-admin"
    Write-Output "Synthetic password: $env:SPLITBIND_DEMO_LOGIN_PASSWORD"
    Write-Output "Logs: $LogDirectory"
    Write-Output "Stop: $StopCommand"
}

if ($TestLibraryOnly) {
    if ($env:SPLITBIND_DEMO_TEST_LIBRARY -ne "true") {
        throw "TestLibraryOnly is restricted to the repository test harness."
    }
    return
}

try {
    Assert-RepositoryRoot
    Assert-DemoRuntimePaths
    if ($Stop) {
        Stop-Demo
        exit 0
    }

    Import-DemoEnvironment
    if (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf) {
        Set-CommonRuntimeEnvironment
    }
    $existingState = Read-ProcessState
    if ($null -ne $existingState -and (Test-HealthyDemoState $existingState)) {
        Write-ReadySummary
        exit 0
    }

    Assert-Prerequisites
    if ($null -ne $existingState) {
        $staleResult = [pscustomobject]@{ Remaining = @(); Errors = @() }
        $staleErrors = @()
        try {
            $staleResult = Stop-DemoProcesses $existingState
            $staleErrors += @($staleResult.Errors)
        }
        finally {
            try {
                Save-RemainingProcessState @($staleResult.Remaining)
            }
            catch {
                $staleErrors += $_.Exception.Message
            }
            finally {
                try {
                    Stop-DemoCompose
                }
                catch {
                    $staleErrors += $_.Exception.Message
                }
            }
        }
        if ($staleErrors.Count -gt 0) {
            throw ($staleErrors -join "; ")
        }
    }
    elseif (Test-DemoComposeExists) {
        Stop-DemoCompose
    }

    Initialize-DemoEnvironment
    Set-CommonRuntimeEnvironment
    $startedProcesses = @()
    $composeStarted = $false
    try {
        $composeStarted = $true
        & docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo up -d --pull never minio-demo
        if ($LASTEXITCODE -ne 0) {
            throw "MinIO failed to start from the locally loaded image. Inspect docker compose --project-name $DemoProjectName logs minio-demo."
        }
        Wait-LocalHttp -Uri "http://127.0.0.1:9000/minio/health/live" -TimeoutSeconds 45 -Component "MinIO"

        $corsScript = @'
import os
import boto3
client = boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:9000",
    aws_access_key_id=os.environ["DEMO_MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["DEMO_MINIO_ROOT_PASSWORD"],
    region_name="auto",
)
bucket = os.environ["OBJECT_STORAGE_BUCKET"]
try:
    client.head_bucket(Bucket=bucket)
except Exception as error:
    code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
    if code not in {"404", "NoSuchBucket", "NotFound"}:
        raise
    client.create_bucket(Bucket=bucket)
client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [{
    "AllowedOrigins": ["http://127.0.0.1:5173", "http://localhost:5173"],
    "AllowedMethods": ["GET", "HEAD", "PUT"],
    "AllowedHeaders": ["content-length", "content-type", "x-amz-meta-sha256"],
    "ExposeHeaders": ["etag", "x-amz-meta-sha256"],
    "MaxAgeSeconds": 300,
}]})
'@
        & $Python -c $corsScript
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the local demo bucket or apply its narrow CORS policy. Inspect MinIO logs."
        }

        & $Python "services/api/manage.py" migrate --noinput --settings=config.settings_demo
        if ($LASTEXITCODE -ne 0) {
            throw "Demo database migrations failed. Inspect the command output."
        }
        & $Python "services/api/manage.py" seed_demo --settings=config.settings_demo
        if ($LASTEXITCODE -ne 0) {
            throw "Synthetic demo seeding failed. Inspect the command output."
        }

        $apiProcess = Start-DemoProcess -Name "api" -FilePath $Python `
            -ArgumentList @("services/api/manage.py", "runserver", "127.0.0.1:8000", "--noreload", "--settings=config.settings_demo") `
            -WorkingDirectory $RepoRoot -Environment (Get-ApiChildEnvironment)
        $startedProcesses += New-TrackedEntry -Name "api" -Process $apiProcess -ExpectedExecutable $Python
        Save-ProcessState $startedProcesses

        $workerProcess = Start-DemoProcess -Name "worker" -FilePath $Python `
            -ArgumentList @("services/api/manage.py", "run_demo_worker", "--settings=config.settings_demo") `
            -WorkingDirectory $RepoRoot -Environment (Get-WorkerChildEnvironment)
        $startedProcesses += New-TrackedEntry -Name "worker" -Process $workerProcess -ExpectedExecutable $Python
        Save-ProcessState $startedProcesses

        $viteProcess = Start-DemoProcess -Name "vite" -FilePath $Node `
            -ArgumentList @("`"$ViteEntry`"", "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
            -WorkingDirectory $RepoRoot -Environment (Get-ViteChildEnvironment)
        $startedProcesses += New-TrackedEntry -Name "vite" -Process $viteProcess -ExpectedExecutable $Node
        Save-ProcessState $startedProcesses
        Wait-LocalHttp -Uri "http://127.0.0.1:8000/health/live" -TimeoutSeconds 45 -Component "Django API"
        Wait-LocalHttp -Uri "http://127.0.0.1:5173" -TimeoutSeconds 45 -Component "Vite"
        $finalState = [pscustomobject]@{ processes = @($startedProcesses) }
        if (-not (Test-HealthyDemoState $finalState)) {
            throw "Final demo identity/readiness validation failed. Inspect $LogDirectory."
        }
        Write-ReadySummary
    }
    catch {
        $startupError = $_.Exception.Message
        try {
            Rollback-Startup -Processes $startedProcesses -ComposeStarted $composeStarted
        }
        catch {
            throw "$startupError Rollback also reported: $($_.Exception.Message)"
        }
        throw
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
