import { ReactNode } from "react";
import { ShieldAlert } from "lucide-react";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div className={`empty-state-card ${className}`.trim()} role="region" aria-label={title}>
      <div className="empty-state-icon" aria-hidden="true">
        {icon ?? <ShieldAlert size={28} strokeWidth={1.75} />}
      </div>
      <div className="empty-state-body">
        <h3 className="empty-state-title">{title}</h3>
        <p className="empty-state-desc">{description}</p>
      </div>
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
