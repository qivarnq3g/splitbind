import json
import os
import pathlib
import shutil
import subprocess
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
        self.assertIn(
            "test_repository_contract.py",
            (ROOT / ".github/workflows/smoke.yaml").read_text(encoding="utf-8"),
        )

        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["name"], "splitbind")
        self.assertEqual(lock["lockfileVersion"], 3)
        self.assertEqual(lock["packages"][""]["workspaces"], ["apps/*"])

    def test_default_toolchain_check_does_not_require_release_tools_or_docker_daemon(self):
        result, docker_was_invoked = self._run_toolchain()

        self.assertEqual(result.returncode, 0, self._combined_output(result))
        self.assertIn("TOOLCHAIN_OK", result.stdout)
        self.assertFalse(docker_was_invoked)

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

    @staticmethod
    def _combined_output(result):
        return f"{result.stdout}\n{result.stderr}"

    def _run_toolchain(
        self,
        *,
        release_tools=False,
        present_release_tools=frozenset(),
        omitted=frozenset(),
        versions=None,
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

        with tempfile.TemporaryDirectory(prefix="splitbind-toolchain-test-") as temp:
            fake_bin = pathlib.Path(temp)
            docker_sentinel = fake_bin / "docker-invoked"
            for name, version in tool_versions.items():
                if name not in omitted:
                    self._write_fake_tool(fake_bin, name, f"echo {version}")
            self._write_fake_tool(
                fake_bin,
                "docker",
                'echo invoked > "$TOOLCHAIN_DOCKER_SENTINEL"',
            )
            for name in ("gh", "az"):
                if name in present_release_tools:
                    self._write_fake_tool(fake_bin, name, "exit 0")

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
    def _write_fake_tool(directory, name, body):
        if os.name == "nt":
            path = directory / f"{name}.cmd"
            normalized_body = body.replace(
                "$TOOLCHAIN_DOCKER_SENTINEL",
                "%TOOLCHAIN_DOCKER_SENTINEL%",
            )
            path.write_text(
                f"@echo off\r\n{normalized_body}\r\n",
                encoding="utf-8",
            )
        else:
            path = directory / name
            path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
            path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
