import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from splitbind_ref import contracts
from splitbind_ref.payload import PayloadDecode, decode_payload, encode_payload, verify_crc


ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
GOLDEN_PAYLOAD = bytes.fromhex(
    "534201123456781234567812345678123456789ae24281"
)
ROOT = Path(__file__).resolve().parents[4]
PYTHON_PROJECT = ROOT / "research" / "python"
CONSTRAINTS = PYTHON_PROJECT / "constraints-py311.txt"


def test_payload_has_stable_network_byte_order():
    value = encode_payload(ISSUANCE_ID, 1)

    assert value[:19].hex() == "53420112345678123456781234567812345678"
    assert value == GOLDEN_PAYLOAD
    assert len(value) == 23


def test_decode_payload_recovers_version_and_issuance_identifier():
    assert decode_payload(GOLDEN_PAYLOAD) == PayloadDecode(
        issuance_id=ISSUANCE_ID,
        version=1,
    )


def test_crc_rejects_a_corrupted_payload():
    corrupted = bytearray(GOLDEN_PAYLOAD)
    corrupted[8] ^= 0x01

    assert verify_crc(GOLDEN_PAYLOAD) is True
    assert verify_crc(bytes(corrupted)) is False
    with pytest.raises(ValueError, match="CRC"):
        decode_payload(bytes(corrupted))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (GOLDEN_PAYLOAD[:-1], "length"),
        (b"XX" + GOLDEN_PAYLOAD[2:], "magic"),
        (GOLDEN_PAYLOAD[:2] + b"\x02" + GOLDEN_PAYLOAD[3:], "version"),
    ],
)
def test_decode_payload_rejects_values_outside_the_frozen_contract(value, message):
    with pytest.raises(ValueError, match=message):
        decode_payload(value)


def test_encode_payload_rejects_an_unsupported_version():
    with pytest.raises(ValueError, match="version"):
        encode_payload(ISSUANCE_ID, version=2)


def test_contract_loader_honors_an_explicit_shared_contract_root(tmp_path, monkeypatch):
    shared_root = tmp_path / "shared-algorithm-contracts"
    shared_root.mkdir()
    expected = {"source": "explicit-contract-root"}
    (shared_root / "payload-profile.v1.json").write_text(
        json.dumps(expected), encoding="utf-8"
    )
    monkeypatch.setenv("SPLITBIND_ALGORITHM_CONTRACTS", str(shared_root))

    assert contracts._load_algorithm_contract("payload-profile.v1.json") == expected


def test_contract_loader_reports_how_to_fix_an_invalid_explicit_root(tmp_path, monkeypatch):
    missing_root = tmp_path / "missing-algorithm-contracts"
    monkeypatch.setenv("SPLITBIND_ALGORITHM_CONTRACTS", str(missing_root))

    with pytest.raises(
        RuntimeError,
        match=r"SPLITBIND_ALGORITHM_CONTRACTS.*missing-algorithm-contracts",
    ):
        contracts._load_algorithm_contract("payload-profile.v1.json")


def test_non_editable_wheel_uses_locked_dependencies_and_shared_contracts(tmp_path):
    package_source = tmp_path / "package-source"
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "installed"
    run_directory = tmp_path / "outside-checkout"
    wheelhouse.mkdir()
    run_directory.mkdir()
    shutil.copytree(PYTHON_PROJECT / "src", package_source / "src")
    shutil.copy2(PYTHON_PROJECT / "pyproject.toml", package_source / "pyproject.toml")

    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
            str(package_source),
        ],
        cwd=run_directory,
        text=True,
        capture_output=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(wheelhouse.glob("splitbind_ref-*.whl"))

    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--target",
            str(target),
            "--constraint",
            str(CONSTRAINTS),
            f"{wheel}[test]",
        ],
        cwd=run_directory,
        text=True,
        capture_output=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    script = """
from pathlib import Path
from uuid import UUID
import splitbind_ref.payload as payload

print(Path(payload.__file__).resolve())
print(payload.encode_payload(UUID('12345678-1234-5678-1234-567812345678')).hex())
"""
    isolated_environment = os.environ.copy()
    isolated_environment["PYTHONPATH"] = str(target)
    isolated_environment.pop("SPLITBIND_ALGORITHM_CONTRACTS", None)
    without_contracts = subprocess.run(
        [sys.executable, "-s", "-c", script],
        cwd=run_directory,
        env=isolated_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert without_contracts.returncode != 0
    assert "SPLITBIND_ALGORITHM_CONTRACTS" in without_contracts.stderr

    isolated_environment["SPLITBIND_ALGORITHM_CONTRACTS"] = str(
        ROOT / "contracts" / "algorithm"
    )
    with_contracts = subprocess.run(
        [sys.executable, "-s", "-c", script],
        cwd=run_directory,
        env=isolated_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert with_contracts.returncode == 0, with_contracts.stderr
    module_path, payload_hex = with_contracts.stdout.splitlines()
    assert Path(module_path).is_relative_to(target)
    assert payload_hex == GOLDEN_PAYLOAD.hex()
