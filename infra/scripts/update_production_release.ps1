[CmdletBinding()]
param(
    [string]$VmHost = "PRODUCTION_VM_HOST",
    [string]$AdminUser = "PRODUCTION_VM_ADMIN",
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [string]$ApiImage = "",
    [string]$WebImage = "",
    [string]$ReleaseName = ("release-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$Hostname = "splitbind.qivarn.id.vn",
    [switch]$SkipComposeSync,
    [switch]$SkipMigrations
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$remoteRoot = "/home/$AdminUser/splitbind"
$composeFile = "$remoteRoot/compose/compose.yaml"
$rollbackDir = "$remoteRoot/rollbacks/$ReleaseName"

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" "( $Command ) 2>&1"
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "Remote command failed with exit code ${code}:`n$Command`n$($output -join "`n")"
    }
    return $output
}

function Invoke-Scp {
    param(
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$RemotePath
    )
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        scp -i $SshKeyPath $LocalPath "$AdminUser@$VmHost`:$RemotePath"
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) {
        throw "Failed to copy $LocalPath to ${RemotePath}: scp exited with $code"
    }
}

$envFile = Join-Path $repoRoot "release-images.env"
if (-not $ApiImage -and (Test-Path $envFile)) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^API_IMAGE=(.+)$') { $ApiImage = $matches[1].Trim() }
        if ($line -match '^WEB_IMAGE=(.+)$') { $WebImage = $matches[1].Trim() }
    }
}

if (-not $ApiImage -or -not $WebImage) {
    throw "Missing required image digests. Pass -ApiImage and -WebImage or place them in release-images.env."
}
foreach ($reference in @($ApiImage, $WebImage)) {
    if ($reference -notmatch '@sha256:[0-9a-f]{64}$') {
        throw "Image reference '$reference' is not an immutable digest. A mutable tag is not an acceptable deployment input."
    }
}

Write-Host "Starting production update for SplitBind." -ForegroundColor Cyan
Write-Host "Target Host: $AdminUser@$VmHost"
Write-Host "API Image:   $ApiImage"
Write-Host "Web Image:   $WebImage"
Write-Host "Release Tag: $ReleaseName"

$syncScript = Join-Path $scriptDir "sync_azure_ssh_ip.ps1"
if (Test-Path $syncScript) {
    & $syncScript -VmHost $VmHost -AdminUser $AdminUser -SshKeyPath $SshKeyPath
}

