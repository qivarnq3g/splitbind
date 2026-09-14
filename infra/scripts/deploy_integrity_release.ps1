[CmdletBinding()]
param(
    [string]$VmHost = $env:SPLITBIND_VM_HOST,
    [string]$AdminUser = $env:SPLITBIND_VM_ADMIN_USER,
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [string]$Hostname = "splitbind.qivarn.id.vn",
    [string]$AcmeEmail = $env:SPLITBIND_ACME_EMAIL,
    [string]$ApiImage = "ghcr.io/qivarnq3g/splitbind-api@sha256:15b9f8255fe170c28f5454e86113f16c424f9d606358c871258fbf8289c5f680",
    [string]$WebImage = "ghcr.io/qivarnq3g/splitbind-web@sha256:c17fbcf1cc506016497f10f4a8f44d1d753e0c317feef49bb50fdb12fc3aae58",
    [string]$DatabaseHost = $env:SPLITBIND_DATABASE_HOST,
    [string]$DatabaseUrl = $env:SPLITBIND_DATABASE_URL,
    [string]$R2Endpoint = $env:SPLITBIND_R2_ENDPOINT,
    [string]$R2Bucket = $(if ($env:SPLITBIND_R2_BUCKET) { $env:SPLITBIND_R2_BUCKET } else { "splitbind-storage" }),
    [string]$R2AccessKey = $env:SPLITBIND_R2_ACCESS_KEY,
    [string]$R2SecretKey = $env:SPLITBIND_R2_SECRET_KEY,
    [string]$AdminPassword = $env:SPLITBIND_ADMIN_PASSWORD,
    [string]$OrganizationName = "SplitBind",
    [string]$OrganizationSlug = "splitbind",
    [string]$BootstrapUsername = "admin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$missingTarget = @()
if (-not $VmHost) { $missingTarget += "SPLITBIND_VM_HOST (or -VmHost)" }
if (-not $AdminUser) { $missingTarget += "SPLITBIND_VM_ADMIN_USER (or -AdminUser)" }
if (-not $AcmeEmail) { $missingTarget += "SPLITBIND_ACME_EMAIL (or -AcmeEmail)" }
if (-not $DatabaseHost) { $missingTarget += "SPLITBIND_DATABASE_HOST (or -DatabaseHost)" }
if (-not $R2Endpoint) { $missingTarget += "SPLITBIND_R2_ENDPOINT (or -R2Endpoint)" }
if ($missingTarget.Count -gt 0) {
    throw "Missing deployment target settings: $($missingTarget -join ', '). The production host, administrator and endpoints are deliberately not stored in this repository; see infra/scripts/README.md."
}

if (-not $DatabaseUrl -or -not $R2AccessKey -or -not $R2SecretKey -or -not $AdminPassword) {
    throw "Missing required deployment credentials. Pass -DatabaseUrl, -R2AccessKey, -R2SecretKey, -AdminPassword or define their SPLITBIND_* environment variables."
}

Write-Host "Starting automated deployment of SplitBind Integrity Release 0.1 to Azure VM $VmHost..." -ForegroundColor Cyan

# 1. Generate local cryptographic keypair for worker signing
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$tempSecretDir = Join-Path $env:TEMP ("splitbind-deploy-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempSecretDir -Force | Out-Null

try {
    # Check if signing key already exists on remote VM
    $remoteKeyCheck = ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$AdminUser@$VmHost" "test -f /home/$AdminUser/splitbind/secrets/manifest-signing-key.pk8 && echo EXISTS || echo MISSING"
    $hasExistingKey = ($remoteKeyCheck -match "EXISTS")

    if ($hasExistingKey) {
        Write-Host "Reusing existing Ed25519 signing key on VM..." -ForegroundColor Yellow
        $extractSecret = ssh -i $SshKeyPath "$AdminUser@$VmHost" "grep DJANGO_SECRET_KEY /home/$AdminUser/splitbind/secrets/api.env | cut -d= -f2"
        $djangoSecretKey = $extractSecret.Trim()
    } else {
        Write-Host "Generating Ed25519 PKCS#8 encrypted signing key..." -ForegroundColor Yellow
        $keygenScript = @"
import os, secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

passphrase = secrets.token_urlsafe(32).encode('utf-8')
private_key = Ed25519PrivateKey.generate()
pkcs8_pem = private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.BestAvailableEncryption(passphrase),
)
django_secret = secrets.token_urlsafe(50)

with open('$($tempSecretDir.Replace('\', '/'))/manifest-signing-key.pk8', 'wb') as f:
    f.write(pkcs8_pem)
with open('$($tempSecretDir.Replace('\', '/'))/manifest-signing-key.passphrase', 'wb') as f:
    f.write(passphrase + b'\n')
with open('$($tempSecretDir.Replace('\', '/'))/django-secret-key.txt', 'w', encoding='utf-8') as f:
    f.write(django_secret)
print('KEYS_GENERATED')
"@
        & "$repoRoot\.venv\Scripts\python.exe" -c $keygenScript
        $djangoSecretKey = (Get-Content -Raw -Path (Join-Path $tempSecretDir "django-secret-key.txt")).Trim()

        Write-Host "Transferring encrypted signing keys to VM..." -ForegroundColor Yellow
        scp -i $SshKeyPath -o StrictHostKeyChecking=accept-new (Join-Path $tempSecretDir "manifest-signing-key.pk8") "$AdminUser@$VmHost`:/home/$AdminUser/splitbind/secrets/manifest-signing-key.pk8"
        scp -i $SshKeyPath -o StrictHostKeyChecking=accept-new (Join-Path $tempSecretDir "manifest-signing-key.passphrase") "$AdminUser@$VmHost`:/home/$AdminUser/splitbind/secrets/manifest-signing-key.passphrase"
    }

    # 4. Generate remote env files
    Write-Host "Writing remote environment files..." -ForegroundColor Yellow
    $apiEnvContent = @"
ENVIRONMENT=production
DJANGO_SECRET_KEY=$djangoSecretKey
DATABASE_URL=$DatabaseUrl
NEON_DATABASE_HOST=$DatabaseHost
SPLITBIND_ALLOWED_HOSTS=$Hostname,api,localhost,127.0.0.1
OBJECT_STORAGE_ENDPOINT=$R2Endpoint
OBJECT_STORAGE_ENDPOINT_HINT=$R2Endpoint
OBJECT_STORAGE_BUCKET=$R2Bucket
OBJECT_STORAGE_ACCESS_KEY=$R2AccessKey
OBJECT_STORAGE_SECRET_KEY=$R2SecretKey
MAX_PDF_BYTES=104857600
MAX_PDF_PAGES=50
MAX_IMAGE_PIXELS=40000000
MAX_DOCUMENT_RASTER_PIXELS=120000000
JOB_TIMEOUT_SECONDS=600
WORKER_CONCURRENCY=1
RETENTION_RECONCILIATION_LEASE_SECONDS=600
"@
    $workerEnvContent = @"
ENVIRONMENT=production
DJANGO_SECRET_KEY=$djangoSecretKey
DATABASE_URL=$DatabaseUrl
NEON_DATABASE_HOST=$DatabaseHost
SPLITBIND_ALLOWED_HOSTS=$Hostname,api,localhost,127.0.0.1
OBJECT_STORAGE_ENDPOINT=$R2Endpoint
OBJECT_STORAGE_ENDPOINT_HINT=$R2Endpoint
OBJECT_STORAGE_BUCKET=$R2Bucket
OBJECT_STORAGE_ACCESS_KEY=$R2AccessKey
OBJECT_STORAGE_SECRET_KEY=$R2SecretKey
MAX_PDF_BYTES=104857600
MAX_PDF_PAGES=50
MAX_IMAGE_PIXELS=40000000
MAX_DOCUMENT_RASTER_PIXELS=120000000
JOB_TIMEOUT_SECONDS=600
WORKER_CONCURRENCY=1
RETENTION_RECONCILIATION_LEASE_SECONDS=600
"@
    $composeEnvContent = @"
WEB_IMAGE=$WebImage
API_IMAGE=$ApiImage
SPLITBIND_HOSTNAME=$Hostname
ACME_EMAIL=$AcmeEmail
NEON_DATABASE_HOST=$DatabaseHost
R2_ENDPOINT=$R2Endpoint
API_ENV_FILE=/home/$AdminUser/splitbind/secrets/api.env
WORKER_ENV_FILE=/home/$AdminUser/splitbind/secrets/worker.env
MANIFEST_SIGNING_KEY_FILE=/home/$AdminUser/splitbind/secrets/manifest-signing-key.pk8
MANIFEST_SIGNING_KEY_PASSPHRASE_FILE=/home/$AdminUser/splitbind/secrets/manifest-signing-key.passphrase
"@

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $tempSecretDir "api.env"), $apiEnvContent, $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $tempSecretDir "worker.env"), $workerEnvContent, $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $tempSecretDir "compose.env"), $composeEnvContent, $utf8NoBom)

    scp -i $SshKeyPath (Join-Path $tempSecretDir "api.env") "$AdminUser@$VmHost`:~/splitbind/secrets/api.env"
    scp -i $SshKeyPath (Join-Path $tempSecretDir "worker.env") "$AdminUser@$VmHost`:~/splitbind/secrets/worker.env"
    scp -i $SshKeyPath (Join-Path $tempSecretDir "compose.env") "$AdminUser@$VmHost`:~/splitbind/compose/.env"

    # Copy compose.production.yaml
    scp -i $SshKeyPath (Join-Path $repoRoot "infra\compose\compose.production.yaml") "$AdminUser@$VmHost`:~/splitbind/compose/compose.yaml"

    # Set strict Linux file permissions on secrets
    ssh -i $SshKeyPath "$AdminUser@$VmHost" "chmod 700 /home/$AdminUser/splitbind/secrets; chmod 600 /home/$AdminUser/splitbind/secrets/*.env /home/$AdminUser/splitbind/compose/.env; chmod 644 /home/$AdminUser/splitbind/secrets/manifest-signing-key.*"

    # 5. Pull immutable container images
    Write-Host "Pulling immutable container images on VM..." -ForegroundColor Yellow
    ssh -i $SshKeyPath "$AdminUser@$VmHost" "docker pull $ApiImage; docker pull $WebImage"

    # 6. Run one-shot database migrations
    Write-Host "Executing database migrations..." -ForegroundColor Yellow
    $migrateCommand = "docker run --rm --entrypoint /usr/local/bin/migration-entrypoint.sh --env-file /home/$AdminUser/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 $ApiImage"
    ssh -i $SshKeyPath "$AdminUser@$VmHost" $migrateCommand

    # 7. Run one-shot production bootstrap for administrator
    Write-Host "Bootstrapping initial production administrator..." -ForegroundColor Yellow
    $bootstrapCommand = "docker run --rm --entrypoint python --env-file /home/$AdminUser/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 -e SPLITBIND_BOOTSTRAP_PASSWORD='$AdminPassword' $ApiImage manage.py bootstrap_integrity_release --organization-name '$OrganizationName' --organization-slug '$OrganizationSlug' --username '$BootstrapUsername'"
    ssh -i $SshKeyPath "$AdminUser@$VmHost" $bootstrapCommand

    # 8. Register worker integrity signing key in database
    Write-Host "Registering integrity signing key in database..." -ForegroundColor Yellow
    $getOrgIdCmd = "docker run --rm --entrypoint python --env-file /home/$AdminUser/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 $ApiImage manage.py shell -c 'from splitbind.access.models import Organization; print(Organization.objects.first().id)'"
    $orgId = (ssh -i $SshKeyPath "$AdminUser@$VmHost" $getOrgIdCmd | Select-String -Pattern '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$').Line.Trim()

    $pyCheck = "from splitbind.access.models import SigningKey, SigningKeyStatus; from splitbind.release.manifest import load_manifest_signing_key, public_key_pem; k = load_manifest_signing_key('/secrets/manifest-signing-key.pk8', '/secrets/manifest-signing-key.passphrase'); print('KEY_EXISTS=' + str(SigningKey.objects.filter(public_key=public_key_pem(k), status=SigningKeyStatus.ACTIVE).exists()))"
    $checkKeyCmd = 'docker run --rm --user 0:0 --entrypoint python --env-file /home/' + $AdminUser + '/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 -v /home/' + $AdminUser + '/splitbind/secrets:/secrets:ro ' + $ApiImage + ' manage.py shell -c \"' + $pyCheck + '\"'
    $keyCheckOutput = ssh -i $SshKeyPath "$AdminUser@$VmHost" $checkKeyCmd
    if ($keyCheckOutput -match "KEY_EXISTS=True") {
        Write-Host "Active integrity signing key already registered in database." -ForegroundColor Green
    } else {
        $keyId = "key-integrity-" + (Get-Date -Format "yyyyMMdd-HHmmss")
        $registerKeyCommand = "docker run --rm --user 0:0 --entrypoint python --env-file /home/$AdminUser/splitbind/secrets/api.env -e SPLITBIND_RELEASE_MODE=integrity_v1 -v /home/$AdminUser/splitbind/secrets:/secrets:ro $ApiImage manage.py register_integrity_signing_key --organization-id '$orgId' --key-id '$keyId' --private-key-file /secrets/manifest-signing-key.pk8 --passphrase-file /secrets/manifest-signing-key.passphrase --valid-from '2026-09-08T00:00:00Z'"
        ssh -i $SshKeyPath "$AdminUser@$VmHost" $registerKeyCommand
    }

    # 9. Start production Docker Compose services
    Write-Host "Starting production Docker Compose services..." -ForegroundColor Yellow
    ssh -i $SshKeyPath "$AdminUser@$VmHost" "cd /home/$AdminUser/splitbind/compose && docker compose down --remove-orphans; docker compose up -d"

    # 10. Wait and probe healthchecks
    Write-Host "Waiting for services to become healthy..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15
    $healthOutput = ssh -i $SshKeyPath "$AdminUser@$VmHost" "cd /home/$AdminUser/splitbind/compose && docker compose ps"
    Write-Host $healthOutput

    # 11. Probe HTTPS public endpoint
    Write-Host "Testing public HTTPS endpoint https://$Hostname..." -ForegroundColor Yellow
    $httpsStatus = $null
    for ($i = 1; $i -le 6; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "https://$Hostname" -UseBasicParsing -TimeoutSec 10
            if ($resp.StatusCode -eq 200) {
                $httpsStatus = "200 OK"
                break
            }
        } catch {
            Write-Host "Waiting for Caddy certificate issuance (attempt $i/6): $($_.Exception.Message)"
            Start-Sleep -Seconds 10
        }
    }

    if (-not $httpsStatus) {
        throw "Public HTTPS never returned 200 for https://$Hostname. The cutover is NOT verified; inspect Caddy certificate issuance before calling this a release."
    }

    Write-Host "`nDEPLOYMENT VERIFIED." -ForegroundColor Green
    Write-Host "Endpoint: https://$Hostname"
    Write-Host "HTTPS Status: $httpsStatus"
    Write-Host "Admin Username: $BootstrapUsername"
    Write-Host "Organization: $OrganizationName ($OrganizationSlug)"

} finally {
    if (Test-Path $tempSecretDir) {
        Remove-Item -Path $tempSecretDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
