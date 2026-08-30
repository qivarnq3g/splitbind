import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
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
  it.each(statuses)("separates the four evidence sections for %s", (status) => {
    render(<EvidenceSummary status={status} evidence={{}} />);
    expect(screen.getByRole("heading", { name: "Sự kiện" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Độ tin cậy" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Giới hạn" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Suy luận thận trọng" })).toBeVisible();
    expect(screen.getByText(STATUS_COPY[status].label)).toBeVisible();
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
    expect(screen.getByText(new RegExp(copy, "i"))).toBeVisible();
  });

  it("shows only a safe generic message for an unknown limitation identifier", () => {
    render(<EvidenceSummary status="INVALID_MANIFEST" evidence={{ limitations: ["private.backend.detail"] }} />);
    expect(screen.queryByText("private.backend.detail")).not.toBeInTheDocument();
    expect(screen.getByText("Kết quả có thêm giới hạn kỹ thuật chưa được giao diện mô tả chi tiết.")).toBeVisible();
  });
});
