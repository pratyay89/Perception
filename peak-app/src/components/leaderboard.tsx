"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Medal, Trophy } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { formatMarks, num } from "@/lib/format";
import type { PaperLeaderboard } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface LeaderboardRow {
  key: string;
  rank: number;
  name: string;
  email: string | null;
  isYou: boolean;
  /** Main figure on the right, e.g. "12 / 15" */
  score: string;
  /** Small text under the name, e.g. "3 papers" */
  detail?: string;
  percentage: number;
}

const MEDAL_STYLES: Record<number, string> = {
  1: "bg-amber-100 text-amber-700 ring-amber-300/60",
  2: "bg-muted text-foreground ring-border",
  3: "bg-orange-100 text-orange-700 ring-orange-300/60 dark:bg-orange-500/15 dark:text-orange-300",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters =
    parts.length > 1 ? parts[0][0] + parts.at(-1)![0] : name.slice(0, 2);
  return letters.toUpperCase();
}

export function RankBadge({ rank }: { rank: number }) {
  if (rank <= 3) {
    return (
      <span
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1",
          MEDAL_STYLES[rank],
        )}
        aria-label={`Rank ${rank}`}
      >
        {rank === 1 ? (
          <Trophy className="h-4 w-4" />
        ) : (
          <Medal className="h-4 w-4" />
        )}
      </span>
    );
  }
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center font-mono text-sm text-muted-foreground">
      #{rank}
    </span>
  );
}

/** Ranked rows, best first, with the viewer's own row highlighted. */
export function LeaderboardList({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <ol className="divide-y divide-border">
      {rows.map((row, i) => (
        <motion.li
          key={row.key}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: Math.min(i, 10) * 0.03 }}
          className={cn(
            "flex items-center gap-3 px-4 py-3 sm:px-6",
            row.isYou && "bg-primary/[0.06]",
          )}
        >
          <RankBadge rank={row.rank} />
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
            {initials(row.name)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="truncate font-medium">{row.name}</p>
              {row.isYou && (
                <Badge
                  variant="outline"
                  className="h-5 px-1.5 text-[10px] uppercase"
                >
                  You
                </Badge>
              )}
            </div>
            {(row.email || row.detail) && (
              <p className="truncate text-xs text-muted-foreground">
                {[row.email, row.detail].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
          <div className="hidden w-32 sm:block" aria-hidden="true">
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{
                  width: `${Math.max(0, Math.min(100, row.percentage))}%`,
                }}
              />
            </div>
          </div>
          <div className="w-20 shrink-0 text-right">
            <p className="font-semibold tabular-nums">
              {row.percentage.toFixed(1)}%
            </p>
            <p className="text-xs tabular-nums text-muted-foreground">
              {row.score}
            </p>
          </div>
        </motion.li>
      ))}
    </ol>
  );
}

export function LeaderboardSkeleton() {
  return (
    <div className="space-y-3 p-6">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-8 w-8 rounded-full" />
          <Skeleton className="h-9 w-9 rounded-full" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

/** Ranking of one paper's evaluated submissions. */
export function PaperLeaderboardCard({ qpid }: { qpid: string | number }) {
  const [board, setBoard] = useState<PaperLeaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<PaperLeaderboard>(`/leaderboard/papers/${qpid}`)
      .then((response) => !cancelled && setBoard(response.data))
      .catch(
        (err) =>
          !cancelled &&
          setError(errorMessage(err, "Could not load the leaderboard")),
      );
    return () => {
      cancelled = true;
    };
  }, [qpid]);

  const ranked = board?.entries.length ?? 0;
  const pending = board?.pending_count ?? 0;

  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b bg-muted/50">
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5" /> Leaderboard
        </CardTitle>
        <CardDescription>
          {board
            ? `${ranked} ranked${pending ? ` · ${pending} awaiting evaluation` : ""}`
            : "Ranked by marks on this paper"}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {error ? (
          <p className="p-6 text-sm text-muted-foreground">{error}</p>
        ) : !board ? (
          <LeaderboardSkeleton />
        ) : ranked === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            No evaluated submissions yet. The ranking appears once answers are
            graded.
          </p>
        ) : (
          <LeaderboardList
            rows={board.entries.map((entry, i) => ({
              key: entry.s_email ?? `${entry.full_name}-${i}`,
              rank: entry.rank,
              name: entry.full_name,
              email: entry.is_you ? null : entry.s_email,
              isYou: entry.is_you,
              score: `${formatMarks(entry.marks_obtained)} / ${formatMarks(board.total_marks)}`,
              percentage: num(entry.percentage),
            }))}
          />
        )}
      </CardContent>
    </Card>
  );
}
