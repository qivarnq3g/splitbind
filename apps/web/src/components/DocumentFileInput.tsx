import { DragEvent, useRef, useState } from "react";
import { FileCheck2, FileWarning, UploadCloud, X } from "lucide-react";
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
export function DocumentFileInput({
  id,
  label,
  accept,
  describedBy,
  disabled,
  invalid,
  filename,
  onChange,
}: Props) {
  const [isDragOver, setIsDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragOver(false);
    if (!disabled && event.dataTransfer.files?.[0])
      onChange(event.dataTransfer.files[0]);
  }
  return (
    <>
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div
        className={`file-picker ${isDragOver ? "is-dragover" : ""} ${filename ? "has-file" : "is-empty"}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={drop}
      >
        <span className="file-picker-icon" aria-hidden="true">
          {invalid ? (
            <FileWarning size={30} strokeWidth={1.5} />
          ) : filename ? (
            <FileCheck2 size={30} strokeWidth={1.5} />
          ) : (
            <UploadCloud size={30} strokeWidth={1.5} />
          )}
        </span>
        <input
          ref={input}
          className="file-control"
          id={id}
          name={id}
          type="file"
          accept={accept}
          required={!filename}
          disabled={disabled}
          aria-label={label}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          onChange={(event) => {
            if (event.target.files?.[0]) onChange(event.target.files[0]);
          }}
        />
        <div className="file-selection">
          <span className="file-name" aria-live="polite">
            {filename ?? "Chưa chọn tệp"}
          </span>
          <span className="file-instruction">
            {filename
              ? "Tệp được chọn trên thiết bị"
              : "Kéo tệp vào đây hoặc chọn từ thiết bị"}
          </span>
        </div>
        <label className="file-trigger" htmlFor={id}>
          {filename ? "Đổi tệp" : "Chọn tệp"}
        </label>
      </div>
      {filename ? (
        <button
          className="remove-file"
          type="button"
          disabled={disabled}
          aria-label="Bỏ tệp đã chọn"
          onClick={() => {
            if (input.current) input.current.value = "";
            onChange(undefined);
          }}
        >
          <X size={14} aria-hidden="true" />
          Bỏ tệp
        </button>
      ) : null}
    </>
  );
}
