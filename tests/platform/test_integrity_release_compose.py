import json
import os
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "compose" / "compose.production.yaml"
VALIDATOR = ROOT / "infra" / "scripts" / "validate_compose_contract.py"
DIGEST = "sha256:" + ("a" * 64)


def _render_production() -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "WEB_IMAGE": f"splitbind-web@{DIGEST}",
            "API_IMAGE": f"splitbind-api@{DIGEST}",
            "SPLITBIND_HOSTNAME": "splitbind.example.invalid",
            "ACME_EMAIL": "operator@example.invalid",
            "NEON_DATABASE_HOST": "ep-release.neon.tech.invalid",
            "R2_ENDPOINT": "https://release.r2.cloudflarestorage.com.invalid",
            "API_ENV_FILE": "./config-test-api.env",
            "WORKER_ENV_FILE": "./config-test-worker.env",
            "MANIFEST_SIGNING_KEY_FILE": "./config-test-secret.bin",
            "MANIFEST_SIGNING_KEY_PASSPHRASE_FILE": "./config-test-secret.bin",
        }
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "config",
            "--format",
            "json",
            "--no-env-resolution",
            "--no-path-resolution",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _published_ports(service: dict) -> set[int]:
    return {int(item["published"]) for item in service.get("ports", [])}


def _secret_sources(service: dict) -> set[str]:
    return {
        item if isinstance(item, str) else item["source"]
        for item in service.get("secrets", [])
    }


def test_integrity_release_has_one_hardened_public_edge():
    rendered = _render_production()
    services = rendered["services"]

    assert set(services) == {"caddy", "api", "worker"}
    assert _published_ports(services["caddy"]) == {80, 443}
    assert not _published_ports(services["api"])
    assert not _published_ports(services["worker"])
    for name in ("api", "worker"):
        service = services[name]
        assert re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", service["user"])
        assert service["read_only"] is True
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["cap_drop"] == ["ALL"]
        assert service["tmpfs"]
        assert service["healthcheck"]["test"]
    assert services["worker"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_integrity_release_is_bounded_and_worker_alone_owns_signing_key():
    services = _render_production()["services"]

    assert services["worker"]["environment"]["WORKER_CONCURRENCY"] == "1"
    assert services["worker"]["environment"]["SPLITBIND_RELEASE_MODE"] == "integrity_v1"
    assert _secret_sources(services["worker"]) == {
        "manifest_signing_key",
        "manifest_signing_key_passphrase",
    }
    assert services["worker"]["environment"][
        "SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE"
    ] == "/run/secrets/manifest_signing_key_passphrase"
    assert "\n        mode:" not in COMPOSE.read_text(encoding="utf-8")
    assert not _secret_sources(services["api"])
    assert not _secret_sources(services["caddy"])
    assert sum(int(service["mem_limit"]) for service in services.values()) <= 3 * 1024**3


def test_integrity_release_uses_only_immutable_runtime_images():
    services = _render_production()["services"]
    immutable = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")

    assert all(immutable.fullmatch(service["image"]) for service in services.values())
    assert services["worker"]["image"] == services["api"]["image"]


def test_container_builds_use_verified_immutable_digest_bases():
    api = (ROOT / "infra" / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "infra" / "docker" / "web.Dockerfile").read_text(encoding="utf-8")

    assert re.search(r"ARG PYTHON_BASE_IMAGE=[^\s]+@sha256:[0-9a-f]{64}$", api, re.MULTILINE)
    assert "FROM ${PYTHON_BASE_IMAGE}" in api
    assert re.search(r"ARG NODE_BASE_IMAGE=[^\s]+@sha256:[0-9a-f]{64}$", web, re.MULTILINE)
    assert re.search(r"ARG CADDY_BASE_IMAGE=[^\s]+@sha256:[0-9a-f]{64}$", web, re.MULTILINE)
    assert "FROM ${NODE_BASE_IMAGE}" in web
    assert "FROM ${CADDY_BASE_IMAGE}" in web
    assert api.index("ARG PYTHON_BASE_IMAGE=") < api.index("FROM ")
    first_web_from = web.index("FROM ")
    assert web.index("ARG NODE_BASE_IMAGE=") < first_web_from
    assert web.index("ARG CADDY_BASE_IMAGE=") < first_web_from
    assert web.index("npm install --global npm@12.0.1") < web.index("npm ci --ignore-scripts")
    assert not re.search(r"^FROM\s+\S+:[^@\s]+", api + "\n" + web, re.MULTILINE)


def test_compose_contract_validator_accepts_the_release_file():
    environment = os.environ.copy()
    environment.update(
        {
            "WEB_IMAGE": f"splitbind-web@{DIGEST}",
            "API_IMAGE": f"splitbind-api@{DIGEST}",
            "SPLITBIND_HOSTNAME": "splitbind.example.invalid",
            "ACME_EMAIL": "operator@example.invalid",
            "NEON_DATABASE_HOST": "ep-release.neon.tech.invalid",
            "R2_ENDPOINT": "https://release.r2.cloudflarestorage.com.invalid",
            "API_ENV_FILE": "./config-test-api.env",
            "WORKER_ENV_FILE": "./config-test-worker.env",
            "MANIFEST_SIGNING_KEY_FILE": "./config-test-secret.bin",
            "MANIFEST_SIGNING_KEY_PASSPHRASE_FILE": "./config-test-secret.bin",
        }
    )
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["service_count"] == 3


def test_api_startup_never_runs_schema_migrations():
    entrypoint = (ROOT / "infra" / "docker" / "api-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    migration_entrypoint = (
        ROOT / "infra" / "docker" / "migration-entrypoint.sh"
    ).read_text(encoding="utf-8")
    dockerfile = (ROOT / "infra" / "docker" / "api.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "manage.py migrate" not in entrypoint
    assert "exec python manage.py migrate --noinput" in migration_entrypoint
    assert "migration-entrypoint.sh" in dockerfile


def test_production_compose_never_overlays_image_content_with_host_files():
    rendered = _render_production()
    for name, service in rendered["services"].items():
        for volume in service.get("volumes", []):
            assert volume.get("type") != "bind", (
                f"{name} bind-mounts {volume.get('source')} over {volume.get('target')}; "
                "the image digest must be the only source of application code"
            )


def test_validator_rejects_a_host_file_mounted_over_application_code():
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_compose_contract", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rendered = _render_production()
    rendered["services"]["api"]["volumes"] = [
        {
            "type": "bind",
            "source": "/home/operator/patches/settings_common.py",
            "target": "/app/services/api/config/settings_common.py",
            "read_only": True,
        }
    ]

    try:
        module.validate_contract(rendered)
    except module.ComposeContractError as error:
        assert "bind-mount" in str(error)
    else:
        raise AssertionError("a host file mounted over /app must fail the contract")
