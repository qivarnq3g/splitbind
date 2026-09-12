[CmdletBinding()]
param(
    [string]$VmHost = $env:SPLITBIND_VM_HOST,
    [string]$AdminUser = $env:SPLITBIND_VM_ADMIN_USER,
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [ValidateSet("true", "false")]
    [string]$Enabled = "true",
    [switch]$RotateKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$missingTarget = @()
if (-not $VmHost) { $missingTarget += "SPLITBIND_VM_HOST (or -VmHost)" }
if (-not $AdminUser) { $missingTarget += "SPLITBIND_VM_ADMIN_USER (or -AdminUser)" }
if ($missingTarget.Count -gt 0) {
    throw "Missing deployment target settings: $($missingTarget -join ', '). The production host, administrator and endpoints are deliberately not stored in this repository; see infra/scripts/README.md."
}

$remoteRoot = "/home/$AdminUser/splitbind"
$composeFile = "$remoteRoot/compose/compose.yaml"

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    $Command = $Command -replace "`r", ""
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

Write-Host "Setting the transformed-attribution capability to '$Enabled'." -ForegroundColor Cyan

$existing = Invoke-Remote "grep -c '^SPLITBIND_DEMO_FINGERPRINT_KEY_HEX=' $remoteRoot/secrets/worker.env || true"
$hasKey = (($existing -join "").Trim() -ne "0")

if ($hasKey -and -not $RotateKey) {
    Write-Host "A fingerprint key is already present and is being kept." -ForegroundColor Green
} else {
    if ($hasKey) {
        Write-Warning "Rotating the fingerprint key makes every previously issued document undecodable."
    }
    Write-Host "Generating a fingerprint key on the VM; the value is never printed or transferred." -ForegroundColor Yellow
    $generate = "key=`$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n') && " +
                "sed -i '/^SPLITBIND_DEMO_FINGERPRINT_KEY_HEX=/d' $remoteRoot/secrets/worker.env && " +
                "printf 'SPLITBIND_DEMO_FINGERPRINT_KEY_HEX=%s\n' `"`$key`" >> $remoteRoot/secrets/worker.env && " +
                "unset key && echo KEY_WRITTEN"
    $result = Invoke-Remote $generate
    if (($result -join "`n") -notmatch "KEY_WRITTEN") {
        throw "Failed to write the fingerprint key: $($result -join "`n")"
    }
    Write-Host "Fingerprint key written." -ForegroundColor Green
}

foreach ($envName in @("api.env", "worker.env")) {
    $envPath = "$remoteRoot/secrets/$envName"
    Invoke-Remote "sed -i '/^SPLITBIND_FINGERPRINT_ENABLED=/d' $envPath" | Out-Null
    Invoke-Remote "printf 'SPLITBIND_FINGERPRINT_ENABLED=%s\n' '$Enabled' >> $envPath" | Out-Null
    Invoke-Remote "chmod 600 $envPath" | Out-Null
    $observed = Invoke-Remote "grep '^SPLITBIND_FINGERPRINT_ENABLED=' $envPath"
    Write-Host "  ${envName}: $($observed -join '')"
    if (($observed -join "") -ne "SPLITBIND_FINGERPRINT_ENABLED=$Enabled") {
        throw "$envName was not set correctly."
    }
}

$keyPresent = Invoke-Remote "grep -c '^SPLITBIND_DEMO_FINGERPRINT_KEY_HEX=[0-9a-f]\{64\}$' $remoteRoot/secrets/worker.env"
if (($keyPresent -join "").Trim() -ne "1") {
    throw "worker.env does not hold exactly one well-formed fingerprint key; refusing to restart."
}
Write-Host "worker.env holds exactly one 64-character hexadecimal key." -ForegroundColor Green

Write-Host "Restarting the API and worker." -ForegroundColor Yellow
Invoke-Remote "cd $remoteRoot/compose && docker compose up -d api worker" | Write-Host

$healthy = $false
for ($attempt = 1; $attempt -le 15; $attempt++) {
    Start-Sleep -Seconds 6
    $state = Invoke-Remote "cd $remoteRoot/compose && docker compose ps -q | xargs -r docker inspect --format '{{.Name}}={{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}'"
    $joined = $state -join " "
    Write-Host "  attempt ${attempt}: $joined"
    if (@($state | Where-Object { $_ -match '=' }).Count -ge 3 -and -not ($joined -match "starting|unhealthy|restarting|exited|created")) {
        $healthy = $true
        break
    }
}
if (-not $healthy) {
    throw "Services did not return to health. Set -Enabled false and rerun to back the capability out."
}

Write-Host "`nCAPABILITY SET TO '$Enabled' AND SERVICES HEALTHY." -ForegroundColor Green
