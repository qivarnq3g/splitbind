import json
import os
import pathlib
import re
import subprocess
import unittest
import urllib.parse

from infra.scripts.validate_database_host import (
    DatabaseHostValidationError,
    validate_database_host,
)


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_DIR = ROOT / "infra" / "compose"
CONFIG_TEST_ENV = COMPOSE_DIR / "config-test.env"


def render_compose(
    filename,
    *profiles,
    use_config_env=True,
    environment_overrides=None,
):
    compose_file = COMPOSE_DIR / filename
    compose_file.read_text(encoding="utf-8")
    command = ["docker", "compose"]
    if use_config_env:
        command.extend(["--env-file", str(CONFIG_TEST_ENV)])
    command.extend(["-f", str(compose_file)])
    for profile in profiles:
        command.extend(["--profile", profile])
    command.extend(
        [
            "config",
            "--format",
            "json",
            "--no-env-resolution",
            "--no-path-resolution",
        ]
    )
    environment = os.environ.copy()
    if not use_config_env:
        environment.update(
            {
                "WEB_IMAGE": "splitbind-web:local",
                "API_IMAGE": "splitbind-api:local",
                "WORKER_IMAGE": "splitbind-worker:local",
                "RABBITMQ_IMAGE": "rabbitmq:4.1.4-management-alpine",
                "SPLITBIND_HOSTNAME": "http://localhost:8080",
                "ACME_EMAIL": "compose-test@example.invalid",
                "NEON_DATABASE_HOST": "ep-synthetic.neon.tech.invalid",
                "R2_ENDPOINT": "https://synthetic-account.r2.cloudflarestorage.com.invalid",
            }
        )
    environment.update(environment_overrides or {})
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Compose render failed for {filename}:\n{result.stdout}\n{result.stderr}"
        )
    return json.loads(result.stdout)


def published_ports(service):
    return {int(port["published"]) for port in service.get("ports", [])}


def secret_sources(service):
    return {
        item if isinstance(item, str) else item["source"]
        for item in service.get("secrets", [])
    }


def read_env_keys(filename):
    return {
        line.split("=", 1)[0]
        for line in (COMPOSE_DIR / filename).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }


