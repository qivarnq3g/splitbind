import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class RepositoryContractTest(unittest.TestCase):
    def test_root_toolchains_and_npm_workspace_are_pinned(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertTrue(package["private"])
        self.assertEqual(package["workspaces"], ["apps/*"])
        self.assertEqual(
            package["engines"],
            {"node": ">=24.18.0 <25", "npm": ">=12 <13"},
        )
        self.assertEqual(package.get("packageManager"), "npm@12.0.1")
        self.assertEqual(
            package["scripts"],
            {
                "format:check": "npm run format:check --workspaces --if-present",
                "lint": "npm run lint --workspaces --if-present",
                "typecheck": "npm run typecheck --workspaces --if-present",
                "test": "npm run test --workspaces --if-present",
                "generate:api": "npm run generate:api --workspace @splitbind/web",
            },
        )
        self.assertEqual((ROOT / ".nvmrc").read_text().strip(), "24.18.0")
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.11.9")
        with (ROOT / "rust-toolchain.toml").open("rb") as rust_file:
            rust = tomllib.load(rust_file)
        self.assertEqual(
            rust["toolchain"],
            {
                "channel": "1.97.1",
                "components": ["clippy", "rustfmt"],
                "profile": "minimal",
            },
        )
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["name"], "splitbind")
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"][""]["workspaces"], ["apps/*"])

    def test_smoke_dry_run_publishes_the_exact_reproducible_command_plan(self):
        result = subprocess.run(
            [sys.executable, "infra/scripts/run_smoke.py", "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertEqual(
            json.loads(result.stdout),
            {
                "schema_version": 1,
                "commands": [
                    {
                        "name": "npm-ci",
                        "argv": ["npm", "ci", "--ignore-scripts"],
                    },
                    {
                        "name": "python-environment",
                        "argv": [
                            "{python}",
                            "-m",
                            "pip",
                            "install",
                            "-c",
                            "research/python/constraints-py311.txt",
                            "./research/python[test]",
                        ],
                    },
                    {
                        "name": "api-environment",
                        "argv": [
                            "{python}",
                            "-m",
                            "pip",
                            "install",
                            "-c",
                            "services/api/constraints-py311.txt",
                            "./services/api[test]",
                        ],
                    },
                    {
                        "name": "api-tests",
                        "argv": [
                            "{python}",
                            "-m",
                            "pytest",
                            "services/api/tests",
                            "-v",
                        ],
                    },
                    {
                        "name": "openapi-validate",
                        "argv": [
                            "{python}",
                            "services/api/manage.py",
                            "spectacular",
                            "--format",
                            "openapi-json",
                            "--file",
                            "contracts/openapi/schema.json",
                            "--validate",
                            "--fail-on-warn",
                            "--settings",
                            "config.settings_test",
                        ],
                    },
                    {
                        "name": "web-generate-api",
                        "argv": [
                            "npm",
                            "run",
                            "generate:api",
                            "--workspace",
                            "@splitbind/web",
                        ],
                    },
                    {
                        "name": "contract-drift",
                        "argv": [
                            "git",
                            "diff",
                            "--exit-code",
                            "--",
                            "contracts/openapi/schema.json",
                            "apps/web/src/api/generated/schema.d.ts",
                        ],
                    },
                    {
                        "name": "web-tests",
                        "argv": ["npm", "test", "--workspace", "@splitbind/web"],
                    },
                    {
                        "name": "web-typecheck",
                        "argv": [
                            "npm",
                            "run",
                            "typecheck",
                            "--workspace",
                            "@splitbind/web",
                        ],
                    },
                    {
                        "name": "platform-tests",
                        "argv": [
                            "{python}",
                            "-m",
                            "unittest",
                            "discover",
                            "-s",
                            "tests/platform",
                            "-p",
                            "test_*.py",
                            "-v",
                        ],
                    },
                    {
                        "name": "research-tests",
                        "argv": [
                            "{python}",
                            "-m",
                            "pytest",
                            "research/python/tests",
                            "-v",
                        ],
                    },
                ],
            },
        )

    def test_ci_invokes_the_shared_smoke_plan(self):
        workflow = (ROOT / ".github/workflows/smoke.yaml").read_text(encoding="utf-8")

        self.assertIn("run: python infra/scripts/run_smoke.py --release", workflow)
        self.assertNotIn("run_smoke.py --dry-run", workflow)

    def test_release_smoke_excludes_unreleased_research_benchmarks(self):
        result = subprocess.run(
            [
                sys.executable,
                "infra/scripts/run_smoke.py",
                "--dry-run",
                "--release",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        names = [command["name"] for command in json.loads(result.stdout)["commands"]]
        self.assertIn("api-tests", names)
        self.assertIn("web-tests", names)
        self.assertIn("platform-tests", names)
        self.assertNotIn("research-tests", names)

    def test_smoke_runner_propagates_the_first_failure_and_stops(self):
        program = """
import pathlib
import sys

from infra.scripts import run_smoke

sentinel = pathlib.Path(sys.argv[1])
commands = [
    {
        "name": "first-failure",
        "argv": [sys.executable, "-c", "import sys; sys.exit(7)"],
    },
    {
        "name": "must-not-run",
        "argv": [
            sys.executable,
            "-c",
            "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('ran')",
            str(sentinel),
        ],
    },
]
exit_code = run_smoke.run_commands(commands)
raise SystemExit(0 if exit_code == 7 and not sentinel.exists() else 1)
"""
        with tempfile.TemporaryDirectory(prefix="splitbind-smoke-runner-test-") as temp:
            sentinel = pathlib.Path(temp) / "second-command-ran"
            result = subprocess.run(
                [sys.executable, "-c", program, str(sentinel)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, self._combined_output(result))

    def test_smoke_runner_resolves_platform_command_shims(self):
        program = """
from infra.scripts import run_smoke

raise SystemExit(
    run_smoke.run_commands(
        [{"name": "npm-version", "argv": ["npm", "--version"]}]
    )
)
"""
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, self._combined_output(result))

    def test_default_toolchain_check_does_not_require_release_tools_or_docker_daemon(self):
        result, docker_was_invoked = self._run_toolchain()

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertIn("TOOLCHAIN_OK", result.stdout)
        self.assertFalse(docker_was_invoked)

    def test_posix_fake_tool_emits_version_text_with_shell_metacharacters(self):
        posix_shell = self._find_posix_shell()
        if posix_shell is None:
            self.skipTest("A POSIX shell is unavailable")

        with tempfile.TemporaryDirectory(prefix="splitbind-posix-tool-test-") as temp:
            tool = self._write_fake_tool(
                pathlib.Path(temp),
                "rustc",
                output="rustc 1.97.1 (test fixture)",
                platform="posix",
            )
            result = subprocess.run(
                [posix_shell, str(tool), "--version"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertEqual(result.stdout.strip(), "rustc 1.97.1 (test fixture)")

    def test_release_toolchain_check_requires_github_and_azure_clis(self):
        cases = (({"az"}, "gh"), ({"gh"}, "az"))
        for present_tools, missing_tool in cases:
            with self.subTest(missing_tool=missing_tool):
                result, _ = self._run_toolchain(
                    release_tools=True,
                    present_release_tools=present_tools,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"MISSING_RELEASE_TOOL:{missing_tool}",
                    self._combined_output(result),
                )

    def test_release_toolchain_check_accepts_present_release_clis(self):
        result, _ = self._run_toolchain(
            release_tools=True,
            present_release_tools={"gh", "az"},
        )

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertIn("TOOLCHAIN_OK", result.stdout)

    def test_toolchain_check_distinguishes_a_missing_tool_from_a_wrong_version(self):
        missing, _ = self._run_toolchain(omitted={"node"})
        wrong, _ = self._run_toolchain(versions={"node": "v23.0.0"})

        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("MISSING_TOOL:node", self._combined_output(missing))
        self.assertNotEqual(wrong.returncode, 0)
        self.assertIn("TOOL_VERSION:node:v23.0.0", self._combined_output(wrong))

    def test_toolchain_check_rejects_wrong_patch_versions(self):
        cases = (
            ("node", "v24.0.0"),
            ("python", "Python 3.11.0"),
            ("rustc", "rustc 1.97.9 (test fixture)"),
        )
        for name, version in cases:
            with self.subTest(name=name, version=version):
                result, _ = self._run_toolchain(versions={name: version})

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"TOOL_VERSION:{name}:{version}",
                    self._combined_output(result),
                )

    def test_toolchain_check_rejects_correct_output_from_a_failed_probe(self):
        result, _ = self._run_toolchain(exit_codes={"node": 7})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TOOL_EXIT:node:7", self._combined_output(result))

    def test_toolchain_check_ignores_probe_diagnostics_before_version(self):
        result, _ = self._run_toolchain(
            stderr_outputs={
                "rustc": "info: syncing channel updates for 1.97.1-x86_64-unknown-linux-gnu"
            }
        )

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertIn("TOOLCHAIN_OK", result.stdout)

    @staticmethod
    def _combined_output(result):
        return f"{result.stdout}\n{result.stderr}"

    @staticmethod
    def _find_posix_shell():
        candidates = [
            shutil.which("sh"),
            pathlib.Path(os.environ.get("ProgramFiles", "")) / "Git/bin/sh.exe",
        ]
        for candidate in candidates:
            if candidate and pathlib.Path(candidate).is_file():
                return str(candidate)
        return None

    def _run_toolchain(
        self,
        *,
        release_tools=False,
        present_release_tools=frozenset(),
        omitted=frozenset(),
        versions=None,
        exit_codes=None,
        stderr_outputs=None,
    ):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(powershell, "PowerShell is required to exercise the script")
        tool_versions = {
            "node": "v24.18.0",
            "npm": "12.0.1",
            "python": "Python 3.11.9",
            "rustc": "rustc 1.97.1 (test fixture)",
        }
        tool_versions.update(versions or {})
        tool_exit_codes = exit_codes or {}

        with tempfile.TemporaryDirectory(prefix="splitbind-toolchain-test-") as temp:
            fake_bin = pathlib.Path(temp)
            docker_sentinel = fake_bin / "docker-invoked"
            for name, version in tool_versions.items():
                if name not in omitted:
                    self._write_fake_tool(
                        fake_bin,
                        name,
                        output=version,
                        exit_code=tool_exit_codes.get(name, 0),
                        stderr_output=(stderr_outputs or {}).get(name),
                    )
            self._write_fake_tool(
                fake_bin,
                "docker",
                sentinel_env="TOOLCHAIN_DOCKER_SENTINEL",
            )
            for name in ("gh", "az"):
                if name in present_release_tools:
                    self._write_fake_tool(fake_bin, name)

            env = os.environ.copy()
            path_entries = [str(fake_bin)]
            if os.name == "nt":
                path_entries.append(str(pathlib.Path(env["WINDIR"]) / "System32"))
            env["PATH"] = os.pathsep.join(path_entries)
            env["TOOLCHAIN_DOCKER_SENTINEL"] = str(docker_sentinel)
            command = [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "infra/scripts/verify-toolchain.ps1"),
            ]
            if release_tools:
                command.append("-ReleaseTools")
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            docker_was_invoked = docker_sentinel.exists()

        return result, docker_was_invoked

    @staticmethod
    def _write_fake_tool(
        directory,
        name,
        *,
        output=None,
        exit_code=0,
        sentinel_env=None,
        stderr_output=None,
        platform=None,
    ):
        platform = platform or os.name
        if platform == "nt":
            path = directory / f"{name}.cmd"
            lines = ["@echo off"]
            if output is not None:
                lines.append(f"echo {output}")
            if stderr_output is not None:
                lines.append(f"echo {stderr_output} 1>&2")
            if sentinel_env is not None:
                lines.append(f'> "%{sentinel_env}%" echo invoked')
            lines.append(f"exit /b {exit_code}")
            path.write_text(
                "\r\n".join(lines) + "\r\n",
                encoding="utf-8",
            )
        else:
            path = directory / name
            lines = ["#!/bin/sh"]
            if output is not None:
                lines.append(f"printf '%s\\n' {shlex.quote(output)}")
            if stderr_output is not None:
                lines.append(f"printf '%s\\n' {shlex.quote(stderr_output)} >&2")
            if sentinel_env is not None:
                lines.append(f'echo invoked > "${sentinel_env}"')
            lines.append(f"exit {exit_code}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            path.chmod(0o755)
        return path


if __name__ == "__main__":
    unittest.main()
