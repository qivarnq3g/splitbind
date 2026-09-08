import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "infra" / "scripts" / "check_compose_capabilities.py"


class ComposeCapabilitiesTest(unittest.TestCase):
    def test_installed_compose_supports_the_static_renderer_contract(self):
        result = subprocess.run(
            [sys.executable, str(PREFLIGHT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "schema_version": 1,
                "command": ["docker", "compose", "config"],
                "required_options": [
                    "--format",
                    "--no-env-resolution",
                    "--no-path-resolution",
                ],
            },
        )

    def test_preflight_reports_each_missing_capability_with_upgrade_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            help_file = pathlib.Path(temporary) / "compose-config-help.txt"
            help_file.write_text(
                "Usage: docker compose config\n  --format string\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PREFLIGHT), "--help-file", str(help_file)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "COMPOSE_CAPABILITY_MISSING: --no-env-resolution, --no-path-resolution",
            result.stderr,
        )
        self.assertIn("upgrade Docker Compose", result.stderr)


if __name__ == "__main__":
    unittest.main()
