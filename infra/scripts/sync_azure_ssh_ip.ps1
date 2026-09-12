[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-splitbind-prod",
    [string]$NsgName = "nsg-splitbind-prod",
    [string]$RuleName = "AllowSshFromAdmin",
    [string]$VmHost = "PRODUCTION_VM_HOST",
    [string]$AdminUser = "PRODUCTION_VM_ADMIN",
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [ValidateSet("32", "24", "16")]
    [string]$SubnetMask = "32"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Checking current workstation public IPv4 address..." -ForegroundColor Cyan
$currentIp = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
if (-not $currentIp -or $currentIp -notmatch '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$') {
    throw "Failed to resolve valid public IPv4 address: '$currentIp'"
}
Write-Host "Current Public IPv4: $currentIp" -ForegroundColor Green

$octets = $currentIp.Split('.')
$expectedPrefix = switch ($SubnetMask) {
    "16" { "$($octets[0]).$($octets[1]).0.0/16" }
    "24" { "$($octets[0]).$($octets[1]).$($octets[2]).0/24" }
    "32" { "$currentIp/32" }
}

Write-Host "Querying Azure NSG rule '$RuleName' in '$ResourceGroup'..." -ForegroundColor Cyan
$ruleJson = az network nsg rule show -g $ResourceGroup --nsg-name $NsgName -n $RuleName -o json | ConvertFrom-Json
$configuredPrefix = $ruleJson.sourceAddressPrefix
Write-Host "Configured NSG Prefix: $configuredPrefix"

if ($configuredPrefix -eq $expectedPrefix) {
    Write-Host "NSG rule is already synchronized with current IP subnet ($expectedPrefix)." -ForegroundColor Green
} else {
    Write-Host "IP changed ($configuredPrefix -> $expectedPrefix). Updating Azure NSG rule..." -ForegroundColor Yellow
    az network nsg rule update -g $ResourceGroup --nsg-name $NsgName -n $RuleName --source-address-prefixes $expectedPrefix -o json | Out-Null
    Write-Host "Azure NSG rule updated successfully to $expectedPrefix." -ForegroundColor Green
}

Write-Host "Testing SSH connectivity to $AdminUser@$VmHost..." -ForegroundColor Cyan
$sshResult = ssh -n -i $SshKeyPath -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$AdminUser@$VmHost" "uptime"
Write-Host "SSH Connected successfully: $sshResult" -ForegroundColor Green
