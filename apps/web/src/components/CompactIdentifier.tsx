import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CompactIdentifier({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const compact = value.length > 13 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className="compact-identifier" title={value}>
      <code>{compact}</code>
      <button
        className="copy-identifier"
        type="button"
        aria-label={`${copied ? "Đã sao chép" : "Sao chép"} ${label.toLocaleLowerCase("vi-VN")}`}
        onClick={() => void copy()}
      >
        {copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
      </button>
    </span>
  );
}
