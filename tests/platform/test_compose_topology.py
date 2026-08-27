import json
import os
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_DIR = ROOT / "infra" / "compose"
CONFIG_TEST_ENV = COMPOSE_DIR / "config-test.env"


def render_compose(filename, *profiles, use_config_env=True):
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
            }
        )
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


class ComposeTopologyTest(unittest.TestCase):
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
        published = {
            port
            for service in production["services"].values()
            for port in published_ports(service)
        }
        self.assertEqual(published, {80, 443})
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

    def test_caddy_is_same_origin_and_does_not_proxy_metrics(self):
        caddy = (ROOT / "infra" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("{$SPLITBIND_HOSTNAME}", caddy)
        self.assertIn("handle /api/*", caddy)
        self.assertIn("handle /health/*", caddy)
        self.assertEqual(caddy.count("reverse_proxy api:8000"), 2)
        self.assertNotIn("/metrics", caddy)


if __name__ == "__main__":
    unittest.main()
