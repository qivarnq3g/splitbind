import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrityEvidence } from "../features/evidence/IntegrityEvidence";
import type { components } from "../api/generated/schema";

const ISSUANCE_ID = "00000000-0000-4000-8000-00000000beef";

const EVIDENCE: components["schemas"]["VerificationEvidence"] = {
  algorithm_label: "integrity_release_v1",
  analyzed_page_count: 3,
  decode_status: null,
  exact_file_hash_match: true,
  fingerprint_confidence: undefined,
  integrity_score: null,
  limitations: [],
  manifest_signature_valid: true,
  suspicious_regions: [],
  valid_vote_count: undefined,
};

function openTechnicalDetails() {
  fireEvent.click(screen.getByText("Xem chi tiết kỹ thuật"));
}

function json(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("exporting the verifiable manifest", () => {
  beforeEach(() => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:manifest");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  });

  it("offers no export when nothing was matched", () => {
    render(
      <IntegrityEvidence
        status="NO_WATERMARK"
        evidence={{ ...EVIDENCE, exact_file_hash_match: false }}
        showConclusion={false}
      />,
    );

    openTechnicalDetails();

    expect(
      screen.queryByRole("button", { name: "Tải hồ sơ kiểm chứng" }),
    ).not.toBeInTheDocument();
  });

  it("fetches the public manifest for the matched issuance", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async () =>
      json({
        payload: '{"issuance_id":"x"}',
        signature: { algorithm: "Ed25519", key_id: "k1", signature: "sig" },
        public_key: { key_id: "k1", algorithm: "Ed25519", public_key: "pem" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click");
    click.mockImplementation(() => undefined);

    render(
      <IntegrityEvidence
        status="VERIFIED_INTACT"
        evidence={EVIDENCE}
        showConclusion={false}
        matchedIssuanceId={ISSUANCE_ID}
      />,
    );

    openTechnicalDetails();
    fireEvent.click(
      screen.getByRole("button", { name: "Tải hồ sơ kiểm chứng" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0]![0];
    expect(String(request instanceof Request ? request.url : request)).toContain(
      `/api/v1/issuances/${ISSUANCE_ID}/manifest`,
    );
    await waitFor(() => expect(click).toHaveBeenCalled());
  });

  it("shows the matched issuance among the technical facts", () => {
    render(
      <IntegrityEvidence
        status="VERIFIED_INTACT"
        evidence={EVIDENCE}
        showConclusion={false}
        matchedIssuanceId={ISSUANCE_ID}
      />,
    );

    openTechnicalDetails();

    expect(screen.getByText("Hồ sơ cấp phát đã khớp")).toBeVisible();
  });
});
