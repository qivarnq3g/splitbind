import json

import pytest

from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def test_schema_publishes_every_current_browser_facing_route(schema):
    assert set(schema["paths"]) == {
        "/api/v1/audit-events",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/session",
        "/api/v1/demo/capabilities",
        "/api/v1/issuances",
        "/api/v1/issuances/{id}",
        "/api/v1/issuances/{id}/result",
        "/api/v1/jobs",
        "/api/v1/jobs/{id}",
        "/api/v1/jobs/{id}/cancel",
        "/api/v1/uploads",
        "/api/v1/uploads/{id}/complete",
        "/api/v1/verifications",
        "/api/v1/verifications/{id}",
        "/health/live",
        "/health/ready",
    }


@pytest.mark.parametrize(
    ("path", "method", "status_codes"),
    [
        ("/api/v1/auth/session", "get", {"200"}),
        ("/api/v1/auth/login", "post", {"200", "400", "403"}),
        ("/api/v1/auth/logout", "post", {"200", "403"}),
        ("/api/v1/demo/capabilities", "get", {"200", "403"}),
        ("/api/v1/audit-events", "get", {"200", "403"}),
        ("/api/v1/uploads", "post", {"201", "400", "403", "429", "503"}),
        ("/api/v1/uploads/{id}/complete", "post", {"200", "400", "403", "404", "429", "503"}),
        ("/api/v1/issuances", "post", {"201", "400", "403", "404", "409", "429"}),
        ("/api/v1/issuances/{id}", "get", {"200", "403", "404"}),
        ("/api/v1/issuances/{id}/result", "get", {"200", "403", "404", "409", "429", "503"}),
        ("/api/v1/verifications", "post", {"201", "400", "403", "404", "409", "429"}),
        ("/api/v1/verifications/{id}", "get", {"200", "403", "404"}),
        ("/api/v1/jobs", "get", {"200", "403"}),
        ("/api/v1/jobs/{id}", "get", {"200", "403", "404"}),
        ("/api/v1/jobs/{id}/cancel", "post", {"200", "400", "403", "404", "409", "429"}),
        ("/health/live", "get", {"200"}),
        ("/health/ready", "get", {"200", "503"}),
    ],
)
def test_operation_documents_current_success_and_error_paths(schema, path, method, status_codes):
    assert set(schema["paths"][path][method]["responses"]) == status_codes


def test_schema_describes_session_cookie_and_csrf_boundaries(schema):
    assert schema["paths"]["/health/live"]["get"].get("security", []) == []
    assert schema["paths"]["/health/ready"]["get"].get("security", []) == []
    assert schema["paths"]["/api/v1/auth/session"]["get"].get("security", []) == []
    assert schema["paths"]["/api/v1/auth/login"]["post"].get("security", []) == []

    protected = schema["paths"]["/api/v1/jobs/{id}"]["get"]
    assert {"cookieAuth": []} in protected["security"]
    assert {"cookieAuth": []} in schema["paths"]["/api/v1/jobs"]["get"]["security"]

    mutation = schema["paths"]["/api/v1/jobs/{id}/cancel"]["post"]
    csrf = next(parameter for parameter in mutation["parameters"] if parameter["name"] == "X-CSRFToken")
    assert csrf["in"] == "header"
    assert csrf["required"] is True
    assert all(parameter["name"] != "X-CSRFToken" for parameter in protected.get("parameters", []))


def test_schema_exposes_structured_response_contracts(schema):
    components = schema["components"]["schemas"]
    assert components["UploadIntent"]["properties"]["upload_url"]["format"] == "uri"
    assert components["Issuance"]["properties"]["result_available"]["type"] == "boolean"
    assert components["IssuanceResult"]["properties"]["download_url"]["format"] == "uri"

    def enum_values(component, field):
        field_schema = components[component]["properties"][field]
        reference = field_schema.get("$ref") or next(
            item["$ref"] for item in field_schema.get("oneOf", []) + field_schema.get("allOf", [])
            if item.get("$ref", "").rsplit("/", 1)[-1] != "NullEnum"
        )
        return components[reference.rsplit("/", 1)[1]]["enum"]

    assert enum_values("Job", "status") == [
        "created",
        "queued",
        "processing",
        "retryable_failed",
        "succeeded",
        "failed",
        "dead_lettered",
        "cancelled",
    ]
    assert enum_values("Verification", "status") == [
        "VERIFIED_INTACT",
        "SOURCE_IDENTIFIED_MODIFIED",
        "PARTIAL_EVIDENCE",
        "NO_WATERMARK",
        "INVALID_MANIFEST",
        "PROCESSING_FAILED",
    ]
    assert enum_values("VerificationEvidence", "algorithm_label") == [
        "experimental_unreleased_fingerprint_v2",
        "integrity_release_v1",
    ]
    assert enum_values("VerificationEvidence", "decode_status") == [
        "decoded",
        "partial_payload_evidence",
        "payload_not_detected",
        "insufficient_sync_evidence",
        "geometry_rejected",
        "execution_error",
        "cancelled",
    ]
    assert "NullEnum" in json.dumps(
        components["VerificationEvidence"]["properties"]["algorithm_label"]
    )
    assert "NullEnum" in json.dumps(
        components["VerificationEvidence"]["properties"]["decode_status"]
    )
    capability = components["DemoCapability"]["properties"]
    assert capability["hidden_fingerprint_enabled"]["type"] == "boolean"
    assert capability["transformed_attribution_available"]["type"] == "boolean"
