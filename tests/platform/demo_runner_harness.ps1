[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Runner,
    [Parameter(Mandatory = $true)][string]$Scenario,
    [Parameter(Mandatory = $true)][string]$ScratchRoot,
    [string]$DumpEnvironmentScript = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:SPLITBIND_DEMO_TEST_LIBRARY = "true"
. $Runner -TestLibraryOnly

function Write-Result($Value) {
    Write-Output ($Value | ConvertTo-Json -Compress -Depth 8)
}

switch ($Scenario) {
    "readiness" {
        $apiGood = [pscustomobject]@{ StatusCode = 200; Content = '{"status":"ok"}' }
        $apiWrongBody = [pscustomobject]@{ StatusCode = 200; Content = '{"status":"other"}' }
        $apiWrongStatus = [pscustomobject]@{ StatusCode = 204; Content = '{"status":"ok"}' }
        $viteGood = [pscustomobject]@{
            StatusCode = 200
            Content = '<html><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>'
        }
        $viteWrong = [pscustomobject]@{ StatusCode = 200; Content = '<html>unrelated service</html>' }
        $minioGood = [pscustomobject]@{ StatusCode = 200; Content = '' }
        $minioWrong = [pscustomobject]@{ StatusCode = 200; Content = 'unrelated service' }
        Write-Result ([ordered]@{
            api_good = Test-ApiReadinessResponse $apiGood
            api_wrong_body = Test-ApiReadinessResponse $apiWrongBody
            api_wrong_status = Test-ApiReadinessResponse $apiWrongStatus
            vite_good = Test-ViteReadinessResponse $viteGood
            vite_wrong = Test-ViteReadinessResponse $viteWrong
            minio_good = Test-MinIOReadinessResponse $minioGood
            minio_wrong = Test-MinIOReadinessResponse $minioWrong
        })
    }
    "healthy-state" {
        $script:processMode = "all"
        $script:composeRunning = $true
        function Get-TrackedProcessStatus($Entry) {
            if ($script:processMode -eq "worker-dead" -and $Entry.name -eq "worker") {
                return [pscustomobject]@{ Status = "missing"; Process = $null }
            }
            return [pscustomobject]@{ Status = "matched"; Process = [pscustomobject]@{ Id = $Entry.pid } }
        }
        function Test-DemoComposeRunning { return $script:composeRunning }
        function Test-ApiReadiness { return $true }
        function Test-ViteReadiness { return $true }
        function Test-MinIOReadiness { return $true }
        $state = [pscustomobject]@{
            processes = @(
                [pscustomobject]@{ name = "api"; pid = 11 },
                [pscustomobject]@{ name = "worker"; pid = 12 },
                [pscustomobject]@{ name = "vite"; pid = 13 }
            )
        }
        $healthy = Test-HealthyDemoState $state
        $script:processMode = "worker-dead"
        $workerDead = Test-HealthyDemoState $state
        $script:processMode = "all"
        $script:composeRunning = $false
        $minioMissing = Test-HealthyDemoState $state
        Write-Result ([ordered]@{
            healthy = $healthy
            worker_dead = $workerDead
            minio_missing = $minioMissing
        })
    }
    "cleanup" {
        $script:stopRequests = @()
        $script:composeStops = 0
        $script:retainedEntries = @()
        function Get-TrackedProcessStatus($Entry) {
            if ($Entry.pid -eq 3) {
                return [pscustomobject]@{ Status = "mismatch"; Process = [pscustomobject]@{ Id = 3 } }
            }
            return [pscustomobject]@{ Status = "matched"; Process = [pscustomobject]@{ Id = $Entry.pid } }
        }
        function Request-TrackedProcessStop($Process) {
            $script:stopRequests += $Process.Id
        }
        function Wait-TrackedProcessExit($Process, [int]$TimeoutMilliseconds) {
            return $Process.Id -ne 1
        }
        function Stop-DemoCompose {
            $script:composeStops += 1
        }
        function Save-RemainingProcessState([object[]]$Entries) {
            $script:retainedEntries = @($Entries)
        }
        $script:RepoRoot = (Resolve-Path (Join-Path $ScratchRoot "..\..")).Path
        $script:DemoRoot = $ScratchRoot
        $script:StateFile = Join-Path $ScratchRoot "process-state.json"
        New-Item -ItemType Directory -Force -Path $ScratchRoot | Out-Null
        $entries = @(
            [ordered]@{ name = "api"; pid = 1; expected_executable = "one"; start_time_utc = "2026-01-01T00:00:00.0000000Z" },
            [ordered]@{ name = "worker"; pid = 2; expected_executable = "two"; start_time_utc = "2026-01-01T00:00:00.0000000Z" },
            [ordered]@{ name = "vite"; pid = 3; expected_executable = "three"; start_time_utc = "2026-01-01T00:00:00.0000000Z" }
        )
        $message = ""
        try {
            Rollback-Startup -Processes $entries -ComposeStarted $true
        }
        catch {
            $message = $_.Exception.Message
        }
        $retained = @($script:retainedEntries | ForEach-Object { $_.pid })
        Write-Result ([ordered]@{
            stop_requests = @($script:stopRequests)
            compose_stops = $script:composeStops
            retained_pids = @($retained)
            error = $message
        })
    }
    "child-environment" {
        $script:LogDirectory = $ScratchRoot
        New-Item -ItemType Directory -Force -Path $ScratchRoot | Out-Null
        $env:VITE_SENTINEL_SECRET = "must-not-leak"
        $env:AZURE_SENTINEL_SECRET = "must-not-leak"
        $shell = (Get-Process -Id $PID).Path
        $process = Start-DemoProcess -Name "environment" -FilePath $shell `
            -ArgumentList @("-NoProfile", "-File", $DumpEnvironmentScript) `
            -WorkingDirectory $ScratchRoot `
            -Environment @{ EXPECTED_CHILD_VALUE = "allowed" }
        $exited = $process.WaitForExit(10000)
        if ($exited) {
            $process.WaitForExit()
            $process.Refresh()
        }
        $output = Get-Content -Raw -LiteralPath (Join-Path $ScratchRoot "environment.stdout.log")
        Write-Result ([ordered]@{
            exited = [bool]$exited
            has_expected = $output.Contains("EXPECTED_CHILD_VALUE=allowed")
            has_vite_secret = $output.Contains("VITE_SENTINEL_SECRET")
            has_cloud_secret = $output.Contains("AZURE_SENTINEL_SECRET")
        })
    }
    "missing-node" {
        $priorPath = $env:PATH
        $emptyPath = Join-Path $ScratchRoot "empty-path"
        New-Item -ItemType Directory -Force -Path $emptyPath | Out-Null
        $env:PATH = $emptyPath
        $message = ""
        try {
            Resolve-NodeExecutable | Out-Null
        }
        catch {
            $message = $_.Exception.Message
        }
        finally {
            $env:PATH = $priorPath
        }
        Write-Result ([ordered]@{
            error = $message
            demo_created = Test-Path -LiteralPath (Join-Path $ScratchRoot "artifacts\demo")
        })
    }
    "reparse" {
        $safeRoot = Join-Path $ScratchRoot "safe"
        $outsideRoot = Join-Path $ScratchRoot "outside"
        New-Item -ItemType Directory -Force -Path $safeRoot, $outsideRoot | Out-Null
        $junction = Join-Path $safeRoot "junction"
        New-Item -ItemType Junction -Path $junction -Target $outsideRoot | Out-Null
        $junctionRejected = $false
        try {
            Assert-ContainedNonReparsePath -Path (Join-Path $junction "demo.env") -Root $safeRoot
        }
        catch {
            $junctionRejected = $true
        }
        $outsideLeaf = Join-Path $outsideRoot "leaf-target"
        New-Item -ItemType Directory -Force -Path $outsideLeaf | Out-Null
        $outsideFile = Join-Path $outsideLeaf "outside.txt"
        [System.IO.File]::WriteAllText($outsideFile, "outside")
        $leaf = Join-Path $safeRoot "leaf"
        $writeTarget = $leaf
        try {
            New-Item -ItemType SymbolicLink -Path $leaf -Target $outsideFile | Out-Null
        }
        catch {
            New-Item -ItemType Junction -Path $leaf -Target $outsideLeaf | Out-Null
            $writeTarget = Join-Path $leaf "outside.txt"
        }
        $leafRejected = $false
        try {
            $script:RepoRoot = $safeRoot
            Write-Utf8NoBom -Path $writeTarget -Lines @("overwritten")
        }
        catch {
            $leafRejected = $true
        }
        Write-Result ([ordered]@{
            junction_rejected = $junctionRejected
            leaf_rejected = $leafRejected
            outside_unchanged = ([System.IO.File]::ReadAllText($outsideFile) -eq "outside")
        })
    }
    default {
        throw "Unknown scenario: $Scenario"
    }
}
