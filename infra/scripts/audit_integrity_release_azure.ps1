[CmdletBinding()]
param(
    [string]$ResourceGroupName = "rg-splitbind-prod",
    [string]$VmName = "vm-splitbind-prod",
    [string]$SshKeyPath = "$env:USERPROFILE\.ssh\splitbind_azure_ed25519",
    [string]$AdminUser = $env:SPLITBIND_VM_ADMIN_USER,
    [string]$ExpectedHostname = "splitbind.qivarn.id.vn"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$missingTarget = @()
if (-not $AdminUser) { $missingTarget += "SPLITBIND_VM_ADMIN_USER (or -AdminUser)" }
if ($missingTarget.Count -gt 0) {
    throw "Missing deployment target settings: $($missingTarget -join ', '). The production host, administrator and endpoints are deliberately not stored in this repository; see infra/scripts/README.md."
}

Write-Host "Running read-only Azure preflight audit for SplitBind Integrity Release 0.1..." -ForegroundColor Cyan

$auditResults = [ordered]@{}

# 1. Subscription check
try {
    $account = az account show -o json | ConvertFrom-Json
    $auditResults["subscription_name"] = $account.name
    $auditResults["subscription_id"] = $account.id
    $auditResults["subscription_status"] = if ($account.state -eq "Enabled") { "PASS" } else { "FAIL" }
} catch {
    $auditResults["subscription_status"] = "FAIL"
    $auditResults["subscription_error"] = $_.Exception.Message
}

# 2. VM and Resource Group check
try {
    $vm = az vm show -g $ResourceGroupName -n $VmName -o json | ConvertFrom-Json
    $auditResults["vm_name"] = $vm.name
    $auditResults["vm_size"] = $vm.hardwareProfile.vmSize
    $auditResults["vm_location"] = $vm.location
    $auditResults["vm_identity"] = $vm.identity.type
    $auditResults["vm_status"] = if ($vm.hardwareProfile.vmSize -eq "Standard_B2ls_v2") { "PASS" } else { "WARN" }
} catch {
    $auditResults["vm_status"] = "FAIL"
    $auditResults["vm_error"] = $_.Exception.Message
}

# 3. Public IP and DNS check
try {
    $pip = az network public-ip show -g $ResourceGroupName -n "pip-splitbind-prod" --query ipAddress -o tsv
    $auditResults["public_ip"] = $pip
    $dns = Resolve-DnsName -Name $ExpectedHostname -Server "1.1.1.1" -ErrorAction SilentlyContinue
    $dnsIp = if ($dns) { ($dns | Where-Object { $_.Type -eq "A" } | Select-Object -First 1).IPAddress } else { $null }
    $auditResults["dns_resolved_ip"] = $dnsIp
    $auditResults["dns_match"] = if ($dnsIp -eq $pip) { "PASS" } else { "FAIL" }
} catch {
    $auditResults["dns_match"] = "FAIL"
    $auditResults["dns_error"] = $_.Exception.Message
}

# 4. NSG Firewall rules check
try {
    $currentIp = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
    $auditResults["current_admin_ip"] = $currentIp
    $sshRule = az network nsg rule show -g $ResourceGroupName --nsg-name "nsg-splitbind-prod" -n "AllowSshFromAdmin" -o json | ConvertFrom-Json
    $sshPrefix = $sshRule.sourceAddressPrefix
    $auditResults["nsg_ssh_prefix"] = $sshPrefix
    $auditResults["nsg_ssh_status"] = if ($sshPrefix -eq "$currentIp/32") { "PASS" } else { "WARN" }
} catch {
    $auditResults["nsg_ssh_status"] = "FAIL"
    $auditResults["nsg_error"] = $_.Exception.Message
}

# 5. Azure Budget check
try {
    $budgets = az consumption budget list -o json | ConvertFrom-Json
    $matchedBudget = $budgets | Where-Object { $_.name -eq "SplitBind-Monthly-Budget" } | Select-Object -First 1
    if ($matchedBudget) {
        $auditResults["budget_name"] = $matchedBudget.name
        $auditResults["budget_amount"] = $matchedBudget.amount
        $auditResults["budget_status"] = "PASS"
    } else {
        $auditResults["budget_status"] = "FAIL"
    }
} catch {
    $auditResults["budget_status"] = "FAIL"
    $auditResults["budget_error"] = $_.Exception.Message
}

# 6. SSH and VM resource check
try {
    $sshOutput = ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new -o BatchMode=yes "$AdminUser@$($auditResults['public_ip'])" "df -m /; free -m; docker --version; docker compose version"
    $auditResults["ssh_connection"] = "PASS"
    $auditResults["vm_diagnostics"] = $sshOutput
} catch {
    $auditResults["ssh_connection"] = "FAIL"
    $auditResults["ssh_error"] = $_.Exception.Message
}

Write-Host "Audit completed:" -ForegroundColor Green
$auditResults | ConvertTo-Json -Depth 5
