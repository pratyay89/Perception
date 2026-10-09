"use client";
import { useCallback, useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { formatMarks } from "@/lib/format";
import type { PaperDetail, SubmissionSummary } from "@/lib/types";
import { motion, AnimatePresence } from "framer-motion";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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
import { toast } from "sonner";
import { Loading } from "@/components/loading";

import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Clock,
  FileQuestion,
  Save,
  PenLine,
  AlertTriangle,
  Bookmark,
  BookmarkCheck,
  HelpCircle,
} from "lucide-react";

// The server rejects longer answers
const MAX_ANSWER_LENGTH = 20000;

interface Question {
  // Position in the paper (1, 2, 3, ...), used as the key in the UI
  order: number;
  // The question's id on the server
  qid: number;
  question: string;
  marks: string;
}

interface Paper {
  title: string;
  durationMinutes: number | null;
  questions: Question[];
}

// What is kept in the browser while the student is writing. Answers are only
// sent to the server when the paper is submitted.
interface Draft {
  startedAt: number;
  answers: { [qid: number]: string };
}

function readDraft(key: string): Draft | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (typeof draft.startedAt !== "number" || !draft.answers) return null;
    return draft;
  } catch {
    return null;
  }
}

function formatRemaining(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(seconds)}`
    : `${pad(minutes)}:${pad(seconds)}`;
}

export default function AttemptPage() {
  const params = useParams();
  const router = useRouter();
  const { session } = useSession({ role: "student" });
  const email = session?.email ?? null;
  const paperId = typeof params.id === "string" ? params.id : "";
  const draftKey = email ? `perception:draft:${email}:${paperId}` : null;

  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [answers, setAnswers] = useState<{ [key: number]: string }>({});
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [showSubmitDialog, setShowSubmitDialog] = useState(false);
  const [savedStatus, setSavedStatus] = useState<{ [key: number]: boolean }>(
    {}
  );
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const submittedRef = useRef(false);

  // Write the current answers to this browser's storage
  const saveDraft = useCallback(
    (currentAnswers: { [order: number]: string }): boolean => {
      if (!draftKey || !paper || startedAt === null || submittedRef.current) {
        return false;
      }
      const byQid: { [qid: number]: string } = {};
      paper.questions.forEach((q) => {
        if (currentAnswers[q.order]) byQid[q.qid] = currentAnswers[q.order];
      });
      try {
        const draft: Draft = { startedAt, answers: byQid };
        window.localStorage.setItem(draftKey, JSON.stringify(draft));
        return true;
      } catch {
        return false;
      }
    },
    [draftKey, paper, startedAt]
  );

  // Auto-save shortly after the student stops typing
  useEffect(() => {
    // Cleared answers count too, so an old draft cannot come back later
    const hasUnsaved = Object.keys(answers).some(
      (order) => savedStatus[Number(order)] === false
    );
    if (!hasUnsaved) return;

    const timer = setTimeout(() => {
      if (saveDraft(answers)) {
        const allSaved: { [key: number]: boolean } = {};
        Object.keys(answers).forEach((order) => {
          allSaved[Number(order)] = true;
        });
        setSavedStatus(allSaved);
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, [answers, savedStatus, saveDraft]);

  // Load the paper, and any draft left in this browser
  useEffect(() => {
    if (!email || !draftKey) return;
    let mounted = true;

    const fetchPaper = async () => {
      try {
        // A paper can be answered only once
        const existing = await api.get<SubmissionSummary[]>(
          `/submissions/${paperId}`
        );
        if (existing.data.length > 0) {
          toast.info("You have already submitted this paper");
          router.replace(`/view-paper/${paperId}`);
          return;
        }

        const { data } = await api.get<PaperDetail>(`/papers/${paperId}`);
        if (!mounted) return;

        if (data.status !== "open") {
          toast.error("This paper is not accepting submissions");
          router.replace("/dashboard");
          return;
        }

        const questions: Question[] = data.questions.map((q, index) => ({
          order: index + 1,
          qid: q.qid,
          question: q.question_text,
          marks: q.marks_assigned,
        }));

        const draft = readDraft(draftKey);
        if (draft) {
          const restored: { [order: number]: string } = {};
          const saved: { [order: number]: boolean } = {};
          questions.forEach((q) => {
            if (draft.answers[q.qid]) {
              restored[q.order] = draft.answers[q.qid];
              saved[q.order] = true;
            }
          });
          setAnswers(restored);
          setSavedStatus(saved);
          if (Object.keys(restored).length > 0) {
            toast.info("Restored the answers you wrote earlier on this device");
          }
        }
        setStartedAt(draft?.startedAt ?? Date.now());
        setPaper({
          title: data.title,
          durationMinutes: data.duration_minutes,
          questions,
        });
      } catch (error) {
        toast.error(errorMessage(error, "Failed to load paper"));
        router.replace("/dashboard");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchPaper();

    return () => {
      mounted = false;
    };
  }, [paperId, email, draftKey, router]);

  // Remember when the attempt started, so the timer survives a page reload
  useEffect(() => {
    if (!draftKey || !paper || startedAt === null) return;
    if (!readDraft(draftKey)) saveDraft({});
  }, [draftKey, paper, startedAt, saveDraft]);

  // Tick once a second while there is a time limit
  useEffect(() => {
    if (!paper?.durationMinutes) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [paper?.durationMinutes]);

  // Focus textarea when changing questions
  useEffect(() => {
    if (textareaRef.current) {
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 100);
    }
  }, [currentQuestion]);

  const handleAnswerChange = (order: number, value: string) => {
    setAnswers((prev) => ({ ...prev, [order]: value }));
    setSavedStatus((prev) => ({ ...prev, [order]: false }));
  };

  const handleSaveAnswer = (order: number) => {
    if (!answers[order] || answers[order].trim() === "") {
      toast.info("Nothing to save");
      return;
    }

    if (saveDraft(answers)) {
      setSavedStatus((prev) => ({ ...prev, [order]: true }));
      toast.success("Answer saved on this device");
    } else {
      toast.error("Could not save. Is browser storage disabled or full?");
    }
  };

  const handleSubmit = () => {
    if (!email || !paper) return;
    // The dialog warns about unanswered questions before the final submit
    setShowSubmitDialog(true);
  };

  const confirmSubmit = async () => {
    if (!email || !paper) return;

    setSubmitting(true);
    try {
      await api.post(`/submissions/${paperId}`, {
        answers: paper.questions.map((q) => ({
          qid: q.qid,
          student_answer: answers[q.order] || "",
        })),
      });

      submittedRef.current = true;
      if (draftKey) window.localStorage.removeItem(draftKey);

      toast.success("Paper submitted successfully!");
      router.push("/dashboard");
    } catch (error) {
      toast.error(errorMessage(error, "Failed to submit paper"));
      setShowSubmitDialog(false);
    } finally {
      setSubmitting(false);
    }
  };

  const goToNextQuestion = () => {
    if (!paper) return;
    if (currentQuestion < paper.questions.length - 1) {
      setCurrentQuestion(currentQuestion + 1);
    }
  };

  const goToPreviousQuestion = () => {
    if (currentQuestion > 0) {
      setCurrentQuestion(currentQuestion - 1);
    }
  };

  // Calculate progress
  const getProgress = () => {
    if (!paper || paper.questions.length === 0) return 0;
    const answeredQuestions = paper.questions.filter(
      (q) => answers[q.order] && answers[q.order].trim() !== ""
    ).length;
    return (answeredQuestions / paper.questions.length) * 100;
  };

  if (loading || !paper) return <Loading />;
  const currentQ = paper.questions[currentQuestion];

  const remainingMs =
    paper.durationMinutes && startedAt !== null
      ? startedAt + paper.durationMinutes * 60_000 - now
      : null;
  const timeIsUp = remainingMs !== null && remainingMs <= 0;

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 pb-8">
      {/* Header */}
      <div className="bg-white border-b sticky top-0 z-10 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <Button
                variant="ghost"
                size="sm"
                className="mb-2 text-primary hover:text-primary/90 transition-colors"
                onClick={() => router.push("/dashboard")}
              >
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Dashboard
              </Button>
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
                {paper.title}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <Badge
                variant="outline"
                className={
                  timeIsUp
                    ? "bg-red-50 text-red-700 border-red-200"
                    : "bg-blue-50 text-blue-700 border-blue-200"
                }
              >
                <Clock className="h-3.5 w-3.5 mr-1" />
                {remainingMs === null
                  ? "In Progress"
                  : timeIsUp
                  ? "Time is up"
                  : `${formatRemaining(remainingMs)} left`}
              </Badge>
              <Button
                size="sm"
                className="bg-green-600 hover:bg-green-700"
                onClick={handleSubmit}
              >
                <CheckCircle className="h-4 w-4 mr-1.5" />
                Submit Paper
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        {timeIsUp && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-800 flex items-start">
            <AlertTriangle className="h-5 w-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" />
            <span className="text-sm">
              The time limit of {paper.durationMinutes} minutes is over. Please
              submit your paper now.
            </span>
          </div>
        )}
        <div className="bg-white rounded-md border shadow-sm p-4 mb-6">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium text-gray-700">
              Your Progress
            </span>
            <span className="text-sm font-medium text-gray-700">
              {
                paper.questions.filter(
                  (q) => answers[q.order] && answers[q.order].trim() !== ""
                ).length
              }
              /{paper.questions.length} Questions Answered
            </span>
          </div>
          <Progress value={getProgress()} className="h-2" />
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-12 gap-6">
          {/* Question Navigator */}
          <div className="col-span-12 md:col-span-3">
            <Card className="sticky top-28">
              <CardHeader className="py-3 px-4 bg-gray-50 border-b">
                <CardTitle className="text-sm flex items-center gap-1.5">
                  <FileQuestion className="h-4 w-4 text-gray-500" />
                  Questions
                </CardTitle>
              </CardHeader>
              <CardContent className="p-2">
                <div className="grid grid-cols-3 md:grid-cols-1 gap-2">
                  {paper.questions.map((q, index) => {
                    const isAnswered =
                      answers[q.order] && answers[q.order].trim() !== "";
                    const isActive = index === currentQuestion;

                    return (
                      <Button
                        key={q.order}
                        variant={
                          isActive
                            ? "default"
                            : isAnswered
                            ? "outline"
                            : "ghost"
                        }
                        size="sm"
                        className={`justify-start ${
                          isAnswered && !isActive
                            ? "bg-green-50 border-green-200 text-green-700"
                            : ""
                        }`}
                        onClick={() => setCurrentQuestion(index)}
                      >
                        {isAnswered ? (
                          <BookmarkCheck className="h-3.5 w-3.5 mr-2" />
                        ) : (
                          <Bookmark className="h-3.5 w-3.5 mr-2" />
                        )}
                        Q{q.order}
                      </Button>
                    );
                  })}
                </div>
              </CardContent>
              <CardFooter className="border-t bg-gray-50/80 p-3 flex justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={handleSubmit}
                >
                  <CheckCircle className="h-4 w-4 mr-1.5" />
                  Submit All
                </Button>
              </CardFooter>
            </Card>
          </div>

          {/* Current Question */}
          <div className="col-span-12 md:col-span-9">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentQuestion}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
              >
                <Card className="shadow-sm">
                  <CardHeader className="border-b bg-gradient-to-r from-blue-50 to-indigo-50">
                    <div className="flex justify-between">
                      <Badge variant="outline" className="mb-1 bg-white">
                        Question {currentQ.order} of {paper.questions.length} ·{" "}
                        {formatMarks(currentQ.marks)} marks
                      </Badge>
                      {savedStatus[currentQ.order] && (
                        <Badge
                          variant="outline"
                          className="bg-green-50 text-green-700 border-green-200"
                        >
                          <CheckCircle className="h-3 w-3 mr-1" /> Saved
                        </Badge>
                      )}
                    </div>
                    <CardTitle className="text-xl">
                      {currentQ.question}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 space-y-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <label
                          htmlFor="answer"
                          className="text-sm font-medium text-gray-700 flex items-center gap-1.5"
                        >
                          <PenLine className="h-4 w-4 text-gray-500" />
                          Your Answer
                        </label>
                        <div className="text-xs text-gray-500">
                          Press Ctrl+Enter to save
                        </div>
                      </div>
                      <Textarea
                        id="answer"
                        ref={textareaRef}
                        placeholder="Type your answer here..."
                        className="min-h-[250px] resize-y"
                        maxLength={MAX_ANSWER_LENGTH}
                        value={answers[currentQ.order] || ""}
                        onChange={(e) =>
                          handleAnswerChange(currentQ.order, e.target.value)
                        }
                        onKeyDown={(e) => {
                          if (e.ctrlKey && e.key === "Enter") {
                            handleSaveAnswer(currentQ.order);
                          }
                        }}
                      />
                    </div>
                  </CardContent>
                  <CardFooter className="border-t bg-gray-50 p-4 flex flex-wrap justify-between gap-4">
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={goToPreviousQuestion}
                        disabled={currentQuestion === 0}
                      >
                        <ArrowLeft className="h-4 w-4 mr-1" />
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={goToNextQuestion}
                        disabled={
                          currentQuestion === paper.questions.length - 1
                        }
                      >
                        Next
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </Button>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleSaveAnswer(currentQ.order)}
                        disabled={
                          !answers[currentQ.order] ||
                          savedStatus[currentQ.order]
                        }
                      >
                        <Save className="h-4 w-4 mr-1.5" />
                        Save Answer
                      </Button>
                      {currentQuestion === paper.questions.length - 1 && (
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          onClick={handleSubmit}
                        >
                          <CheckCircle className="h-4 w-4 mr-1.5" />
                          Submit Paper
                        </Button>
                      )}
                    </div>
                  </CardFooter>
                </Card>
              </motion.div>
            </AnimatePresence>

            {/* Tips Card */}
            <Card className="mt-4 bg-blue-50 border-blue-200">
              <CardContent className="p-4 flex">
                <HelpCircle className="h-5 w-5 text-blue-600 mr-3 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-medium text-blue-800 mb-1">Tips</h3>
                  <ul className="text-sm text-blue-700 space-y-1">
                    <li>
                      Your answers are saved automatically in this browser
                      while you type, so a page reload does not lose them. They
                      reach your teacher only when you submit
                    </li>
                    <li>
                      Navigate between questions using the sidebar or
                      previous/next buttons
                    </li>
                    <li>Review all questions before submitting</li>
                  </ul>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Submit confirmation dialog */}
      <AlertDialog open={showSubmitDialog} onOpenChange={setShowSubmitDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit Your Paper?</AlertDialogTitle>
            <AlertDialogDescription>
              You are about to submit your answers. This action cannot be
              undone.
              {paper.questions.some(
                (q) => !answers[q.order] || answers[q.order].trim() === ""
              ) && (
                <span className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded-md text-amber-800 flex items-start">
                  <AlertTriangle className="h-5 w-5 text-amber-500 mr-2 flex-shrink-0 mt-0.5" />
                  <span>
                    You have unanswered questions. They will get 0 marks. Are
                    you sure you want to proceed?
                  </span>
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmSubmit();
              }}
              className="bg-green-600 hover:bg-green-700"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <div className="h-4 w-4 border-2 border-white border-opacity-50 border-t-transparent rounded-full animate-spin mr-2" />
                  Submitting...
                </>
              ) : (
                "Yes, Submit"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
