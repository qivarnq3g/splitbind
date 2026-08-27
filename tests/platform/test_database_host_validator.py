import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "infra" / "scripts" / "validate_database_host.py"
SYNTHETIC_HOST = "ep-synthetic.neon.tech.invalid"
SYNTHETIC_SUFFIX = ".neon.tech.invalid"


def run_validator(host):
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--database-host",
            host,
            "--required-suffix",
            SYNTHETIC_SUFFIX,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class DatabaseHostValidatorTest(unittest.TestCase):
    def test_accepts_a_host_only_synthetic_neon_authority(self):
        result = run_validator(SYNTHETIC_HOST)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "schema_version": 1,
                "database_host": SYNTHETIC_HOST,
                "required_suffix": SYNTHETIC_SUFFIX,
            },
        )

    def test_rejects_credentials_and_every_non_host_authority_component(self):
        invalid_hosts = (
            "user:password@ep-synthetic.neon.tech.invalid",
            "ep-synthetic.neon.tech.invalid:5432",
            "ep-synthetic.neon.tech.invalid/database",
            "ep-synthetic.neon.tech.invalid?sslmode=require",
            "ep-synthetic.neon.tech.invalid#fragment",
            "https://ep-synthetic.neon.tech.invalid",
            " ep-synthetic.neon.tech.invalid",
            "ep-synthetic.neon.tech.invalid\t",
            "ep-synthetic.neon.tech.invalid\x01",
            "ep-synthetic.neon.tech.invalid\x7f",
            "ep_synthetic.neon.tech.invalid",
            "EP-SYNTHETIC.neon.tech.invalid",
        )
        for host in invalid_hosts:
            with self.subTest(host=repr(host)):
                result = run_validator(host)
                self.assertEqual(result.returncode, 1)
                self.assertIn("DATABASE_HOST_INVALID", result.stderr)
                if "@" in host:
                    self.assertNotIn(host, result.stderr)
                    self.assertNotIn("password", result.stderr.lower())

    def test_rejects_a_safe_dns_host_outside_the_required_suffix(self):
        result = run_validator("database.example.invalid")

        self.assertEqual(result.returncode, 1)
        self.assertIn("DATABASE_HOST_INVALID", result.stderr)
        self.assertIn(SYNTHETIC_SUFFIX, result.stderr)


if __name__ == "__main__":
    unittest.main()
