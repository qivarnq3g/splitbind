"""Validate the bounded P2 Caddyfile contract without a Caddy runtime.

This parser intentionally recognizes only the exact SplitBind P2 block shape. P3
must additionally run the official ``caddy validate`` command inside its image.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import shlex
import sys


class CaddyfileValidationError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Directive:
    tokens: tuple[str, ...]
    line: int


@dataclasses.dataclass(frozen=True)
class Block:
    label: tuple[str, ...]
    items: tuple[Directive | "Block", ...]
    line: int


def _tokenize(text: str) -> list[Directive]:
    tokenized = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        try:
            tokens = tuple(shlex.split(line, comments=True, posix=True))
        except ValueError as error:
            raise CaddyfileValidationError(
                f"line {line_number}: invalid quoting: {error}"
            ) from error
        if tokens:
            tokenized.append(Directive(tokens, line_number))
    return tokenized


def _parse_block(lines: list[Directive], index: int) -> tuple[Block, int]:
    opening = lines[index]
    if opening.tokens[-1:] != ("{",):
        raise CaddyfileValidationError(
            f"line {opening.line}: expected a block opening ending in '{{'"
        )
    label = opening.tokens[:-1]
    items: list[Directive | Block] = []
    index += 1
    while index < len(lines):
        current = lines[index]
        if current.tokens == ("}",):
            return Block(label, tuple(items), opening.line), index + 1
        if current.tokens[-1:] == ("{",):
            child, index = _parse_block(lines, index)
            items.append(child)
            continue
        if "{" in current.tokens or "}" in current.tokens:
            raise CaddyfileValidationError(
                f"line {current.line}: brace must delimit a complete block line"
            )
        items.append(current)
        index += 1
    raise CaddyfileValidationError(
        f"line {opening.line}: unclosed block {' '.join(label) or '<global>'}"
    )


def _parse_document(text: str) -> tuple[Block, ...]:
    lines = _tokenize(text)
    blocks = []
    index = 0
    while index < len(lines):
        if lines[index].tokens == ("}",):
            raise CaddyfileValidationError(
                f"line {lines[index].line}: unmatched closing brace"
            )
        block, index = _parse_block(lines, index)
        blocks.append(block)
    return tuple(blocks)


def _directives(
    block: Block,
    expected: tuple[tuple[str, ...], ...],
    name: str,
) -> None:
    if any(not isinstance(item, Directive) for item in block.items):
        raise CaddyfileValidationError(f"{name}: nested block is not allowed")
    actual = tuple(item.tokens for item in block.items if isinstance(item, Directive))
    if actual != expected:
        raise CaddyfileValidationError(
            f"{name}: expected {expected!r}, observed {actual!r}"
        )


def validate_caddyfile(text: str) -> dict[str, object]:
    blocks = _parse_document(text)
    if tuple(block.label for block in blocks) != (
        (),
        ("{$SPLITBIND_HOSTNAME}",),
    ):
        raise CaddyfileValidationError(
            "document must contain exactly the global block and "
            "{$SPLITBIND_HOSTNAME} site block"
        )

    global_block, site = blocks
    global_directives = (
        ("admin", "off"),
        ("http_port", "8080"),
        ("https_port", "8443"),
        ("email", "{$ACME_EMAIL}"),
    )
    _directives(global_block, global_directives, "global block")

    if len(site.items) != 5 or not isinstance(site.items[0], Directive):
        raise CaddyfileValidationError("site block: unexpected directive or block count")
    encode, header, api, health, fallback = site.items
    if encode.tokens != ("encode", "zstd", "gzip"):
        raise CaddyfileValidationError("site block: expected encode zstd gzip")
    nested = (header, api, health, fallback)
    if any(not isinstance(item, Block) for item in nested):
        raise CaddyfileValidationError(
            "site block: all routes and headers must be blocks"
        )
    if tuple(item.label for item in nested if isinstance(item, Block)) != (
        ("header",),
        ("handle", "/api/*"),
        ("handle", "/health/*"),
        ("handle",),
    ):
        raise CaddyfileValidationError(
            "site block: expected header, /api/*, /health/* and default handle blocks"
        )

    assert isinstance(header, Block)
    assert isinstance(api, Block)
    assert isinstance(health, Block)
    assert isinstance(fallback, Block)
    header_directives = (
        (">Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
        (">X-Content-Type-Options", "nosniff"),
        (">Referrer-Policy", "same-origin"),
        (">Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
        (
            ">Content-Security-Policy",
            "default-src 'self'; connect-src 'self' "
            "https://*.r2.cloudflarestorage.com; font-src 'self' data:; "
            "img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'",
        ),
        (">Alt-Svc", 'h3=":443"; ma=2592000'),
    )
    _directives(header, header_directives, "header block")
    route_directives = (("reverse_proxy", "api:8000"),)
    _directives(api, route_directives, "API route")
    _directives(health, route_directives, "health route")
    fallback_directives = (
        ("root", "*", "/srv/web"),
        ("try_files", "{path}", "/index.html"),
        ("file_server",),
    )
    _directives(fallback, fallback_directives, "static fallback")

    return {
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
        "headers": {tokens[0][1:]: tokens[1] for tokens in header_directives},
        "routes": {
            "/api/*": {"reverse_proxy": "api:8000"},
            "/health/*": {"reverse_proxy": "api:8000"},
        },
        "static": {
            "root": ["*", "/srv/web"],
            "try_files": ["{path}", "/index.html"],
            "file_server": True,
        },
    }


def main() -> int:
    default_file = pathlib.Path(__file__).resolve().parents[1] / "caddy" / "Caddyfile"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=pathlib.Path, default=default_file)
    arguments = parser.parse_args()
    try:
        text = arguments.file.read_text(encoding="utf-8")
        contract = validate_caddyfile(text)
    except OSError as error:
        print(f"CADDYFILE_IO_ERROR: {error}", file=sys.stderr)
        return 2
    except CaddyfileValidationError as error:
        print(f"CADDYFILE_INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(contract, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
