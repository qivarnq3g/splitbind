import type { UploadStage } from "../features/uploads/uploadIssuance";

const STAGE_STEP: Record<UploadStage, number> = { hashing: 1, intent: 2, uploading: 3, finalizing: 4 };
const STAGE_LABEL: Record<UploadStage, string> = {
  hashing: "Đang kiểm tra tệp",
  intent: "Đang tạo phiên tải lên",
  uploading: "Đang tải tệp",
  finalizing: "Đang xác nhận tệp",
};

export function WorkflowSteps({ stage }: { stage: UploadStage | null }) {
  const step = stage ? STAGE_STEP[stage] : 0;

  return (
    <div className="progress-slot" role="status" aria-label="Tiến độ tải tệp" aria-live="polite">
      {stage ? (
        <>
          <div className="progress-copy"><span>{STAGE_LABEL[stage]}</span><span>Bước {step}/4</span></div>
          <progress max="4" value={step}>Bước {step}/4</progress>
        </>
      ) : <p>Sẵn sàng khi bạn xác nhận.</p>}
    </div>
  );
}
