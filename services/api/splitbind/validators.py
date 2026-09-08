from django.core.validators import RegexValidator


SHA256_PATTERN = r"^[0-9a-f]{64}$"
validate_sha256 = RegexValidator(
    regex=SHA256_PATTERN,
    message="Enter exactly 64 lowercase hexadecimal SHA-256 characters.",
    code="invalid_sha256",
)