Write-Host "Creating rollback directory $rollbackDir." -ForegroundColor Yellow
$backupCmd = @"
mkdir -m 700 -p $rollbackDir && \
cp $remoteRoot/compose/.env $rollbackDir/compose.env && \
cp $composeFile $rollbackDir/compose.yaml && \
chmod 600 $rollbackDir/* && \
docker compose -f $composeFile exec -T api python manage.py dumpdata --output /tmp/metadata-backup.json && \
docker compose -f $composeFile exec -T api cat /tmp/metadata-backup.json > $rollbackDir/metadata.json && \
chmod 600 $rollbackDir/metadata.json && \
docker compose -f $composeFile exec -T api rm -f /tmp/metadata-backup.json && \
python3 -m json.tool $rollbackDir/metadata.json > /dev/null && \
echo BACKUP_SUCCESS
"@
$sshBackup = Invoke-Remote $backupCmd
if ($sshBackup -notmatch "BACKUP_SUCCESS") {
    throw "Rollback backup failed on VM: $sshBackup"
}
Write-Host "Rollback state and metadata saved and validated." -ForegroundColor Green

if (-not $SkipComposeSync) {
    $localCompose = Join-Path $repoRoot "infra\compose\compose.production.yaml"
    Write-Host "Comparing the running Compose file against $localCompose." -ForegroundColor Yellow
    $remoteCompose = Invoke-Remote "cat $composeFile"
    $remoteText = ($remoteCompose -join "`n")
    $localText = ((Get-Content -Raw -Path $localCompose) -replace "`r`n", "`n").TrimEnd()
    if ($remoteText.TrimEnd() -eq $localText) {
        Write-Host "Running Compose file already matches the repository." -ForegroundColor Green
    } else {
        Write-Host "Compose file differs. Replacing it; the previous copy is in $rollbackDir/compose.yaml." -ForegroundColor Yellow
        $diffPath = Join-Path $env:TEMP ("splitbind-remote-compose-" + [guid]::NewGuid().ToString("N") + ".yaml")
        try {
            [System.IO.File]::WriteAllText($diffPath, $remoteText, (New-Object System.Text.UTF8Encoding($false)))
            Compare-Object -ReferenceObject (Get-Content $diffPath) -DifferenceObject (Get-Content $localCompose) |
                Format-Table -AutoSize | Out-String | Write-Host
        } finally {
            Remove-Item -Path $diffPath -Force -ErrorAction SilentlyContinue
        }
        Invoke-Scp -LocalPath $localCompose -RemotePath $composeFile
        Write-Host "Compose file synchronized." -ForegroundColor Green
    }
}

Write-Host "Pulling immutable container images on VM." -ForegroundColor Yellow
Invoke-Remote "docker pull $ApiImage && docker pull $WebImage" | Out-Null
Write-Host "Images pulled." -ForegroundColor Green

$runApi = "docker run --rm --env-file $remoteRoot/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1"
Write-Host "Migration state before the release:" -ForegroundColor Yellow
Invoke-Remote "$runApi --entrypoint python $ApiImage manage.py showmigrations --plan | grep '\[ \]' || echo 'NO_UNAPPLIED_MIGRATIONS'" | Write-Host

if (-not $SkipMigrations) {
    Write-Host "Applying database migrations with the new API image." -ForegroundColor Yellow
    Invoke-Remote "$runApi --entrypoint /usr/local/bin/migration-entrypoint.sh $ApiImage" | Write-Host
    Write-Host "Migration state after the release:" -ForegroundColor Yellow
    $pending = Invoke-Remote "$runApi --entrypoint python $ApiImage manage.py showmigrations --plan | grep '\[ \]' || echo 'NO_UNAPPLIED_MIGRATIONS'"
    Write-Host $pending
    if ($pending -notmatch "NO_UNAPPLIED_MIGRATIONS") {
        throw "Migrations remain unapplied after running the migration entrypoint:`n$pending"
    }
}

Write-Host "Updating image references in $remoteRoot/compose/.env." -ForegroundColor Yellow
$updateEnvCmd = @"
sed -i 's|^API_IMAGE=.*|API_IMAGE=$ApiImage|' $remoteRoot/compose/.env && \
sed -i 's|^WEB_IMAGE=.*|WEB_IMAGE=$WebImage|' $remoteRoot/compose/.env && \
grep -E '^(API|WEB)_IMAGE=' $remoteRoot/compose/.env
"@
$envUpdateResult = Invoke-Remote $updateEnvCmd
Write-Host "Updated environment:`n$envUpdateResult" -ForegroundColor Green

Write-Host "Validating the Caddyfile inside the new web image before recreating the edge." -ForegroundColor Yellow
$caddyCheck = "docker run --rm -e SPLITBIND_HOSTNAME=$Hostname -e ACME_EMAIL=preflight@example.invalid --entrypoint caddy $WebImage validate --config /etc/caddy/Caddyfile --adapter caddyfile"
$caddyOutput = Invoke-Remote $caddyCheck
if (($caddyOutput -join "`n") -notmatch "Valid configuration") {
    throw "The Caddyfile in $WebImage did not validate. Recreating the edge would take the site down:`n$caddyOutput"
}
Write-Host "Caddyfile valid." -ForegroundColor Green

Write-Host "Restarting Docker Compose services." -ForegroundColor Yellow
Invoke-Remote "cd $remoteRoot/compose && docker compose up -d --remove-orphans" | Write-Host

Write-Host "Waiting for every container to report healthy." -ForegroundColor Yellow
$inspectCmd = "cd $remoteRoot/compose && docker compose ps -q | xargs -r docker inspect --format '{{.Name}}={{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}'"
$healthy = $false
for ($attempt = 1; $attempt -le 20; $attempt++) {
    Start-Sleep -Seconds 6
    $states = Invoke-Remote $inspectCmd
    $joined = ($states -join " ")
    Write-Host "  attempt ${attempt}: $joined"
    $reported = @($states | Where-Object { $_ -match '=' })
    if ($reported.Count -ge 3 -and -not ($joined -match "starting|unhealthy|restarting|exited|created")) {
        $healthy = $true
        break
    }
}
if (-not $healthy) {
    throw "Containers did not all reach a healthy state. Roll back with the configuration saved in $rollbackDir."
}
Write-Host "All services healthy." -ForegroundColor Green

Write-Host "Probing https://$Hostname/health/live." -ForegroundColor Yellow
$live = $null
for ($attempt = 1; $attempt -le 6; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri "https://$Hostname/health/live" -UseBasicParsing -TimeoutSec 15
        if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
            $live = $response.Content
            break
        }
    } catch {
        Write-Host "  attempt ${attempt}: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 10
}
if (-not $live) {
    throw "Public liveness probe never returned 200 with status ok. The rollout is NOT verified. Roll back using $rollbackDir."
}
Write-Host "Liveness: $live" -ForegroundColor Green

Write-Host "Probing https://$Hostname/health/ready." -ForegroundColor Yellow
$readyStatus = 0
$readyBody = ""
try {
    $ready = Invoke-WebRequest -Uri "https://$Hostname/health/ready" -UseBasicParsing -TimeoutSec 15
    $readyStatus = [int]$ready.StatusCode
    $readyBody = $ready.Content
} catch {
    $failed = $_.Exception.Response
    if ($null -ne $failed) {
        $readyStatus = [int]$failed.StatusCode
        $reader = New-Object System.IO.StreamReader($failed.GetResponseStream())
        try { $readyBody = $reader.ReadToEnd() } finally { $reader.Close() }
    } else {
        $readyBody = $_.Exception.Message
    }
}
Write-Host "Readiness: HTTP $readyStatus $readyBody"
if ($readyStatus -ne 200) {
    throw "Public readiness probe returned HTTP $readyStatus. The rollout is NOT verified. Roll back using $rollbackDir."
}

Write-Host "`nPRODUCTION UPDATE VERIFIED." -ForegroundColor Green
Write-Host "Endpoint:  https://$Hostname"
Write-Host "API image: $ApiImage"
Write-Host "Web image: $WebImage"
Write-Host "Rollback:  $rollbackDir"
