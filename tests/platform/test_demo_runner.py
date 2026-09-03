import json
import os
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "infra" / "scripts" / "run_demo.ps1"
COMPOSE = ROOT / "infra" / "compose" / "compose.local.yaml"
CONFIG_ENV = ROOT / "infra" / "compose" / "config-test.env"
VITE_CONFIG = ROOT / "apps" / "web" / "vite.config.ts"


def render_compose(*profiles):
    command = [
        "docker",
        "compose",
        "--env-file",
        str(CONFIG_ENV),
        "-f",
        str(COMPOSE),
    ]
    for profile in profiles:
        command.extend(["--profile", profile])
    command.extend(["config", "--format", "json", "--no-env-resolution", "--no-path-resolution"])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def published_ports(service):
    return {int(item["published"]) for item in service.get("ports", [])}


class DemoRunnerContractTest(unittest.TestCase):
    def test_demo_profile_isolated_to_loopback_minio(self):
        demo = render_compose("demo")

        self.assertEqual(set(demo["services"]), {"minio-demo"})
        service = demo["services"]["minio-demo"]
        self.assertEqual(service.get("pull_policy"), "never")
        self.assertEqual(service["command"], ["server", "/data"])
        self.assertTrue(service["image"].startswith("minio/minio:RELEASE."))
        self.assertEqual(published_ports(service), {9000})
        self.assertEqual(service["ports"][0].get("host_ip"), "127.0.0.1")
        self.assertNotIn("minio-demo", render_compose("core")["services"])
        self.assertNotIn("minio-demo", render_compose("full")["services"])

    def test_runner_is_valid_powershell_and_has_no_cloud_or_public_actions(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell)
        parser = (
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            "$env:SPLITBIND_PARSE_FILE,[ref]$tokens,[ref]$errors) | Out-Null; "
            "if($errors.Count){$errors | ForEach-Object {$_.Message}; exit 1}"
        )
        environment = os.environ.copy()
        environment["SPLITBIND_PARSE_FILE"] = str(RUNNER)
        parsed = subprocess.run(
            [powershell, "-NoProfile", "-Command", parser],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

        source = RUNNER.read_text(encoding="utf-8").lower()
        for required in (
            "config.settings_demo",
            "splitbind_demo_mode",
            "migrate",
            "seed_demo",
            "run_demo_worker",
            "vite",
            "start-process",
            "starttime",
            "wait-localhttp",
            "test-trackedprocessidentity",
            "rollback-startup",
            "put_bucket_cors",
            "docker image inspect",
            "docker info",
            "--pull never",
            "stop-demo",
            "--project-name",
            "splitbind-demo",
            "127.0.0.1:5173",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "azure",
            "key vault",
            "cloudflare",
            "r2.cloudflarestorage",
            "splitbind.qivarn.id.vn",
            "git push",
            "docker pull",
            "az login",
            "deploy",
        ):
            self.assertNotIn(forbidden, source)

    def test_vite_proxies_only_local_api_routes(self):
        source = VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn('"/api"', source)
        self.assertIn('"/health"', source)
        self.assertGreaterEqual(source.count('target: "http://127.0.0.1:8000"'), 2)
        self.assertNotIn("changeOrigin: true", source)

    def test_runner_prints_an_exact_stop_command_only_after_readiness(self):
        source = RUNNER.read_text(encoding="utf-8")
        ready_api = source.index('Wait-LocalHttp -Uri "http://127.0.0.1:8000/health/live"')
        ready_web = source.index('Wait-LocalHttp -Uri "http://127.0.0.1:5173"')
        self.assertIn('Write-Output "Browser: http://127.0.0.1:5173"', source)
        browser_output = source.rindex("Write-ReadySummary")
        self.assertIn("infra/scripts/run_demo.ps1 -Stop", source)
        self.assertLess(ready_api, browser_output)
        self.assertLess(ready_web, browser_output)


if __name__ == "__main__":
    unittest.main()
