import hashlib

from rest_framework.throttling import SimpleRateThrottle
from rest_framework.settings import api_settings


def _bounded_digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


class AccountRateThrottle(SimpleRateThrottle):
    scope = "account"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": _bounded_digest(user.pk)}


class SourceIPRateThrottle(SimpleRateThrottle):
    scope = "source_ip"

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": _bounded_digest(self.get_ident(request)),
        }


class _JobKindRateThrottle(AccountRateThrottle):
    def get_cache_key(self, request, view):
        account_key = super().get_cache_key(request, view)
        if account_key is None:
            return None
        return f"{account_key}:{self.scope}"


class IssuanceJobRateThrottle(_JobKindRateThrottle):
    scope = "issuance_job"


class VerificationJobRateThrottle(_JobKindRateThrottle):
    scope = "verification_job"
