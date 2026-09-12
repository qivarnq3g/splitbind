import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

export function CompactIdentifier({
  label,
  value,
  full = false,
}: {
  label: string;
  value: string;
  full?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const displayValue = full
    ? value
    : value.length > 13
      ? `${value.slice(0, 8)}…${value.slice(-4)}`
      : value;

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2500);
    return () => window.clearTimeout(timer);
  }, [copied]);

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
      <code>{displayValue}</code>
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
