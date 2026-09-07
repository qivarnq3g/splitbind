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
  return (
    <>
      <span className="field-label">{label}</span>
      <div className="file-picker">
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
