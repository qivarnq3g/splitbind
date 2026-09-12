import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = sorted((ROOT / "infra" / "scripts").glob("*.ps1"))

PARSE_SNIPPET = (
    "$errors = $null; "
    "[void][System.Management.Automation.Language.Parser]::ParseFile("
    "'__PATH__', [ref]$null, [ref]$errors); "
    "if ($errors -and $errors.Count -gt 0) { "
    "$errors | ForEach-Object { Write-Output \"$($_.Extent.StartLineNumber): $($_.Message)\" }; exit 1 } "
    "else { exit 0 }"
)


def _host() -> str | None:
    for executable in ("powershell", "pwsh"):
        if shutil.which(executable):
            return executable
    return None


class PowerShellScriptsParseTest(unittest.TestCase):
    def test_every_operational_script_parses_on_the_deployment_host(self):
        host = _host()
        if host is None:
            self.skipTest("no PowerShell host available")
        self.assertTrue(SCRIPTS, "no PowerShell scripts were discovered")

        for script in SCRIPTS:
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [
                        host,
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        PARSE_SNIPPET.replace("__PATH__", script.as_posix()),
                    ],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{script.name} does not parse under {host}:\n{result.stdout}{result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
