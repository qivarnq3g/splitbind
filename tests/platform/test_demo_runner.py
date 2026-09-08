import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = ROOT / "infra" / "scripts" / "run_demo.ps1"
COMPOSE = ROOT / "infra" / "compose" / "compose.local.yaml"
CONFIG_ENV = ROOT / "infra" / "compose" / "config-test.env"
VITE_CONFIG = ROOT / "apps" / "web" / "vite.config.ts"
HARNESS = ROOT / "tests" / "platform" / "demo_runner_harness.ps1"
API_PYPROJECT = ROOT / "services" / "api" / "pyproject.toml"
API_CONSTRAINTS = ROOT / "services" / "api" / "constraints-py311.txt"


def run_harness(scenario, scratch, *, dump_environment_script=None):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARNESS),
        "-Runner",
        str(RUNNER),
        "-Scenario",
        scenario,
        "-ScratchRoot",
        str(scratch),
    ]
    if dump_environment_script is not None:
        command.extend(["-DumpEnvironmentScript", str(dump_environment_script)])
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


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
    def setUp(self):
        temporary_parent = ROOT / "tmp"
        temporary_parent.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="demo-runner-", dir=temporary_parent
        )
        self.scratch = pathlib.Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_demo_profile_isolated_to_loopback_minio(self):
        demo = render_compose("demo")

        self.assertEqual(set(demo["services"]), {"minio-demo"})
        service = demo["services"]["minio-demo"]
        self.assertEqual(service.get("pull_policy"), "never")
        self.assertEqual(service["command"], ["server", "/data"])
        self.assertTrue(service["image"].startswith("minio/minio:RELEASE."))
        self.assertEqual(published_ports(service), {9000})
        self.assertEqual(service["ports"][0].get("host_ip"), "127.0.0.1")
        self.assertEqual(
            service["environment"]["MINIO_API_CORS_ALLOW_ORIGIN"],
            "http://127.0.0.1:5173,http://localhost:5173",
        )
        self.assertEqual(len(service.get("volumes", [])), 1)
        self.assertEqual(service["volumes"][0]["type"], "bind")
        self.assertEqual(service["volumes"][0]["target"], "/data")
        self.assertIn("artifacts/demo", service["volumes"][0]["source"].replace("\\", "/"))
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
            "put_bucket_cors",
        ):
            self.assertNotIn(forbidden, source)

    def test_vite_proxies_only_local_api_routes(self):
        source = VITE_CONFIG.read_text(encoding="utf-8")
        self.assertIn('"/api"', source)
        self.assertIn('"/health"', source)
        self.assertGreaterEqual(source.count('target: "http://127.0.0.1:8000"'), 2)
        self.assertNotIn("changeOrigin: true", source)

    def test_runner_starts_vite_from_the_web_application_root(self):
        source = RUNNER.read_text(encoding="utf-8")

        self.assertIn('$WebRoot = Join-Path $RepoRoot "apps\\web"', source)
        self.assertIn('-WorkingDirectory $WebRoot -Environment (Get-ViteChildEnvironment)', source)

    def test_runner_prints_an_exact_stop_command_only_after_readiness(self):
        source = RUNNER.read_text(encoding="utf-8")
        ready_api = source.index('Wait-LocalHttp -Uri "http://127.0.0.1:8000/health/live"')
        ready_web = source.index('Wait-LocalHttp -Uri "http://127.0.0.1:5173"')
        self.assertIn('Write-Output "Browser: http://127.0.0.1:5173"', source)
        browser_output = source.rindex("Write-ReadySummary")
        self.assertIn("infra/scripts/run_demo.ps1 -Stop", source)
        self.assertLess(ready_api, browser_output)
        self.assertLess(ready_web, browser_output)

    def test_readiness_requires_exact_status_and_service_payload(self):
        observed = run_harness("readiness", self.scratch)

        self.assertEqual(
            observed,
            {
                "api_good": True,
                "api_wrong_body": False,
                "api_wrong_status": False,
                "vite_good": True,
                "vite_wrong": False,
                "minio_good": True,
                "minio_wrong": False,
            },
        )

    def test_healthy_reuse_requires_minio_and_final_worker_identity(self):
        observed = run_harness("healthy-state", self.scratch)

        self.assertEqual(
            observed,
            {"healthy": True, "worker_dead": False, "minio_missing": False},
        )

    def test_cleanup_is_exhaustive_and_retains_timeout_and_mismatch_state(self):
        observed = run_harness("cleanup", self.scratch)

        self.assertEqual(observed["stop_requests"], [1, 2])
        self.assertEqual(observed["compose_stops"], 1)
        self.assertEqual(observed["retained_pids"], [1, 3])
        self.assertIn("PID 1", observed["error"])
        self.assertIn("PID 3", observed["error"])

    @unittest.skipUnless(os.name == "nt", "Windows Start-Process contract")
    def test_child_process_gets_minimal_environment_without_vite_or_cloud_sentinels(self):
        dump_script = self.scratch / "dump-environment.ps1"
        dump_script.write_text(
            "Get-ChildItem Env: | Sort-Object Name | ForEach-Object { "
            "Write-Output ($_.Name + '=' + $_.Value) }\n",
            encoding="utf-8",
        )

        observed = run_harness(
            "child-environment", self.scratch, dump_environment_script=dump_script
        )

        self.assertTrue(observed["exited"])
        self.assertTrue(observed["has_expected"])
        self.assertFalse(observed["has_vite_secret"])
        self.assertFalse(observed["has_cloud_secret"])

    def test_missing_node_is_actionable_and_does_not_mutate_demo_state(self):
        observed = run_harness("missing-node", self.scratch)

        self.assertIn("Node.js is missing", observed["error"])
        self.assertIn("Node 24", observed["error"])
        self.assertFalse(observed["demo_created"])

    def test_demo_extra_closes_the_reference_fingerprint_runtime_dependency(self):
        with API_PYPROJECT.open("rb") as project_file:
            project = tomllib.load(project_file)

        self.assertIn(
            "reedsolo==1.7.0",
            project["project"]["optional-dependencies"]["demo"],
        )
        self.assertIn(
            "reedsolo==1.7.0",
            API_CONSTRAINTS.read_text(encoding="utf-8").splitlines(),
        )

    def test_python_preflight_imports_the_actual_fingerprint_module(self):
        observed = run_harness("python-dependency-probe", self.scratch)

        self.assertTrue(observed["accepted"])
        self.assertIn("splitbind_ref.fingerprint_v2", observed["arguments"])

    def test_embedded_python_is_sent_over_stdin_without_losing_quotes(self):
        observed = run_harness("python-stdin", self.scratch)

        self.assertEqual(observed, {"exit_code": 0, "output": "NoSuchBucket"})

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point contract")
    def test_reparse_chain_and_leaf_are_rejected_before_external_write(self):
        observed = run_harness("reparse", self.scratch)

        self.assertTrue(observed["junction_rejected"])
        self.assertTrue(observed["leaf_rejected"])
        self.assertTrue(observed["outside_unchanged"])


if __name__ == "__main__":
    unittest.main()
