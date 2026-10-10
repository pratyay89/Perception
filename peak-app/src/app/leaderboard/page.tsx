"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, RefreshCw, Trophy } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { formatMarks, num } from "@/lib/format";
import type { ClassLeaderboard, ClassLeaderboardEntry } from "@/lib/types";
import { Loading } from "@/components/loading";
import { GraphSearchCanvas } from "@/components/graph-search-canvas";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  LeaderboardList,
  LeaderboardSkeleton,
  RankBadge,
} from "@/components/leaderboard";
import { cn } from "@/lib/utils";

function papersText(count: number): string {
  return `${count} ${count === 1 ? "paper" : "papers"}`;
}

/** The top three, side by side, with the winner raised in the middle. */
function Podium({ entries }: { entries: ClassLeaderboardEntry[] }) {
  const top = entries.slice(0, 3);
  if (top.length < 2) return null;
  // Second, first, third
  const order = [top[1], top[0], top[2]].filter(Boolean);
  // Taller for a better rank, so tied students stand at the same height
  const heights: Record<number, string> = {
    1: "sm:h-36",
    2: "sm:h-28",
    3: "sm:h-20",
  };

  return (
    <div className="grid grid-cols-3 items-end gap-3 border-b px-4 pb-6 pt-8 sm:px-6">
      {order.map((entry, i) => (
        <motion.div
          key={`${entry.full_name}-${entry.rank}-${i}`}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: [0.15, 0, 0.3][i] }}
          className="flex flex-col items-center text-center"
        >
          <RankBadge rank={entry.rank} />
          <p className="mt-2 w-full truncate text-sm font-semibold">
            {entry.full_name}
            {entry.is_you && (
              <span className="text-muted-foreground"> (you)</span>
            )}
          </p>
          <p className="text-xs tabular-nums text-muted-foreground">
            {num(entry.percentage).toFixed(1)}%
          </p>
          <div
            className={cn(
              "mt-3 h-12 w-full rounded-t-lg border border-b-0 bg-muted/60",
              heights[entry.rank],
              entry.rank === 1 && "bg-primary/10",
            )}
          />
        </motion.div>
      ))}
    </div>
  );
}

function ClassBoard({
  board,
  isTeacher,
}: {
  board: ClassLeaderboard;
  isTeacher: boolean;
}) {
  const you = board.entries.find((e) => e.is_you);
  return (
    <Card className="overflow-hidden shadow-sm">
      <CardHeader className="border-b bg-muted/50">
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5" />
          {isTeacher ? "Your class" : `${board.teacher_name}'s class`}
        </CardTitle>
        <CardDescription>
          Ranked by percentage across {papersText(board.papers_count)}, counting
          only evaluated results
          {you ? ` · you are #${you.rank} of ${board.entries.length}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {board.entries.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            No evaluated results yet. Students appear here once their answers
            are graded.
          </p>
        ) : (
          <>
            <Podium entries={board.entries} />
            <LeaderboardList
              rows={board.entries.map((entry, i) => ({
                key: entry.s_email ?? `${entry.full_name}-${i}`,
                rank: entry.rank,
                name: entry.full_name,
                email: entry.is_you ? null : entry.s_email,
                isYou: entry.is_you,
                detail: `${papersText(entry.papers_evaluated)} evaluated`,
                score: `${formatMarks(entry.marks_obtained)} / ${formatMarks(entry.total_marks)}`,
                percentage: num(entry.percentage),
              }))}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function LeaderboardPage() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [boards, setBoards] = useState<ClassLeaderboard[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await api.get<ClassLeaderboard[]>("/leaderboard");
      setBoards(response.data);
    } catch (error) {
      toast.error(errorMessage(error, "Could not load the leaderboard"));
      setBoards((current) => current ?? []);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  if (loading || !session) return <Loading />;
  const isTeacher = session.role === "teacher";

  return (
    <div className="relative isolate min-h-screen bg-background">
      <div className="fixed inset-0 -z-10">
        <GraphSearchCanvas variant="subtle" />
      </div>
      <header className="sticky top-0 z-10 border-b bg-card">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4 sm:px-6">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5"
            onClick={() => router.push("/dashboard")}
          >
            <ArrowLeft className="h-4 w-4" /> Dashboard
          </Button>
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <Trophy className="h-5 w-5" /> Leaderboard
          </h1>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={load}
              aria-label="Refresh"
              className={refreshing ? "animate-spin" : ""}
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        {boards === null ? (
          <Card>
            <LeaderboardSkeleton />
          </Card>
        ) : boards.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              You are not in a class yet. Ask your teacher to add your email.
            </CardContent>
          </Card>
        ) : (
          boards.map((board) => (
            <ClassBoard
              key={board.t_email}
              board={board}
              isTeacher={isTeacher}
            />
          ))
        )}
      </main>
    </div>
  );
}
