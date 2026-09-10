from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from splitbind.access.models import Recipient, SigningKey, SigningKeyStatus, _signing_key_lifecycle_write


def resolve_recipient_for_issue(
    *,
    organization,
    recipient_email: str,
    recipient_name: str | None = None,
) -> Recipient:
    email = recipient_email.strip().lower()
    validate_email(email)
    name = (recipient_name or "").strip()

    recipient = (
        Recipient.objects.filter(
            organization=organization,
            external_reference__iexact=email,
        ).first()
    )

    if recipient is not None:
        if name and not recipient.display_name.strip():
            recipient.display_name = name
            recipient.save(update_fields=["display_name"])
        return recipient

    try:
        with transaction.atomic():
            return Recipient.objects.create(
                organization=organization,
                external_reference=email,
                display_name=name,
            )
    except IntegrityError:
        recipient = Recipient.objects.get(
            organization=organization,
            external_reference__iexact=email,
        )
        if name and not recipient.display_name.strip():
            recipient.display_name = name
            recipient.save(update_fields=["display_name"])
        return recipient


@transaction.atomic
def register_signing_key(**fields):
    """Create one policy-validated public signing-key registry record."""
    return SigningKey.objects.create(**fields)


@transaction.atomic
def transition_signing_key(key_pk, target_status: str, *, at):
    if target_status not in SigningKeyStatus.values:
        raise ValidationError("signing-key lifecycle target is invalid")
    key = SigningKey.objects.select_for_update().get(pk=key_pk)
    allowed = {
        SigningKeyStatus.ACTIVE: {SigningKeyStatus.VERIFY_ONLY, SigningKeyStatus.REVOKED},
        SigningKeyStatus.VERIFY_ONLY: {SigningKeyStatus.REVOKED},
        SigningKeyStatus.REVOKED: set(),
    }
    if target_status == key.status:
        return key
    if key.status == SigningKeyStatus.REVOKED:
        raise ValidationError("revoked signing-key lifecycle is terminal")
    if target_status not in allowed[key.status]:
        raise ValidationError("signing-key lifecycle transition is invalid")
    if at.tzinfo is None or at < key.valid_from:
        raise ValidationError("signing-key lifecycle time is invalid")
    key.status = target_status
    key.revoked_at = at if target_status == SigningKeyStatus.REVOKED else None
    token = _signing_key_lifecycle_write.set(True)
    try:
        key.save(update_fields=["status", "revoked_at"])
    finally:
        _signing_key_lifecycle_write.reset(token)
    return key
