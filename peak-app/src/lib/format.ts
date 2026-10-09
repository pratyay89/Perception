import type { PaperStatus } from "@/lib/types";

/** Marks arrive from the API as decimal strings ("7.50"). */
export function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** 7 -> "7", 7.5 -> "7.5", 7.25 -> "7.25" */
export function formatMarks(value: string | number | null | undefined): string {
  return String(Math.round(num(value) * 100) / 100);
}

export function percentage(obtained: number, total: number): number {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, (obtained / total) * 100));
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** Value for <input type="datetime-local"> in the browser's own time zone. */
export function toDateTimeLocal(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function getInitials(email: string): string {
  return email.split("@")[0].substring(0, 2).toUpperCase();
}

export const STATUS_LABEL: Record<PaperStatus, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  open: "Active",
  closed: "Closed",
};

export function gradeFor(
  score: number,
  total: number
): { letter: string; color: string; feedback: string } {
  const pct = percentage(score, total);

  if (pct >= 90)
    return {
      letter: "S",
      color: "text-green-600",
      feedback: "Excellent work! Your responses show exceptional understanding.",
    };
  if (pct >= 80)
    return {
      letter: "A",
      color: "text-emerald-600",
      feedback: "Very good! You've demonstrated solid knowledge of the material.",
    };
  if (pct >= 70)
    return {
      letter: "B",
      color: "text-blue-600",
      feedback:
        "Good effort. You understand the core concepts but there's room for improvement.",
    };
  if (pct >= 60)
    return {
      letter: "C",
      color: "text-amber-600",
      feedback:
        "You've grasped some concepts, but need to work on your understanding.",
    };
  if (pct >= 50)
    return {
      letter: "D",
      color: "text-yellow-600",
      feedback: "Your understanding is below average. Please review the material.",
    };
  return {
    letter: "F",
    color: "text-red-600",
    feedback:
      "Your understanding needs significant improvement. Please review the material.",
  };
}

/** Badge colour for a mark, by the share of the maximum that was earned. */
export function scoreColor(obtained: number, total: number): string {
  const pct = percentage(obtained, total);
  if (pct >= 80) return "bg-green-500";
  if (pct >= 60) return "bg-emerald-500";
  if (pct >= 40) return "bg-yellow-500";
  return "bg-red-500";
}
