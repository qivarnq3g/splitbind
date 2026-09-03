[CmdletBinding()]
param(
    [switch]$Stop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$DemoProjectName = "splitbind-demo"
$DemoMinioImage = "minio/minio:RELEASE.2025-09-07T16-13-09Z"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "infra\compose\compose.local.yaml"
$DemoRoot = Join-Path $RepoRoot "artifacts\demo"
$EnvironmentFile = Join-Path $DemoRoot "demo.env"
$StateFile = Join-Path $DemoRoot "process-state.json"
$LogDirectory = Join-Path $DemoRoot "logs"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Node = (Get-Command node -ErrorAction SilentlyContinue).Source
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
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $Lines, $encoding)
}

function Import-DemoEnvironment {
    if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
        return
    }
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
    New-Item -ItemType Directory -Force -Path $DemoRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
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
    $env:PYTHONPATH = Join-Path $RepoRoot "research\python\src"
}

function Assert-Prerequisites {
    $priorErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($PSVersionTable.PSVersion.Major -lt 5) {
            throw "PowerShell 5.1 or newer is required. Start Windows PowerShell 5.1+ and retry."
        }
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
        if ([string]::IsNullOrWhiteSpace($Node)) {
            throw "Node.js is missing. Install the repository-pinned Node 24 release and retry."
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
        & docker compose --project-name $DemoProjectName -f $ComposeFile --profile demo config --quiet *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "The demo Compose profile is invalid. Run docker compose -f infra/compose/compose.local.yaml --profile demo config and inspect the local error."
        }
    }
    finally {
        $ErrorActionPreference = $priorErrorActionPreference
    }
}

function Test-LocalHttp([string]$Uri, [int]$TimeoutSeconds = 2) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
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