class ComposeTopologyTest(unittest.TestCase):
    def test_api_and_worker_env_files_supply_the_storage_adapter_contract(self):
        required = {
            "OBJECT_STORAGE_ENDPOINT",
            "OBJECT_STORAGE_BUCKET",
            "OBJECT_STORAGE_ACCESS_KEY",
            "OBJECT_STORAGE_SECRET_KEY",
        }
        self.assertTrue(required <= read_env_keys("config-test-api.env"))
        self.assertTrue(required <= read_env_keys("config-test-worker.env"))

    def test_local_profiles_render_the_intended_service_boundaries(self):
        core = render_compose("compose.local.yaml", "core")
        research = render_compose("compose.local.yaml", "research")
        observability = render_compose("compose.local.yaml", "observability")
        full = render_compose("compose.local.yaml", "full")

        self.assertEqual(
            set(core["services"]),
            {"caddy", "api", "outbox", "rabbitmq", "worker", "postgres", "minio"},
        )
        self.assertEqual(set(research["services"]), {"research"})
        self.assertEqual(set(observability["services"]), {"prometheus"})
        self.assertEqual(
            set(full["services"]),
            {
                "caddy",
                "api",
                "outbox",
                "rabbitmq",
                "worker",
                "postgres",
                "minio",
                "research",
                "prometheus",
                "e2e",
            },
        )
        self.assertEqual(published_ports(core["services"]["caddy"]), {8080})
        self.assertTrue(
            all(
                not published_ports(service)
                for name, service in core["services"].items()
                if name != "caddy"
            )
        )

    def test_offline_topology_is_pull_free_digest_pinned_and_internal(self):
        offline = render_compose("compose.offline.yaml")
        self.assertEqual(
            set(offline["services"]),
            {"caddy", "api", "outbox", "rabbitmq", "worker", "postgres", "minio"},
        )
        digest_reference = re.compile(r"@sha256:[0-9a-f]{64}$")
        for service in offline["services"].values():
            self.assertEqual(service.get("pull_policy"), "never")
            self.assertRegex(service["image"], digest_reference)
        self.assertTrue(offline["networks"]["app"]["internal"])
        self.assertEqual(published_ports(offline["services"]["caddy"]), {8080})
        self.assertTrue(
            all(
                not published_ports(service)
                for name, service in offline["services"].items()
                if name != "caddy"
            )
        )
        serialized = json.dumps(offline).lower()
        for external_dependency in (
            "keyvault.azure.net",
            "neon.tech",
            "r2.cloudflarestorage.com",
            "splitbind.qivarn.id.vn",
        ):
            self.assertNotIn(external_dependency, serialized)

    def test_production_service_ports_and_secret_ownership_are_fail_closed(self):
        production = render_compose("compose.production.yaml", use_config_env=False)
        self.assertEqual(
            set(production["services"]),
            {"caddy", "api", "outbox", "rabbitmq", "worker"},
        )
        self.assertEqual(
            production["services"]["caddy"]["ports"],
            [
                {
                    "mode": "ingress",
                    "target": 8080,
                    "published": "80",
                    "protocol": "tcp",
                },
                {
                    "mode": "ingress",
                    "target": 8443,
                    "published": "443",
                    "protocol": "tcp",
                },
            ],
        )
        for name in ("api", "outbox", "rabbitmq", "worker"):
            self.assertNotIn("ports", production["services"][name])
        self.assertEqual(
            secret_sources(production["services"]["worker"]),
            {"manifest_signing_key", "fingerprint_key", "integrity_key"},
        )
        for name in ("caddy", "api", "outbox", "rabbitmq"):
            self.assertFalse(secret_sources(production["services"][name]))
        self.assertEqual(
            {name: definition["file"] for name, definition in production["secrets"].items()},
            {
                "manifest_signing_key": "/run/splitbind/secrets/manifest-signing-key.pk8",
                "fingerprint_key": "/run/splitbind/secrets/fingerprint-key.bin",
                "integrity_key": "/run/splitbind/secrets/integrity-key.bin",
            },
        )
        for item in production["services"]["worker"]["secrets"]:
            self.assertEqual(item["target"], f"/run/secrets/{item['source']}")

    def test_production_renders_non_secret_neon_and_r2_boundaries(self):
        production = render_compose("compose.production.yaml")

        database_host = production["services"]["api"].get("environment", {}).get(
            "SPLITBIND_DATABASE_HOST"
        )
        self.assertIsNotNone(database_host)
        self.assertEqual(
            production["services"]["outbox"]["environment"][
                "SPLITBIND_DATABASE_HOST"
            ],
            database_host,
        )
        self.assertEqual(
            validate_database_host(database_host, ".neon.tech.invalid"),
            database_host,
        )
        for name in ("api", "outbox"):
            self.assertIn("env_file", production["services"][name])
            self.assertNotIn(
                "DATABASE_URL",
                production["services"][name].get("environment", {}),
            )

        storage_endpoint = production["services"]["api"].get("environment", {}).get(
            "OBJECT_STORAGE_ENDPOINT"
        )
        self.assertIsNotNone(storage_endpoint)
        self.assertEqual(
            production["services"]["worker"]["environment"][
                "OBJECT_STORAGE_ENDPOINT"
            ],
            storage_endpoint,
        )
        parsed_storage = urllib.parse.urlsplit(storage_endpoint)
        self.assertEqual(parsed_storage.scheme, "https")
        self.assertIsNone(parsed_storage.username)
        self.assertIsNone(parsed_storage.password)
        self.assertTrue(
            (parsed_storage.hostname or "").endswith(
                ".r2.cloudflarestorage.com.invalid"
            )
        )
        self.assertNotIn("minio", parsed_storage.hostname or "")
        self.assertNotIn("localhost", parsed_storage.hostname or "")
        self.assertNotIn(
            "OBJECT_STORAGE_ENDPOINT",
            production["services"]["outbox"].get("environment", {}),
        )

    def test_rendered_production_rejects_a_credential_bearing_database_host(self):
        production = render_compose(
            "compose.production.yaml",
            use_config_env=False,
            environment_overrides={
                "NEON_DATABASE_HOST": (
                    "user:password@ep-synthetic.neon.tech.invalid"
                )
            },
        )
        database_host = production["services"]["api"]["environment"][
            "SPLITBIND_DATABASE_HOST"
        ]

        with self.assertRaisesRegex(
            DatabaseHostValidationError,
            "must not contain credentials",
        ):
            validate_database_host(database_host, ".neon.tech.invalid")


if __name__ == "__main__":
    unittest.main()
