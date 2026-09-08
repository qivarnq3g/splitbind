import { DragEvent, useState } from "react";
import { FileCheck2, UploadCloud } from "lucide-react";

type Props = {
  id: string;
  label: string;
  accept: string;
  describedBy: string;
  disabled: boolean;
  invalid: boolean;
  filename: string | null;
  onChange: (file: File | undefined) => void;
};

export function DocumentFileInput({ id, label, accept, describedBy, disabled, invalid, filename, onChange }: Props) {
  const [isDragOver, setIsDragOver] = useState(false);

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!disabled) setIsDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (!disabled && e.dataTransfer.files?.[0]) {
      onChange(e.dataTransfer.files[0]);
    }
  }

  return (
    <>
      <span className="field-label">{label}</span>
      <div
        className={`file-picker ${isDragOver ? "is-dragover" : ""} ${filename ? "has-file" : "is-empty"}`.trim()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="file-picker-icon" aria-hidden="true">
          {filename ? <FileCheck2 size={22} strokeWidth={2} /> : <UploadCloud size={22} strokeWidth={1.75} />}
        </div>
        <input
          className="file-control"
          id={id}
          name={id}
          type="file"
          accept={accept}
          required
          disabled={disabled}
          aria-label={label}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.files?.[0])}
        />
        <label className="file-trigger" htmlFor={id}>Chọn tệp</label>
        <span className="file-name" aria-live="polite">{filename ?? "Chưa chọn tệp"}</span>
      </div>
    </>
  );
}
