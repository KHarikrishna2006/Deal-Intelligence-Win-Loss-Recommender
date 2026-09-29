import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function money(value: string | number | null | undefined, currency = "USD"): string {
  const n = typeof value === "string" ? Number(value) : (value ?? 0);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}

export function compactMoney(value: string | number | null | undefined, currency = "USD"): string {
  const n = typeof value === "string" ? Number(value) : (value ?? 0);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value.endsWith("Z") || value.includes("+") ? value : value + "Z");
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value.endsWith("Z") || value.includes("+") ? value : value + "Z");
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function relativeTime(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value.endsWith("Z") || value.includes("+") ? value : value + "Z");
  if (Number.isNaN(d.getTime())) return value;
  const diff = Date.now() - d.getTime();
  const mins = Math.round(diff / 60000);
  if (Math.abs(mins) < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 30) return `${days}d ago`;
  return formatDate(value);
}

export const STAGES = [
  "LEAD",
  "QUALIFICATION",
  "DISCOVERY",
  "PROPOSAL",
  "NEGOTIATION",
  "CLOSED_WON",
  "CLOSED_LOST",
] as const;

export const STAGE_LABEL: Record<string, string> = {
  LEAD: "Lead",
  QUALIFICATION: "Qualification",
  DISCOVERY: "Discovery",
  PROPOSAL: "Proposal",
  NEGOTIATION: "Negotiation",
  CLOSED_WON: "Closed Won",
  CLOSED_LOST: "Closed Lost",
};

export function stageTone(stage: string): string {
  switch (stage) {
    case "CLOSED_WON":
      return "text-success border-success/30 bg-success/10";
    case "CLOSED_LOST":
      return "text-danger border-danger/30 bg-danger/10";
    case "NEGOTIATION":
      return "text-warning border-warning/30 bg-warning/10";
    default:
      return "text-accent border-accent/30 bg-accent/soft";
  }
}

export function outcomeTone(value?: string | null): string {
  if (value === "WON") return "text-success border-success/30 bg-success/10";
  if (value === "LOST") return "text-danger border-danger/30 bg-danger/10";
  return "text-ink-muted border-line bg-surface-sunken";
}

export function evidenceTone(value: string): string {
  if (value === "EVIDENCE_BASED") return "text-success border-success/30 bg-success/10";
  if (value === "INSUFFICIENT_DATA") return "text-warning border-warning/30 bg-warning/10";
  return "text-accent border-accent/30 bg-accent-soft";
}
