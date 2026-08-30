import uuid

from django.core.cache import cache
import json

from django.test import Client, RequestFactory, override_settings

from splitbind.access.models import Organization, Role, User
from splitbind.access.throttles import AccountRateThrottle, IssuanceJobRateThrottle, SourceIPRateThrottle, VerificationJobRateThrottle


@override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1, "DEFAULT_THROTTLE_RATES": {"account": "1/min", "source_ip": "1/min", "issuance_job": "1/min", "verification_job": "1/min"}})
def test_account_ip_and_job_kind_throttle_keys_are_isolated(db):
    cache.clear()
    org = Organization.objects.create(name="Throttle", slug=f"throttle-{uuid.uuid4().hex[:8]}")
    first = User.objects.create_user(username="first", password="test", organization=org, role=Role.ISSUER)
    second = User.objects.create_user(username="second", password="test", organization=org, role=Role.ISSUER)
    factory = RequestFactory()

    def request(user, ip):
        value = factory.post("/api/v1/issuances", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR=ip)
        value.user = user
        return value

    first_request = request(first, "198.51.100.10")
    assert AccountRateThrottle().allow_request(first_request, None) is True
    assert AccountRateThrottle().allow_request(first_request, None) is False
    assert AccountRateThrottle().allow_request(request(second, "198.51.100.10"), None) is True
    assert SourceIPRateThrottle().allow_request(first_request, None) is True
    assert SourceIPRateThrottle().allow_request(request(second, "198.51.100.10"), None) is False
    assert SourceIPRateThrottle().allow_request(request(second, "198.51.100.11"), None) is True
    assert IssuanceJobRateThrottle().allow_request(first_request, None) is True
    assert VerificationJobRateThrottle().allow_request(first_request, None) is True


@override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1, "DEFAULT_THROTTLE_RATES": {"account": "1/min", "source_ip": "10/min", "issuance_job": "10/min", "verification_job": "10/min"}})
def test_business_mutation_returns_429_after_account_rate_is_exhausted(db):
    cache.clear()
    org = Organization.objects.create(name="HTTP Throttle", slug=f"http-throttle-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="http-user", password="test", organization=org, role=Role.ISSUER)
    client = Client()
    client.force_login(actor)
    body = json.dumps({"kind": "issuance_input"})

    first = client.post("/api/v1/uploads", data=body, content_type="application/json")
    second = client.post("/api/v1/uploads", data=body, content_type="application/json")

    assert first.status_code == 400
    assert second.status_code == 429


@override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1, "DEFAULT_THROTTLE_RATES": {"account": "10/min", "source_ip": "1/min", "issuance_job": "10/min", "verification_job": "10/min"}})
def test_only_single_internal_proxy_hop_is_trusted(db):
    cache.clear()
    org = Organization.objects.create(name="Proxy", slug=f"proxy-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="proxy-user", password="test", organization=org, role=Role.ISSUER)
    factory = RequestFactory()

    def build(chain):
        request = factory.post("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR=chain)
        request.user = actor
        return request

    throttle = SourceIPRateThrottle()
    assert throttle.allow_request(build("203.0.113.99, 198.51.100.10"), None) is True
    assert SourceIPRateThrottle().allow_request(build("192.0.2.88, 198.51.100.10"), None) is False
