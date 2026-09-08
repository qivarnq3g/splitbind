export function StatusBadge({ label, status, title }: { label: string; status?: string | null; title: string }) {
  return (
    <div className="status-primary" data-status={status ?? undefined} role="status" aria-label={`${label}: ${title}`}>
      <span className="status-dot" aria-hidden="true" />
      <div>
        <p>{label}</p>
        <h2>{title}</h2>
      </div>
    </div>
  );
}
