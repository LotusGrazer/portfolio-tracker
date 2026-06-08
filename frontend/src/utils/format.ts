// Display formatters. Null/undefined render as an em dash so missing data
// (e.g. an unpriced holding) reads cleanly in tables.

const DASH = "—";

export function formatCurrency(
  value: number | null | undefined,
  currency = "AUD",
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(
  value: number | null | undefined,
  maximumFractionDigits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  return new Intl.NumberFormat("en-AU", { maximumFractionDigits }).format(value);
}

export function formatPct(
  value: number | null | undefined,
  withSign = false,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  const text = `${value.toFixed(2)}%`;
  return withSign && value > 0 ? `+${text}` : text;
}

// CSS class for colouring gains green / losses red / zero neutral.
export function gainClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

// Australian financial year (1 Jul – 30 Jun) label, e.g. "2024-25".
export function currentFinancialYear(now = new Date()): string {
  const y = now.getFullYear();
  const start = now.getMonth() >= 6 ? y : y - 1; // getMonth: July = 6
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

export function recentFinancialYears(count = 5, now = new Date()): string[] {
  const startYear = Number(currentFinancialYear(now).slice(0, 4));
  return Array.from({ length: count }, (_, i) => {
    const s = startYear - i;
    return `${s}-${String((s + 1) % 100).padStart(2, "0")}`;
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  // Backend timestamps are naive UTC; mark them as UTC so they localise right.
  const normalised = /[Z+]/.test(iso) ? iso : `${iso}Z`;
  const date = new Date(normalised);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleString("en-AU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
