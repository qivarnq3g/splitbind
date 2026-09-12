import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "infra" / "scripts" / "validate_caddyfile.py"
CADDYFILE = ROOT / "infra" / "caddy" / "Caddyfile"


def run_validator(path=CADDYFILE):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--file", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class CaddyfileValidatorTest(unittest.TestCase):
    def test_validator_emits_the_complete_bounded_edge_contract(self):
        result = run_validator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "schema_version": 1,
                "global": {
                    "admin": "off",
                    "http_port": 8080,
                    "https_port": 8443,
                    "email": "{$ACME_EMAIL}",
                },
                "site_label": "{$SPLITBIND_HOSTNAME}",
                "encodings": ["zstd", "gzip"],
                "header_mode": "deferred_set",
                "headers": {
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "same-origin",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                    "Content-Security-Policy": (
                        "default-src 'self'; connect-src 'self' "
                        "https://*.r2.cloudflarestorage.com; font-src 'self' data:; "
                        "img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; "
                        "frame-ancestors 'none'"
                    ),
                    "Alt-Svc": 'h3=":443"; ma=2592000',
                },
                "routes": {
                    "/api/*": {"reverse_proxy": "api:8000"},
                    "/health/*": {"reverse_proxy": "api:8000"},
                },
                "static": {
                    "root": ["*", "/srv/web"],
                    "try_files": ["{path}", "/index.html"],
                    "file_server": True,
                },
            },
        )

    def test_validator_rejects_unknown_public_route_and_unbalanced_structure(self):
        valid = CADDYFILE.read_text(encoding="utf-8")
        mutations = {
            "metrics route": valid.replace(
                "    handle {\n",
                "    handle /metrics {\n"
                "        reverse_proxy api:8000\n"
                "    }\n"
                "    handle {\n",
                1,
            ),
            "unbalanced block": valid.rsplit("}", 1)[0],
            "non-deferred header duplicates the upstream value": valid.replace(
                ">Referrer-Policy", "Referrer-Policy", 1
            ),
            "Alt-Svc left to advertise the internal port": valid.replace(
                '>Alt-Svc "h3=\\":443\\"; ma=2592000"\n', "", 1
            ),
        }
        for name, content in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                candidate = pathlib.Path(temporary) / "Caddyfile"
                candidate.write_text(content, encoding="utf-8")
                result = run_validator(candidate)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CADDYFILE_INVALID", result.stderr)


if __name__ == "__main__":
    unittest.main()
