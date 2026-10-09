"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, formatMarks, STATUS_LABEL } from "@/lib/format";
import type { PaperEvaluation, PaperSummary } from "@/lib/types";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  BookOpen,
  MoreVertical,
  Loader2,
  Calendar,
  CheckCircle,
  PencilLine,
  Clock,
  FileCheck,
  AlertTriangle,
  XCircle,
  RefreshCcw,
  ArrowRight,
  Delete,
  FileEdit,
  Send,
} from "lucide-react";

interface QPCardProps {
  paper: PaperSummary;
  user_type: "student" | "teacher";
  /** Called after an action changed the paper, so the list can be reloaded. */
  onChanged?: () => void;
}

/** True when every submission of the paper has been evaluated. */
export function isFullyEvaluated(paper: PaperSummary): boolean {
  const submissions = paper.submission_count ?? 0;
  return submissions > 0 && paper.evaluated_count === submissions;
}

export function QPCard({ paper, user_type, onChanged }: QPCardProps) {
  const router = useRouter();
  const id = paper.qpid;
  const { title, status } = paper;
  const expired = status === "closed";
  const attempted = Boolean(paper.attempted);
  const submissionCount = paper.submission_count ?? 0;
  const evaluated =
    user_type === "teacher" ? isFullyEvaluated(paper) : Boolean(paper.evaluated);

  const [viewLoading, setViewLoading] = useState(false);
  const [evaluateLoading, setEvaluateLoading] = useState(false);
  const [expireLoading, setExpireLoading] = useState(false);
  const [unexpireLoading, setUnexpireLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [publishLoading, setPublishLoading] = useState(false);

  // Dialog states
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [showExpireDialog, setShowExpireDialog] = useState(false);
  const [showUnexpireDialog, setShowUnexpireDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // Evaluate every submission of the paper (only for teachers)
  const handleEvaluateClick = async () => {
    setEvaluateLoading(true);
    const toastId = toast.loading(
      "Evaluating submissions with AI. This can take a minute..."
    );
    try {
      const { data } = await api.post<PaperEvaluation>(`/evaluations/${id}`);
      if (data.message) {
        // Some answers failed or are still pending (e.g. rate limit reached)
        toast.warning(
          `${data.evaluated_count} of ${data.submission_count} submissions evaluated. ${data.message}`,
          { id: toastId, duration: 10000 }
        );
      } else {
        toast.success(
          `Evaluation successful: ${data.evaluated_count} of ${data.submission_count} submissions evaluated`,
          { id: toastId }
        );
      }
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Evaluation failed"), { id: toastId });
    } finally {
      setEvaluateLoading(false);
    }
  };

  // View the paper (only for teachers and attempted papers for students)
  const handleViewClick = () => {
    setViewLoading(true);
    router.push(`/view-paper/${id}`);
  };

  // Reset the evaluation (only for teachers)
  const handleResetClick = async () => {
    setResetLoading(true);
    try {
      await api.delete(`/evaluations/${id}`);
      toast.success("Evaluation reset successfully");
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Reset failed"));
    } finally {
      setResetLoading(false);
      setShowResetDialog(false);
    }
  };

  // Stop accepting submissions (only for teachers)
  const handleExpireClick = async () => {
    setExpireLoading(true);
    try {
      await api.patch(`/papers/${id}`, { is_closed: true });
      toast.success("Paper set as expired!");
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Expire failed"));
    } finally {
      setExpireLoading(false);
      setShowExpireDialog(false);
    }
  };

  // Accept submissions again (only for teachers)
  const handleUnexpireClick = async () => {
    setUnexpireLoading(true);
    try {
      await api.patch(`/papers/${id}`, { is_closed: false });
      toast.success("Paper set as active!");
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Unexpire failed"));
    } finally {
      setUnexpireLoading(false);
      setShowUnexpireDialog(false);
    }
  };

  // Publish a draft (only for teachers)
  const handlePublishClick = async () => {
    setPublishLoading(true);
    try {
      await api.patch(`/papers/${id}`, { is_published: true });
      toast.success("Paper published!");
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Publish failed"));
    } finally {
      setPublishLoading(false);
    }
  };

  // Delete the paper (only for teachers)
  const handleDeleteClick = async () => {
    try {
      await api.delete(`/papers/${id}`);
      toast.success("Paper deleted successfully");
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, "Delete failed"));
    }
  };

  const statusBadge = (() => {
    switch (status) {
      case "closed":
        return (
          <Badge variant="destructive" className="flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            <span>Expired</span>
          </Badge>
        );
      case "draft":
        return (
          <Badge variant="outline" className="flex items-center gap-1">
            <FileEdit className="h-3 w-3" />
            <span>{STATUS_LABEL.draft}</span>
          </Badge>
        );
      case "scheduled":
        return (
          <Badge
            variant="outline"
            className="flex items-center gap-1 bg-amber-50 text-amber-700"
          >
            <Calendar className="h-3 w-3" />
            <span>{STATUS_LABEL.scheduled}</span>
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary" className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            <span>{STATUS_LABEL.open}</span>
          </Badge>
        );
    }
  })();

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <Card
          className="overflow-hidden transition-all hover:shadow-md relative border-t-4 border-t-primary/70"
          role="article"
          aria-labelledby={`paper-title-${id}`}
        >
          {/* Top-right status indicators */}
          <div className="absolute top-2 right-2 flex gap-1.5">
            {statusBadge}

            {evaluated && (
              <Badge
                variant="outline"
                className="flex items-center gap-1 bg-green-50"
              >
                <CheckCircle className="h-3 w-3 text-green-600" />
                <span className="text-green-600">Evaluated</span>
              </Badge>
            )}

            {user_type === "student" && (
              <Badge
                variant={attempted ? "secondary" : "outline"}
                className={
                  attempted ? "bg-blue-100 text-blue-700 hover:bg-blue-200" : ""
                }
              >
                {attempted ? "Attempted" : "Not Attempted"}
              </Badge>
            )}
          </div>

          <CardHeader className="pt-10">
            <div className="flex items-start gap-3">
              <div className="rounded-md bg-primary/10 p-2 mt-0.5">
                <BookOpen className="h-5 w-5 text-primary" />
              </div>
              <div className="space-y-1">
                <CardTitle
                  id={`paper-title-${id}`}
                  className="text-xl font-bold line-clamp-2"
                >
                  {title}
                </CardTitle>
                <CardDescription>
                  {user_type === "teacher"
                    ? "Created by you"
                    : paper.teacher_name
                    ? `Assigned by ${paper.teacher_name}`
                    : "Assigned to you"}
                </CardDescription>
              </div>
            </div>
          </CardHeader>

          <CardContent className="text-sm text-gray-600 space-y-1">
            <p>
              {paper.question_count} question
              {paper.question_count === 1 ? "" : "s"} ·{" "}
              {formatMarks(paper.total_marks)} marks
              {paper.duration_minutes
                ? ` · ${paper.duration_minutes} min`
                : ""}
            </p>
            {status === "scheduled" && (
              <p>Opens {formatDateTime(paper.start_date)}</p>
            )}
            {user_type === "teacher" && status !== "draft" && (
              <p>
                {submissionCount} submission{submissionCount === 1 ? "" : "s"}
                {submissionCount > 0
                  ? ` · ${paper.evaluated_count ?? 0} evaluated`
                  : ""}
              </p>
            )}
            {user_type === "student" &&
              evaluated &&
              paper.marks_obtained !== null && (
                <p className="font-medium text-gray-900">
                  Score: {formatMarks(paper.marks_obtained)} /{" "}
                  {formatMarks(paper.total_marks)}
                </p>
              )}
          </CardContent>

          <CardFooter className="flex justify-between items-center border-t bg-gray-50/60 p-3">
            {user_type === "student" && status === "open" && !attempted && (
              <Button
                onClick={() => router.push(`/attempt-paper/${id}`)}
                className="flex items-center gap-2"
              >
                <PencilLine className="h-4 w-4" />
                Attempt
              </Button>
            )}
            {user_type === "student" && status !== "open" && !attempted && (
              <Button
                disabled
                className="flex items-center gap-2"
                title={
                  status === "scheduled"
                    ? "Paper has not started yet"
                    : "Paper is expired"
                }
              >
                {status === "scheduled" ? "Not Started" : "Not Attempted"}
              </Button>
            )}
            {user_type === "student" && attempted && (
              <Button
                onClick={() => router.push(`/view-paper/${id}`)}
                className="flex items-center gap-2"
              >
                <FileCheck className="h-4 w-4" />
                View Attempt
              </Button>
            )}
            {user_type === "teacher" && (
              <Button
                onClick={handleViewClick}
                disabled={viewLoading}
                variant="default"
                className="flex items-center gap-1.5"
              >
                {viewLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Loading...</span>
                  </>
                ) : (
                  <>
                    <FileCheck className="h-4 w-4" />
                    <span>View & Manage</span>
                    <ArrowRight className="h-3 w-3 ml-1" />
                  </>
                )}
              </Button>
            )}
            {user_type === "teacher" && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-full h-8 w-8"
                    aria-label={`Actions for ${title}`}
                  >
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-52">
                  {status === "draft" ? (
                    <DropdownMenuItem
                      onClick={handlePublishClick}
                      disabled={publishLoading}
                      className="flex items-center gap-2 text-emerald-600 focus:text-emerald-700 cursor-pointer"
                    >
                      <Send className="h-4 w-4" />
                      <span>Publish</span>
                    </DropdownMenuItem>
                  ) : evaluated ? (
                    <DropdownMenuItem
                      onClick={() => setShowResetDialog(true)}
                      className="flex items-center gap-2 text-red-600 focus:text-red-700 cursor-pointer"
                    >
                      <AlertTriangle className="h-4 w-4" />
                      <span>Reset Evaluation</span>
                    </DropdownMenuItem>
                  ) : (
                    <DropdownMenuItem
                      onClick={handleEvaluateClick}
                      disabled={evaluateLoading || submissionCount === 0}
                      className="flex items-center gap-2 text-emerald-600 focus:text-emerald-700 cursor-pointer"
                    >
                      {evaluateLoading ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Evaluating...</span>
                        </>
                      ) : (
                        <>
                          <CheckCircle className="h-4 w-4" />
                          <span>
                            {submissionCount === 0
                              ? "No Submissions Yet"
                              : "Evaluate Papers"}
                          </span>
                        </>
                      )}
                    </DropdownMenuItem>
                  )}

                  <DropdownMenuSeparator />

                  <DropdownMenuItem
                    onClick={() => router.push(`/edit-paper/${id}`)}
                    className="flex items-center gap-2 cursor-pointer"
                  >
                    <FileEdit className="h-4 w-4" />
                    <span>Edit</span>
                  </DropdownMenuItem>

                  {status !== "draft" &&
                    (!expired ? (
                      <DropdownMenuItem
                        onClick={() => setShowExpireDialog(true)}
                        className="flex items-center gap-2 text-amber-600 focus:text-amber-700 cursor-pointer"
                      >
                        <Calendar className="h-4 w-4" />
                        <span>Mark as Expired</span>
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem
                        onClick={() => setShowUnexpireDialog(true)}
                        className="flex items-center gap-2 text-green-600 focus:text-green-700 cursor-pointer"
                      >
                        <RefreshCcw className="h-4 w-4" />
                        <span>Reactivate Paper</span>
                      </DropdownMenuItem>
                    ))}

                  <DropdownMenuItem
                    onClick={() => setShowDeleteDialog(true)}
                    className="flex items-center gap-2 text-red-500 focus:text-red-600 cursor-pointer"
                  >
                    <Delete className="h-4 w-4" />
                    <span>Delete</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </CardFooter>
        </Card>
      </motion.div>

      {/* Reset Confirmation Dialog */}
      <AlertDialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Evaluation?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove all marks and feedback for this paper. The
              students&apos; answers are kept. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resetLoading}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleResetClick();
              }}
              className="bg-red-600 hover:bg-red-700"
              disabled={resetLoading}
            >
              {resetLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Resetting...
                </>
              ) : (
                "Yes, Reset"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Expire Confirmation Dialog */}
      <AlertDialog open={showExpireDialog} onOpenChange={setShowExpireDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark Paper as Expired?</AlertDialogTitle>
            <AlertDialogDescription>
              This will prevent students from attempting this paper. You can
              reactivate it later if needed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={expireLoading}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleExpireClick();
              }}
              className="bg-amber-600 hover:bg-amber-700"
              disabled={expireLoading}
            >
              {expireLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Expiring...
                </>
              ) : (
                "Yes, Expire"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Unexpire Confirmation Dialog */}
      <AlertDialog
        open={showUnexpireDialog}
        onOpenChange={setShowUnexpireDialog}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reactivate Paper?</AlertDialogTitle>
            <AlertDialogDescription>
              This will reopen the paper, allowing students who have not
              answered yet to attempt it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unexpireLoading}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleUnexpireClick();
              }}
              className="bg-green-600 hover:bg-green-700"
              disabled={unexpireLoading}
            >
              {unexpireLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Reactivating...
                </>
              ) : (
                "Yes, Reactivate"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Paper?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the paper and all associated data,
              including every student submission. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteClick}
              className="bg-red-600 hover:bg-red-700"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
