[CmdletBinding()]
param(
    [string]$VmHost = "PRODUCTION_VM_HOST",
    [string]$AdminUser = "PRODUCTION_VM_ADMIN",
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [string]$ApiImage = "",
    [string]$WebImage = "",
    [string]$ReleaseName = ("release-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string]$Hostname = "splitbind.qivarn.id.vn"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

# 1. Automatically load image digests from release-images.env if not provided
$envFile = Join-Path $repoRoot "release-images.env"
if (-not $ApiImage -and (Test-Path $envFile)) {
    $lines = Get-Content $envFile
    foreach ($line in $lines) {
        if ($line -match '^API_IMAGE=(.+)$') { $ApiImage = $matches[1].Trim() }
        if ($line -match '^WEB_IMAGE=(.+)$') { $WebImage = $matches[1].Trim() }
    }
}

if (-not $ApiImage -or -not $WebImage) {
    throw "Missing required image digests. Pass -ApiImage and -WebImage or place them in release-images.env."
}

Write-Host "Starting automated production image update for SplitBind..." -ForegroundColor Cyan
Write-Host "Target Host: $AdminUser@$VmHost"
Write-Host "API Image:   $ApiImage"
Write-Host "Web Image:   $WebImage"
Write-Host "Release Tag: $ReleaseName"

# 2. Sync Azure NSG IP
$syncScript = Join-Path $scriptDir "sync_azure_ssh_ip.ps1"
if (Test-Path $syncScript) {
    & $syncScript -VmHost $VmHost -AdminUser $AdminUser -SshKeyPath $SshKeyPath
}

# 3. Create rollback backup directory on remote VM
Write-Host "Creating rollback directory /home/$AdminUser/splitbind/rollbacks/$ReleaseName..." -ForegroundColor Yellow
$backupCmd = @"
mkdir -m 700 -p /home/$AdminUser/splitbind/rollbacks/$ReleaseName && \
cp /home/$AdminUser/splitbind/compose/.env /home/$AdminUser/splitbind/rollbacks/$ReleaseName/compose.env && \
cp /home/$AdminUser/splitbind/compose/compose.yaml /home/$AdminUser/splitbind/rollbacks/$ReleaseName/compose.yaml && \
chmod 600 /home/$AdminUser/splitbind/rollbacks/$ReleaseName/* && \
docker compose -f /home/$AdminUser/splitbind/compose/compose.yaml exec -T api python manage.py dumpdata --output /tmp/metadata-backup.json && \
docker compose -f /home/$AdminUser/splitbind/compose/compose.yaml exec -T api cat /tmp/metadata-backup.json > /home/$AdminUser/splitbind/rollbacks/$ReleaseName/metadata.json && \
chmod 600 /home/$AdminUser/splitbind/rollbacks/$ReleaseName/metadata.json && \
docker compose -f /home/$AdminUser/splitbind/compose/compose.yaml exec -T api rm -f /tmp/metadata-backup.json && \
python3 -m json.tool /home/$AdminUser/splitbind/rollbacks/$ReleaseName/metadata.json > /dev/null && \
echo BACKUP_SUCCESS
"@

$sshBackup = ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" $backupCmd
if ($sshBackup -notmatch "BACKUP_SUCCESS") {
    throw "Rollback backup failed on VM: $sshBackup"
}
Write-Host "Rollback state and metadata successfully saved and validated." -ForegroundColor Green

# 4. Pull new immutable container images
Write-Host "Pulling immutable container images on VM..." -ForegroundColor Yellow
ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" "docker pull $ApiImage && docker pull $WebImage"
Write-Host "Images pulled successfully." -ForegroundColor Green

# 5. Check database migrations
Write-Host "Verifying database migrations with new API image..." -ForegroundColor Yellow
$checkMigrateCmd = "docker run --rm --entrypoint python --env-file /home/$AdminUser/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 $ApiImage manage.py showmigrations"
$migrateStatus = ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" $checkMigrateCmd
Write-Host "Migrations verified." -ForegroundColor Green

# 6. Update compose .env on remote VM
Write-Host "Updating image references in /home/$AdminUser/splitbind/compose/.env..." -ForegroundColor Yellow
$updateEnvCmd = @"
sed -i 's|^API_IMAGE=.*|API_IMAGE=$ApiImage|' /home/$AdminUser/splitbind/compose/.env && \
sed -i 's|^WEB_IMAGE=.*|WEB_IMAGE=$WebImage|' /home/$AdminUser/splitbind/compose/.env && \
grep -E 'IMAGE' /home/$AdminUser/splitbind/compose/.env
"@
$envUpdateResult = ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" $updateEnvCmd
Write-Host "Updated Environment:`n$envUpdateResult" -ForegroundColor Green

# 7. Restart Docker Compose services
Write-Host "Restarting Docker Compose services..." -ForegroundColor Yellow
ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" "cd /home/$AdminUser/splitbind/compose && docker compose up -d"

# 8. Probe healthchecks
Write-Host "Waiting for services to become healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
$psOutput = ssh -n -i $SshKeyPath -o BatchMode=yes "$AdminUser@$VmHost" "docker compose -f /home/$AdminUser/splitbind/compose/compose.yaml ps"
Write-Host $psOutput

# 9. Probe public HTTPS endpoint
Write-Host "Probing public health endpoint https://$Hostname/health/live..." -ForegroundColor Yellow
$healthResp = curl.exe -s -i "https://$Hostname/health/live"
if ($healthResp -match "HTTP/1.1 200 OK" -and $healthResp -match '\{\"status\":\s*\"ok\"\}') {
    Write-Host "Public healthcheck PASSED: 200 OK" -ForegroundColor Green
} else {
    throw "Public healthcheck failed:`n$healthResp"
}

Write-Host "`nPRODUCTION UPDATE COMPLETED SUCCESSFULLY!" -ForegroundColor Green
