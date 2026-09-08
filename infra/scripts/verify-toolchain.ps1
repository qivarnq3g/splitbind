param([switch]$ReleaseTools)
$ErrorActionPreference = "Stop"
$expected = [ordered]@{
    node = '^v24\.18\.0$'
    npm = '^12\.[0-9]+\.[0-9]+$'
    python = '^Python 3\.11\.9$'
    rustc = '^rustc 1\.97\.1(?: .*)?$'
}
foreach ($name in $expected.Keys) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_TOOL:$name" }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $probeOutput = @(& $name --version 2>$null)
        $probeExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($probeExit -ne 0) { throw "TOOL_EXIT:${name}:$probeExit" }
    $actual = ([string]($probeOutput | Select-Object -First 1)).Trim()
    if ($actual -notmatch $expected[$name]) { throw "TOOL_VERSION:${name}:$actual" }
}
foreach ($name in @("docker")) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_TOOL:$name" }
}
if ($ReleaseTools) {
    foreach ($name in @("gh", "az")) {
        if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_RELEASE_TOOL:$name" }
    }
}
Write-Output "TOOLCHAIN_OK"
