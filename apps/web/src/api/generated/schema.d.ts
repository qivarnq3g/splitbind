export interface paths {
    "/api/v1/audit-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["audit_event_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_login"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["auth_logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["auth_session"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/demo/capabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["demo_capabilities_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/issuances": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["issuance_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/issuances/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["issuance_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/issuances/{id}/manifest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** @description Return the public manifest, its detached signature and the signing key, so a third party can verify the issuance without trusting this API. The projection omits the recipient and the source digest by construction. */
        get: operations["issuance_manifest_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/issuances/{id}/result": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["issuance_result_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["job_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["job_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["job_cancel"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/uploads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["upload_intent_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/uploads/{id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["upload_complete"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/verifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["verification_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/verifications/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["verification_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["health_live"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["health_ready"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * @description * `experimental_unreleased_fingerprint_v2` - experimental_unreleased_fingerprint_v2
         *     * `integrity_release_v1` - integrity_release_v1
         * @enum {string}
         */
        AlgorithmLabelEnum: "experimental_unreleased_fingerprint_v2" | "integrity_release_v1";
        AuditEvent: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            actor_id: string | null;
            action: string;
            target_type: string;
            target_id: string;
            /** Format: uuid */
            correlation_id: string;
            outcome: string;
            metadata: unknown;
            /** Format: date-time */
            created_at: string;
        };
        AuditEventList: {
            results: components["schemas"]["AuditEvent"][];
        };
        CancelJobRequest: {
            /** Format: uuid */
            correlation_id: string;
        };
        CodeError: {
            code: string;
        };
        /**
         * @description * `decoded` - decoded
         *     * `partial_payload_evidence` - partial_payload_evidence
         *     * `payload_not_detected` - payload_not_detected
         *     * `insufficient_sync_evidence` - insufficient_sync_evidence
         *     * `geometry_rejected` - geometry_rejected
         *     * `execution_error` - execution_error
         *     * `cancelled` - cancelled
         * @enum {string}
         */
        DecodeStatusEnum: "decoded" | "partial_payload_evidence" | "payload_not_detected" | "insufficient_sync_evidence" | "geometry_rejected" | "execution_error" | "cancelled";
        DemoCapability: {
            enabled: boolean;
            processing_limits: components["schemas"]["DemoProcessingLimits"];
            algorithm_label: components["schemas"]["AlgorithmLabelEnum"];
            hidden_fingerprint_enabled?: boolean;
            transformed_attribution_available?: boolean;
        };
        DemoProcessingLimits: {
            max_pdf_pages: number;
            max_pdf_bytes: number;
            max_image_pixels: number;
        };
        DetailError: {
            detail: string;
        };
        /**
         * @description * `ok` - ok
         * @enum {string}
         */
        HealthStatusEnum: "ok";
        Issuance: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            job_id: string | null;
            status: (components["schemas"]["JobStatusEnum"] | components["schemas"]["NullEnum"]) | null;
            /** Format: date-time */
            issued_at: string;
            result_available: boolean;
            algorithm_label: (components["schemas"]["AlgorithmLabelEnum"] | components["schemas"]["NullEnum"]) | null;
        };
        IssuanceCreateRequest: {
            /** Format: uuid */
            recipient_id?: string;
            /** Format: email */
            recipient_email?: string;
            recipient_name?: string;
            /** Format: uuid */
            upload_id: string;
            /** Format: uuid */
            correlation_id: string;
        };
        /** @description The externally shareable projection: never carries recipient or source. */
        IssuanceManifest: {
            /** @description Canonical public manifest, exactly the bytes the signature covers. */
            payload: string;
            /** @description Detached Ed25519 signature envelope over the payload. */
            signature: {
                [key: string]: unknown;
            };
            public_key: components["schemas"]["ManifestPublicKey"];
        };
        IssuanceResult: {
            /** Format: uri */
            download_url: string;
            /** Format: date-time */
            expires_at: string;
        };
        Job: {
            /** Format: uuid */
            id: string;
            kind: components["schemas"]["JobKindEnum"];
            status: components["schemas"]["JobStatusEnum"];
            attempt: number;
            /** Format: uuid */
            issuance_id: string | null;
            /** Format: uuid */
            verification_id: string | null;
            /** Format: date-time */
            deadline_at: string;
            /** Format: date-time */
            cancel_requested_at: string | null;
            safe_error_code: string | null;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            updated_at: string;
            recipient_email?: string | null;
            recipient_name?: string | null;
            verification_status?: string | null;
        };
        /**
         * @description * `issuance` - issuance
         *     * `verification` - verification
         * @enum {string}
         */
        JobKindEnum: "issuance" | "verification";
        /**
         * @description * `created` - created
         *     * `queued` - queued
         *     * `processing` - processing
         *     * `retryable_failed` - retryable_failed
         *     * `succeeded` - succeeded
         *     * `failed` - failed
         *     * `dead_lettered` - dead_lettered
         *     * `cancelled` - cancelled
         * @enum {string}
         */
        JobStatusEnum: "created" | "queued" | "processing" | "retryable_failed" | "succeeded" | "failed" | "dead_lettered" | "cancelled";
        Live: {
            status: components["schemas"]["HealthStatusEnum"];
        };
        LoginRequest: {
            username: string;
            password: string;
        };
        ManifestPublicKey: {
            key_id: string;
            algorithm: string;
            /** @description Ed25519 public key, standard SPKI PEM. */
            public_key: string;
            status: string;
            /** Format: date-time */
            valid_from: string;
            /** Format: date-time */
            valid_until: string | null;
            /** Format: date-time */
            revoked_at: string | null;
        };
        /** @enum {unknown} */
        NullEnum: null;
        Readiness: {
            status: components["schemas"]["ReadinessStatusEnum"];
            components: {
                [key: string]: "up" | "down" | "not_applicable";
            };
        };
        /**
         * @description * `ready` - ready
         *     * `not_ready` - not_ready
         * @enum {string}
         */
        ReadinessStatusEnum: "ready" | "not_ready";
        /**
         * @description * `administrator` - administrator
         *     * `issuer` - issuer
         *     * `verifier` - verifier
         *     * `auditor` - auditor
         * @enum {string}
         */
        RoleEnum: "administrator" | "issuer" | "verifier" | "auditor";
        SessionResponse: {
            authenticated: boolean;
            csrf_token: string;
            user?: components["schemas"]["SessionUser"];
        };
        SessionUser: {
            /** Format: uuid */
            id: string;
            username: string;
            role: components["schemas"]["RoleEnum"];
            /** Format: uuid */
            organization_id: string;
        };
        SuspiciousRegion: {
            /** Format: double */
            x: number;
            /** Format: double */
            y: number;
            /** Format: double */
            width: number;
            /** Format: double */
            height: number;
        };
        Upload: {
            /** Format: uuid */
            id: string;
            object_key: string;
            expected_sha256: string;
            size_bytes: number;
            /** Format: date-time */
            expires_at: string;
            /** Format: date-time */
            finalized_at: string | null;
        };
        UploadCompleteRequest: {
            /** @description Repeat the client-computed expected SHA-256 bound at intent creation. */
            sha256: string;
        };
        UploadIntent: {
            /** Format: uuid */
            id: string;
            object_key: string;
            expected_sha256: string;
            size_bytes: number;
            /** Format: date-time */
            expires_at: string;
            /** Format: date-time */
            finalized_at: string | null;
            /** Format: uri */
            upload_url: string;
            required_headers: {
                [key: string]: string;
            };
        };
        /**
         * @description * `issuance_input` - issuance_input
         *     * `verification_input` - verification_input
         * @enum {string}
         */
        UploadIntentKindEnum: "issuance_input" | "verification_input";
        UploadIntentRequest: {
            kind: components["schemas"]["UploadIntentKindEnum"];
            filename: string;
            content_type: string;
            size_bytes: number;
            /** @description Client-computed expected SHA-256; the worker independently hashes stored bytes. */
            sha256: string;
        };
        Verification: {
            /** Format: uuid */
            id: string;
            /** Format: uuid */
            job_id: string | null;
            job_status: (components["schemas"]["JobStatusEnum"] | components["schemas"]["NullEnum"]) | null;
            status: (components["schemas"]["VerificationStatusEnum"] | components["schemas"]["NullEnum"]) | null;
            /** Format: date-time */
            created_at: string;
            /** Format: date-time */
            completed_at: string | null;
            /** @description SHA-256 of the file that was submitted for checking. */
            input_sha256: string | null;
            /**
             * Format: uuid
             * @description Issuance this file was recovered to, when one was identified. Fetch its public manifest to verify the match independently.
             */
            matched_issuance_id: string | null;
            evidence: components["schemas"]["VerificationEvidence"];
            metrics: components["schemas"]["VerificationMetrics"];
        };
        VerificationCreateRequest: {
            /** Format: uuid */
            upload_id: string;
            /** Format: uuid */
            correlation_id: string;
        };
        VerificationEvidence: {
            algorithm_label?: (components["schemas"]["AlgorithmLabelEnum"] | components["schemas"]["NullEnum"]) | null;
            decode_status?: (components["schemas"]["DecodeStatusEnum"] | components["schemas"]["NullEnum"]) | null;
            /** Format: double */
            fingerprint_confidence?: number;
            /** Format: double */
            integrity_score?: number | null;
            valid_vote_count?: number;
            analyzed_page_count?: number;
            manifest_signature_valid?: boolean | null;
            exact_file_hash_match?: boolean | null;
            suspicious_regions?: components["schemas"]["SuspiciousRegion"][];
            limitations?: string[];
        };
        VerificationMetrics: {
            processing_ms?: number;
            pages_processed?: number;
            peak_rss_bytes?: number;
            temp_peak_bytes?: number;
            cleanup_failures?: number;
        };
        /**
         * @description * `VERIFIED_INTACT` - VERIFIED_INTACT
         *     * `SOURCE_IDENTIFIED_MODIFIED` - SOURCE_IDENTIFIED_MODIFIED
         *     * `PARTIAL_EVIDENCE` - PARTIAL_EVIDENCE
         *     * `NO_WATERMARK` - NO_WATERMARK
         *     * `INVALID_MANIFEST` - INVALID_MANIFEST
         *     * `PROCESSING_FAILED` - PROCESSING_FAILED
         * @enum {string}
         */
        VerificationStatusEnum: "VERIFIED_INTACT" | "SOURCE_IDENTIFIED_MODIFIED" | "PARTIAL_EVIDENCE" | "NO_WATERMARK" | "INVALID_MANIFEST" | "PROCESSING_FAILED";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    audit_event_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventList"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    auth_login: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["LoginRequest"];
                "multipart/form-data": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Request validation failed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    };
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    auth_logout: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    auth_session: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
        };
    };
    demo_capabilities_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DemoCapability"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    issuance_create: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IssuanceCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["IssuanceCreateRequest"];
                "multipart/form-data": components["schemas"]["IssuanceCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Issuance"];
                };
            };
            /** @description Validation or safe workflow error. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    } | components["schemas"]["CodeError"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Workflow state or idempotency conflict. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    issuance_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Issuance"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    issuance_manifest_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IssuanceManifest"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Workflow state or idempotency conflict. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    issuance_result_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IssuanceResult"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Workflow state or idempotency conflict. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Object storage is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
        };
    };
    job_list: {
        parameters: {
            query?: {
                /** @description Filter jobs by kind (issuance or verification) */
                kind?: "issuance" | "verification";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Job"][];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    job_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Job"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    job_cancel: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelJobRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["CancelJobRequest"];
                "multipart/form-data": components["schemas"]["CancelJobRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Job"];
                };
            };
            /** @description Request validation failed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    };
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Workflow state or idempotency conflict. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    upload_intent_create: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UploadIntentRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UploadIntentRequest"];
                "multipart/form-data": components["schemas"]["UploadIntentRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadIntent"];
                };
            };
            /** @description Validation or safe upload error. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    } | components["schemas"]["CodeError"];
                };
            };
            /** @description Authentication, permission, CSRF, or upload policy denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"] | components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Object storage is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
        };
    };
    upload_complete: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UploadCompleteRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["UploadCompleteRequest"];
                "multipart/form-data": components["schemas"]["UploadCompleteRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Upload"];
                };
            };
            /** @description Validation or safe upload error. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    } | components["schemas"]["CodeError"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Object storage is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
        };
    };
    verification_create: {
        parameters: {
            query?: never;
            header: {
                /** @description Decoded csrftoken cookie value required by Django on unsafe requests. */
                "X-CSRFToken": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerificationCreateRequest"];
                "application/x-www-form-urlencoded": components["schemas"]["VerificationCreateRequest"];
                "multipart/form-data": components["schemas"]["VerificationCreateRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Verification"];
                };
            };
            /** @description Validation or safe workflow error. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[];
                    } | components["schemas"]["CodeError"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Workflow state or idempotency conflict. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodeError"];
                };
            };
            /** @description Request throttled. */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    verification_retrieve: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Verification"];
                };
            };
            /** @description Authentication, permission, or CSRF denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
            /** @description Resource not found in the caller's scope. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetailError"];
                };
            };
        };
    };
    health_live: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Live"];
                };
            };
        };
    };
    health_ready: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
        };
    };
}
