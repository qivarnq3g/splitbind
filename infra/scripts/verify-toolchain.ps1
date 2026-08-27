param([switch]$ReleaseTools)
$ErrorActionPreference = "Stop"
$expected = [ordered]@{ node = "v24."; npm = "12."; python = "Python 3.11."; rustc = "rustc 1.97." }
foreach ($name in $expected.Keys) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "MISSING_TOOL:$name" }
    $actual = (& $name --version | Select-Object -First 1).Trim()
    if (-not $actual.StartsWith($expected[$name])) { throw "TOOL_VERSION:${name}:$actual" }
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
