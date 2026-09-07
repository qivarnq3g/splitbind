import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import { LIMITATION_COPY, STATUS_COPY, STATUS_LIMITATIONS } from "../features/evidence/copy";

const statuses = [
  "VERIFIED_INTACT",
  "SOURCE_IDENTIFIED_MODIFIED",
  "PARTIAL_EVIDENCE",
  "NO_WATERMARK",
  "INVALID_MANIFEST",
  "PROCESSING_FAILED",
] as const;

afterEach(cleanup);

describe("verification evidence language", () => {
  it.each(statuses)("keeps the conclusion visible and technical evidence collapsed for %s", (status) => {
    render(<EvidenceSummary status={status} evidence={{}} />);
    expect(screen.getByText(STATUS_COPY[status].inference)).toBeVisible();
    const details = screen.getByText("Xem chi tiết kỹ thuật").closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Dữ liệu kỹ thuật" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Giới hạn của kết quả" })).toBeInTheDocument();
    for (const limitationId of STATUS_LIMITATIONS[status]) {
      expect(screen.getAllByText(LIMITATION_COPY[limitationId]!)).not.toHaveLength(0);
    }
  });

  it.each([
    ["NO_WATERMARK", "không có nghĩa tài liệu chắc chắn không thuộc hệ thống"],
    ["PARTIAL_EVIDENCE", "chưa đủ ngưỡng để gán nguồn phát hành"],
    ["SOURCE_IDENTIFIED_MODIFIED", "không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán"],
  ] as const)("renders mandatory limitation copy for %s", (status, copy) => {
    render(<EvidenceSummary status={status} evidence={{}} />);
    expect(screen.getByText(new RegExp(copy, "i"))).toBeInTheDocument();
  });

  it("shows only a safe generic message for an unknown limitation identifier", () => {
    render(<EvidenceSummary status="INVALID_MANIFEST" evidence={{ limitations: ["private.backend.detail"] }} />);
    expect(screen.queryByText("private.backend.detail")).not.toBeInTheDocument();
    expect(screen.getByText("Kết quả có thêm giới hạn kỹ thuật chưa được giao diện mô tả chi tiết.")).toBeInTheDocument();
  });

  it("keeps the unreleased fingerprint warning when the API reports it", () => {
    render(<EvidenceSummary
      status="PARTIAL_EVIDENCE"
      evidence={{ limitations: ["fingerprint.experimental_unreleased_v2"] }}
    />);

    expect(screen.getByText(LIMITATION_COPY["fingerprint.experimental_unreleased_v2"]!)).toBeInTheDocument();
  });

  it("does not turn an omitted suspicious-region field into a zero count", () => {
    render(<EvidenceSummary status="NO_WATERMARK" evidence={{}} />);
    const fact = screen.getByText("Số vùng nghi vấn").parentElement!;
    expect(within(fact).getByText("API chưa cung cấp")).toBeInTheDocument();
    expect(within(fact).queryByText("0")).not.toBeInTheDocument();
  });
});
