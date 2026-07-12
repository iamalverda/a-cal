import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes with conflict resolution. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a date for display in the calendar header. */
export function formatDateRange(start: Date, end: Date, view: "week" | "month"): string {
  if (view === "week") {
    const s = start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const e = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return `${s} – ${e}`;
  }
  return start.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

/** Generate a stable color from a string (sub-account name, provider type). */
export function colorFromString(str: string): string {
  const colors = [
    "var(--cal-work)",
    "var(--cal-personal)",
    "var(--cal-email)",
    "var(--cal-other)",
  ];
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}