function Test-TrackedProcessIdentity($Entry) {
    try {
        $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction Stop
        $expectedPath = [System.IO.Path]::GetFullPath([string]$Entry.expected_executable)
        $actualPath = [System.IO.Path]::GetFullPath($process.Path)
        $expectedStart = [DateTime]::Parse(
            [string]$Entry.start_time_utc,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [System.Globalization.DateTimeStyles]::RoundtripKind
        ).ToUniversalTime()
        return $actualPath -eq $expectedPath -and
            $process.StartTime.ToUniversalTime().Ticks -eq $expectedStart.Ticks
    }
    catch {
        return $false
    }
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
    if ($null -eq $State) {
        return
    }
    foreach ($entry in @($State.processes)) {
        if (-not (Test-TrackedProcessIdentity $entry)) {
            Write-Warning "Did not stop stale or mismatched PID $($entry.pid) ($($entry.name))."
            continue
        }
        $process = Get-Process -Id ([int]$entry.pid) -ErrorAction Stop
        Stop-Process -InputObject $process
        if (-not $process.WaitForExit(5000)) {
            throw "Demo PID $($entry.pid) did not stop within five seconds. Inspect it before retrying."
        }
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
    Stop-DemoProcesses $state
    if (Test-Path -LiteralPath $StateFile -PathType Leaf) {
        Remove-Item -LiteralPath $StateFile -Force
    }
    Stop-DemoCompose
    Write-Output "Stopped only the SplitBind demo processes and Compose project."
    Write-Output "Retained synthetic credentials and SQLite state: $DemoRoot"
}

function Test-HealthyDemoState($State) {
    if ($null -eq $State -or @($State.processes).Count -ne 3) {
        return $false
    }
    foreach ($entry in @($State.processes)) {
        if (-not (Test-TrackedProcessIdentity $entry)) {
            return $false
        }
    }
    return (Test-LocalHttp "http://127.0.0.1:8000/health/live") -and
        (Test-LocalHttp "http://127.0.0.1:5173")
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
    [string]$WorkingDirectory
) {
    $stdout = Join-Path $LogDirectory "$Name.stdout.log"
    $stderr = Join-Path $LogDirectory "$Name.stderr.log"
    return Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
}

function Rollback-Startup([object[]]$Processes, [bool]$ComposeStarted) {
    if (@($Processes).Count -gt 0) {
        $state = [ordered]@{ processes = @($Processes) }
        Stop-DemoProcesses $state
    }
    if ($ComposeStarted) {
        try {
            Stop-DemoCompose
        }
        catch {
            Write-Warning $_.Exception.Message
        }
    }
    if (Test-Path -LiteralPath $StateFile -PathType Leaf) {
        Remove-Item -LiteralPath $StateFile -Force
    }
}

function Write-ReadySummary {
    Write-Output "Browser: http://127.0.0.1:5173"
    Write-Output "Username: demo-admin"
    Write-Output "Synthetic password: $env:SPLITBIND_DEMO_LOGIN_PASSWORD"
    Write-Output "Logs: $LogDirectory"
    Write-Output "Stop: $StopCommand"
}

try {
    Assert-RepositoryRoot
    if ($Stop) {
        Stop-Demo
        exit 0
    }

    Import-DemoEnvironment
    $existingState = Read-ProcessState
    if ($null -ne $existingState -and (Test-HealthyDemoState $existingState)) {
        Set-CommonRuntimeEnvironment
        Write-ReadySummary
        exit 0
    }

    Assert-Prerequisites
    if ($null -ne $existingState) {
        Stop-DemoProcesses $existingState
        Remove-Item -LiteralPath $StateFile -Force
        Stop-DemoCompose
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
except Exception:
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

        $demoFingerprintKey = $env:SPLITBIND_DEMO_FINGERPRINT_KEY_HEX
        $demoLoginPassword = $env:SPLITBIND_DEMO_LOGIN_PASSWORD
        $env:SPLITBIND_DEMO_FINGERPRINT_KEY_HEX = $null
        $env:SPLITBIND_DEMO_LOGIN_PASSWORD = $null
        $apiProcess = Start-DemoProcess -Name "api" -FilePath $Python `
            -ArgumentList @("services/api/manage.py", "runserver", "127.0.0.1:8000", "--noreload", "--settings=config.settings_demo") `
            -WorkingDirectory $RepoRoot
        $startedProcesses += New-TrackedEntry -Name "api" -Process $apiProcess -ExpectedExecutable $Python
        Save-ProcessState $startedProcesses

        $env:SPLITBIND_DEMO_FINGERPRINT_KEY_HEX = $demoFingerprintKey
        $workerProcess = Start-DemoProcess -Name "worker" -FilePath $Python `
            -ArgumentList @("services/api/manage.py", "run_demo_worker", "--settings=config.settings_demo") `
            -WorkingDirectory $RepoRoot
        $startedProcesses += New-TrackedEntry -Name "worker" -Process $workerProcess -ExpectedExecutable $Python
        Save-ProcessState $startedProcesses

        $viteSecrets = @{
            DEMO_MINIO_ROOT_PASSWORD = $env:DEMO_MINIO_ROOT_PASSWORD
            DJANGO_SECRET_KEY = $env:DJANGO_SECRET_KEY
            OBJECT_STORAGE_ACCESS_KEY = $env:OBJECT_STORAGE_ACCESS_KEY
            OBJECT_STORAGE_SECRET_KEY = $env:OBJECT_STORAGE_SECRET_KEY
            SPLITBIND_DEMO_FINGERPRINT_KEY_HEX = $env:SPLITBIND_DEMO_FINGERPRINT_KEY_HEX
        }
        foreach ($name in $viteSecrets.Keys) {
            [System.Environment]::SetEnvironmentVariable($name, $null, "Process")
        }
        $viteProcess = Start-DemoProcess -Name "vite" -FilePath $Node `
            -ArgumentList @($ViteEntry, "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
            -WorkingDirectory $RepoRoot
        $startedProcesses += New-TrackedEntry -Name "vite" -Process $viteProcess -ExpectedExecutable $Node
        Save-ProcessState $startedProcesses
        foreach ($name in $viteSecrets.Keys) {
            [System.Environment]::SetEnvironmentVariable($name, $viteSecrets[$name], "Process")
        }
        $env:SPLITBIND_DEMO_LOGIN_PASSWORD = $demoLoginPassword

        Wait-LocalHttp -Uri "http://127.0.0.1:8000/health/live" -TimeoutSeconds 45 -Component "Django API"
        Wait-LocalHttp -Uri "http://127.0.0.1:5173" -TimeoutSeconds 45 -Component "Vite"
        Write-ReadySummary
    }
    catch {
        Rollback-Startup -Processes $startedProcesses -ComposeStarted $composeStarted
        throw
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
