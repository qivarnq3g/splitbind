"""Render and validate the Integrity Release 0.1 production Compose contract."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "compose" / "compose.production.yaml"
COMPOSE_DIR = COMPOSE.parent
IMMUTABLE_IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
MAX_MEMORY = 3 * 1024**3


class ComposeContractError(ValueError):
    pass


def _render() -> dict:
    environment = os.environ.copy()
    synthetic_digest = "sha256:" + ("a" * 64)
    defaults = {
        "WEB_IMAGE": f"splitbind-web@{synthetic_digest}",
        "API_IMAGE": f"splitbind-api@{synthetic_digest}",
        "SPLITBIND_HOSTNAME": "splitbind.example.invalid",
        "ACME_EMAIL": "operator@example.invalid",
        "NEON_DATABASE_HOST": "ep-release.neon.tech.invalid",
        "R2_ENDPOINT": "https://release.r2.cloudflarestorage.com.invalid",
        "API_ENV_FILE": "./config-test-api.env",
        "WORKER_ENV_FILE": "./config-test-worker.env",
        "MANIFEST_SIGNING_KEY_FILE": "./config-test-secret.bin",
        "MANIFEST_SIGNING_KEY_PASSPHRASE_FILE": "./config-test-secret.bin",
    }
    for name, value in defaults.items():
        environment.setdefault(name, value)
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
    if result.returncode != 0:
        raise ComposeContractError(f"compose render failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _secret_sources(service: dict) -> set[str]:
    return {
        item if isinstance(item, str) else item["source"]
        for item in service.get("secrets", [])
    }


def _published_ports(service: dict) -> set[int]:
    return {int(item["published"]) for item in service.get("ports", [])}


def validate_contract(rendered: dict) -> dict[str, object]:
    services = rendered.get("services", {})
    if set(services) != {"caddy", "api", "worker"}:
        raise ComposeContractError("services must be exactly caddy, api, and worker")
    if _published_ports(services["caddy"]) != {80, 443}:
        raise ComposeContractError("caddy must publish exactly ports 80 and 443")
    if any(_published_ports(services[name]) for name in ("api", "worker")):
        raise ComposeContractError("api and worker must not publish host ports")
    if any(not IMMUTABLE_IMAGE.fullmatch(service.get("image", "")) for service in services.values()):
        raise ComposeContractError("every runtime image must use an immutable sha256 digest")
    if services["worker"]["image"] != services["api"]["image"]:
        raise ComposeContractError("worker must reuse the API image")

    for name in ("api", "worker"):
        service = services[name]
        if re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", str(service.get("user", ""))) is None:
            raise ComposeContractError(f"{name} must use a numeric non-root uid and gid")
        if service.get("read_only") is not True:
            raise ComposeContractError(f"{name} root filesystem must be read-only")
        if service.get("cap_drop") != ["ALL"]:
            raise ComposeContractError(f"{name} must drop every Linux capability")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            raise ComposeContractError(f"{name} must disable privilege escalation")
        if not service.get("tmpfs") or not service.get("healthcheck", {}).get("test"):
            raise ComposeContractError(f"{name} must define tmpfs and a healthcheck")

    worker_environment = services["worker"].get("environment", {})
    if worker_environment.get("WORKER_CONCURRENCY") != "1":
        raise ComposeContractError("worker concurrency must be exactly one")
    if worker_environment.get("SPLITBIND_RELEASE_MODE") != "integrity_v1":
        raise ComposeContractError("worker must run only integrity_v1")
    if _secret_sources(services["worker"]) != {
        "manifest_signing_key",
        "manifest_signing_key_passphrase",
    }:
        raise ComposeContractError(
            "worker must receive only the encrypted signing key and passphrase"
        )
    if _secret_sources(services["api"]) or _secret_sources(services["caddy"]):
        raise ComposeContractError("signing material must not be mounted outside the worker")
    memory = sum(int(service.get("mem_limit", 0)) for service in services.values())
    if memory <= 0 or memory > MAX_MEMORY:
        raise ComposeContractError("aggregate container memory must be in (0, 3 GiB]")
    return {
        "schema_version": 1,
        "service_count": len(services),
        "public_ports": [80, 443],
        "memory_limit_bytes": memory,
        "worker_concurrency": 1,
    }


def main() -> int:
    try:
        result = validate_contract(_render())
    except (ComposeContractError, OSError, json.JSONDecodeError) as error:
        print(f"COMPOSE_CONTRACT_INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
