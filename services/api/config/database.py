from dataclasses import dataclass
from string import hexdigits
from urllib.parse import parse_qsl, unquote, urlparse


_ALLOWED_SSL_MODES = {"require", "verify-ca", "verify-full"}
_ALLOWED_OPTIONS = {"sslmode", "channel_binding"}


@dataclass(frozen=True)
class PostgreSQLDatabase:
    name: str
    user: str
    password: str
    host: str
    port: str
    options: dict[str, str]


def _percent_decode(value: str, field_name: str) -> str:
    for index, character in enumerate(value):
        if character == "%" and (
            index + 2 >= len(value) or any(part not in hexdigits for part in value[index + 1 : index + 3])
        ):
            raise RuntimeError(f"DATABASE_URL has invalid percent encoding in {field_name}")
    try:
        decoded = unquote(value, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"DATABASE_URL has invalid UTF-8 in {field_name}") from error
    if not decoded or "\x00" in decoded:
        raise RuntimeError(f"DATABASE_URL has invalid {field_name}")
    return decoded


def normalize_host(value: str, setting_name: str) -> str:
    if not value or any(character.isspace() for character in value):
        raise RuntimeError(f"{setting_name} must be a host name only")
    try:
        parsed = urlparse(f"//{value}")
        port = parsed.port
    except ValueError as error:
        raise RuntimeError(f"{setting_name} must be a host name only") from error
    if (
        parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise RuntimeError(f"{setting_name} must be a host name only")
    return parsed.hostname.rstrip(".").casefold()


def parse_postgresql_url(database_url: str, neon_host_hint: str | None) -> PostgreSQLDatabase:
    try:
        parsed = urlparse(database_url)
        port = parsed.port
    except ValueError as error:
        raise RuntimeError("DATABASE_URL has an invalid PostgreSQL port") from error
    if port is not None and not 1 <= port <= 65535:
        raise RuntimeError("DATABASE_URL has an invalid PostgreSQL port")
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL must use the postgresql scheme")
    if parsed.fragment:
        raise RuntimeError("DATABASE_URL must not contain a fragment")
    if not parsed.hostname or parsed.username is None or not parsed.path.startswith("/"):
        raise RuntimeError("DATABASE_URL must include PostgreSQL host, database, and user")

    host = normalize_host(parsed.hostname, "DATABASE_URL host")
    if neon_host_hint is not None and normalize_host(neon_host_hint, "NEON_DATABASE_HOST") != host:
        raise RuntimeError("NEON_DATABASE_HOST must match the normalized DATABASE_URL host")

    name = _percent_decode(parsed.path[1:], "database name")
    if "/" in name:
        raise RuntimeError("DATABASE_URL must name exactly one database")
    user = _percent_decode(parsed.username, "user")
    password = _percent_decode(parsed.password or "", "password")
    try:
        query_items = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as error:
        raise RuntimeError("DATABASE_URL has an invalid query string") from error
    option_names = [name for name, _ in query_items]
    if len(option_names) != len(set(option_names)) or set(option_names) - _ALLOWED_OPTIONS:
        raise RuntimeError("DATABASE_URL has duplicate or unsupported connection options")
    options = {name: value for name, value in query_items}
    if options.get("sslmode") not in _ALLOWED_SSL_MODES:
        raise RuntimeError("DATABASE_URL must set sslmode=require or stronger")
    if "channel_binding" in options and options["channel_binding"] != "require":
        raise RuntimeError("DATABASE_URL channel_binding must be require when supplied")
    options.setdefault("channel_binding", "require")

    return PostgreSQLDatabase(
        name=name,
        user=user,
        password=password,
        host=host,
        port=str(5432 if port is None else port),
        options=options,
    )
