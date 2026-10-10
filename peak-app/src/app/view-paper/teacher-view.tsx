import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motion } from "framer-motion";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import {
  formatDateTime,
  formatMarks,
  getInitials,
  num,
  percentage,
  scoreColor,
  STATUS_LABEL,
} from "@/lib/format";
import type {
  Answer,
  EvaluationResult,
  PaperDetail,
  SubmissionDetail,
  SubmissionSummary,
} from "@/lib/types";
import { Loading } from "@/components/loading";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Clock,
  CheckCircle2,
  X,
  RefreshCw,
  User,
  BarChart4,
  Loader2,
  Pencil,
  Sparkles,
  RotateCcw,
  FileEdit,
} from "lucide-react";
import { PaperLeaderboardCard } from "@/components/leaderboard";
import { ThemeToggle } from "@/components/theme-toggle";

interface ViewProps {
  id: string;
  email: string;
}

interface EditState {
  qid: number;
  marks: string;
  feedback: string;
}

export function TeacherView({ id }: ViewProps) {
  const router = useRouter();
  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStudent, setSelectedStudent] = useState<string>("");
  const [selectedSubmission, setSelectedSubmission] =
    useState<SubmissionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [editing, setEditing] = useState<EditState | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchSubmissions = useCallback(async () => {
    const { data } = await api.get<SubmissionSummary[]>(`/submissions/${id}`);
    setSubmissions(data);
    return data;
  }, [id]);

  // Load the paper and the list of submissions
  useEffect(() => {
    let mounted = true;

    const fetchPaper = async () => {
      try {
        const [paperRes, list] = await Promise.all([
          api.get<PaperDetail>(`/papers/${id}`),
          fetchSubmissions(),
        ]);
        if (!mounted) return;
        setPaper(paperRes.data);
        if (list.length > 0) {
          setSelectedStudent(list[0].s_email);
        }
      } catch (error) {
        toast.error(errorMessage(error, "An error occurred"));
        router.push("/dashboard");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchPaper();

    return () => {
      mounted = false;
    };
  }, [id, router, fetchSubmissions]);

  // Load the answers of the selected student
  useEffect(() => {
    if (!selectedStudent) {
      setSelectedSubmission(null);
      return;
    }
    let mounted = true;
    setDetailLoading(true);
    setEditing(null);

    api
      .get<SubmissionDetail>(
        `/submissions/${id}/${encodeURIComponent(selectedStudent)}`
      )
      .then(({ data }) => {
        if (mounted) setSelectedSubmission(data);
      })
      .catch((error) => {
        toast.error(errorMessage(error, "Failed to load the submission"));
      })
      .finally(() => {
        if (mounted) setDetailLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [id, selectedStudent]);

  /** Show an updated submission and refresh the totals in the student list. */
  const applyUpdatedSubmission = async (updated: SubmissionDetail) => {
    setSelectedSubmission(updated);
    try {
      await fetchSubmissions();
    } catch {
      // The detail is already up to date; the list refreshes on next load.
    }
  };

  const handleEvaluate = async (force: boolean) => {
    if (!selectedStudent) return;
    setEvaluating(true);
    try {
      const { data } = await api.post<EvaluationResult>(
        `/evaluations/${id}/${encodeURIComponent(selectedStudent)}`,
        null,
        { params: force ? { force: true } : undefined }
      );
      if (data.message) {
        toast.warning(data.message, { duration: 10000 });
      } else {
        toast.success("Evaluation successful");
      }
      await applyUpdatedSubmission(data);
    } catch (error) {
      toast.error(errorMessage(error, "Evaluation failed"));
    } finally {
      setEvaluating(false);
    }
  };

  const handleReset = async () => {
    if (!selectedStudent) return;
    setResetting(true);
    try {
      const { data } = await api.delete<SubmissionDetail>(
        `/evaluations/${id}/${encodeURIComponent(selectedStudent)}`
      );
      toast.success("Evaluation reset for this student");
      await applyUpdatedSubmission(data);
    } catch (error) {
      toast.error(errorMessage(error, "Reset failed"));
    } finally {
      setResetting(false);
    }
  };

  const startEditing = (answer: Answer) => {
    setEditing({
      qid: answer.qid,
      marks: answer.status === "success" ? formatMarks(answer.marks_obtained) : "",
      feedback: answer.feedback || "",
    });
  };

  const saveEdit = async (maxMarks: number) => {
    if (!editing || !selectedStudent) return;

    const marks = editing.marks.trim() === "" ? NaN : Number(editing.marks);
    if (!Number.isFinite(marks) || marks < 0 || marks > maxMarks) {
      toast.error(`Marks must be between 0 and ${formatMarks(maxMarks)}`);
      return;
    }

    setSavingEdit(true);
    try {
      const { data } = await api.patch<SubmissionDetail>(
        `/evaluations/${id}/${encodeURIComponent(selectedStudent)}/${
          editing.qid
        }`,
        { marks_obtained: marks, feedback: editing.feedback }
      );
      toast.success("Marks updated");
      setEditing(null);
      await applyUpdatedSubmission(data);
    } catch (error) {
      toast.error(errorMessage(error, "Could not update the marks"));
    } finally {
      setSavingEdit(false);
    }
  };

  if (loading || !paper) return <Loading />;

  const totalMarks = num(paper.total_marks);
  const hasSubmissions = submissions.length > 0;
  const evaluatedCount = submissions.filter((s) => s.evaluated).length;
  const allEvaluated = hasSubmissions && evaluatedCount === submissions.length;
  const expired = paper.status === "closed";
  const questionNumber = new Map(paper.questions.map((q, i) => [q.qid, i + 1]));
  const questionById = new Map(paper.questions.map((q) => [q.qid, q]));
  const selectedTotal = num(selectedSubmission?.total_marks_obtained);
  const hasGradedAnswer = Boolean(
    selectedSubmission?.answers.some((a) => a.status !== "pending")
  );

  return (
    <div className="space-y-6">
      {/* Paper Header */}
      <div className="bg-card rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div
            className="flex items-center text-primary hover:text-primary/90 transition-colors cursor-pointer"
            onClick={() => router.push("/dashboard")}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            <span className="text-sm font-medium">Back to Dashboard</span>
          </div>
          <ThemeToggle />
        </div>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-foreground">
              {paper.title}
            </h1>
            <div className="flex flex-wrap gap-2 mt-2 items-center">
              <Badge
                variant={expired ? "destructive" : "secondary"}
                className="flex items-center gap-1"
              >
                {expired ? (
                  <>
                    <X className="h-3 w-3" /> Closed
                  </>
                ) : (
                  <>
                    <Clock className="h-3 w-3" /> {STATUS_LABEL[paper.status]}
                  </>
                )}
              </Badge>
              <Badge
                variant={allEvaluated ? "secondary" : "outline"}
                className="flex items-center gap-1"
              >
                {allEvaluated ? (
                  <>
                    <CheckCircle2 className="h-3 w-3" /> Evaluated
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-3 w-3" /> Pending Evaluation
                  </>
                )}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {submissions.length}{" "}
                {submissions.length === 1 ? "submission" : "submissions"}
                {hasSubmissions ? ` · ${evaluatedCount} evaluated` : ""} ·{" "}
                {formatMarks(totalMarks)} marks
              </span>
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              {paper.status === "scheduled" ? "Opens" : "Opened"}{" "}
              {formatDateTime(paper.start_date)}
              {paper.duration_minutes
                ? ` · ${paper.duration_minutes} minute time limit`
                : ""}
            </p>
          </div>
          <Button
            variant="outline"
            className="flex items-center gap-1.5"
            onClick={() => router.push(`/edit-paper/${id}`)}
          >
            <FileEdit className="h-4 w-4" /> Edit Paper
          </Button>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-12 gap-6">
        {/* Questions Panel */}
        <Card className="col-span-12 lg:col-span-4 shadow-sm border">
          <CardHeader className="border-b bg-muted/50">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              Questions ({paper.questions.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {paper.questions.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">
                This paper has no questions yet.
              </p>
            ) : (
              <Tabs defaultValue="0">
                <TabsList className="w-full justify-start border-b rounded-none p-0 h-auto overflow-x-auto flex-nowrap">
                  {paper.questions.map((q, index) => (
                    <TabsTrigger
                      key={q.qid}
                      value={index.toString()}
                      className="data-[state=active]:bg-muted rounded-none border-b-2 data-[state=active]:border-primary"
                    >
                      Q{index + 1}
                    </TabsTrigger>
                  ))}
                </TabsList>

                <div className="py-4 px-6">
                  {paper.questions.map((q, index) => (
                    <TabsContent
                      key={q.qid}
                      value={index.toString()}
                      className="m-0"
                    >
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        <div className="space-y-4">
                          <div>
                            <Badge variant="outline" className="mb-2">
                              Question {index + 1} ·{" "}
                              {formatMarks(q.marks_assigned)} marks
                            </Badge>
                            <p className="text-lg font-medium text-foreground whitespace-pre-wrap">
                              {q.question_text}
                            </p>
                          </div>
                          <Separator />
                          <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-2">
                              Expected Answer
                            </h4>
                            <p className="text-sm bg-muted/50 p-3 rounded border whitespace-pre-wrap">
                              {q.model_answer || (
                                <span className="text-muted-foreground/70 italic">
                                  None provided
                                </span>
                              )}
                            </p>
                          </div>
                          <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-2">
                              Rubric
                            </h4>
                            <p className="text-sm bg-muted/50 p-3 rounded border whitespace-pre-wrap">
                              {q.rubric || (
                                <span className="text-muted-foreground/70 italic">
                                  None provided. The AI grades on accuracy,
                                  completeness, relevance and clarity.
                                </span>
                              )}
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    </TabsContent>
                  ))}
                </div>
              </Tabs>
            )}
          </CardContent>
        </Card>

        {/* Submissions Panel */}
        <Card className="col-span-12 lg:col-span-8 shadow-sm border">
          <CardHeader className="border-b bg-muted/50">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5 text-muted-foreground" />
                Student Submissions
              </CardTitle>
              {hasSubmissions ? (
                <Select
                  value={selectedStudent}
                  onValueChange={setSelectedStudent}
                >
                  <SelectTrigger
                    className="max-w-[300px]"
                    aria-label="Select a student"
                  >
                    <SelectValue placeholder="Select a student" />
                  </SelectTrigger>
                  <SelectContent>
                    {submissions.map((sub) => (
                      <SelectItem key={sub.s_email} value={sub.s_email}>
                        <div className="flex items-center gap-2">
                          <div className="h-6 w-6 rounded-full bg-muted flex items-center justify-center text-xs">
                            {getInitials(sub.s_email)}
                          </div>
                          <span>{sub.student_name || sub.s_email}</span>
                          <span className="text-xs text-muted-foreground">
                            {sub.evaluated
                              ? `${formatMarks(
                                  sub.total_marks_obtained
                                )}/${formatMarks(totalMarks)}`
                              : "not evaluated"}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {hasSubmissions ? (
              selectedSubmission ? (
                <div className="p-6">
                  <div className="bg-muted/50 p-4 rounded-lg mb-6 border">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs">
                            {getInitials(selectedSubmission.s_email)}
                          </div>
                          <div>
                            <h3 className="font-medium">
                              {selectedSubmission.student_name ||
                                selectedSubmission.s_email}
                            </h3>
                            <p className="text-xs text-muted-foreground">
                              {selectedSubmission.s_email} · submitted{" "}
                              {formatDateTime(selectedSubmission.created_at)}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <BarChart4 className="h-5 w-5 text-muted-foreground/70" />
                        <span className="font-bold">
                          Score: {formatMarks(selectedTotal)} /{" "}
                          {formatMarks(totalMarks)}
                        </span>
                      </div>
                    </div>

                    <Progress
                      value={percentage(selectedTotal, totalMarks)}
                      className="h-2"
                    />

                    <div className="flex flex-wrap items-center gap-2 mt-4">
                      {!selectedSubmission.evaluated && (
                        <Button
                          size="sm"
                          onClick={() => handleEvaluate(false)}
                          disabled={evaluating || resetting}
                          className="flex items-center gap-1.5"
                        >
                          {evaluating ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Sparkles className="h-4 w-4" />
                          )}
                          {evaluating ? "Evaluating..." : "Evaluate with AI"}
                        </Button>
                      )}
                      {hasGradedAnswer && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleEvaluate(true)}
                            disabled={evaluating || resetting}
                            className="flex items-center gap-1.5"
                            title="Grade every answer again, replacing the current marks"
                          >
                            <RefreshCw className="h-4 w-4" />
                            Re-evaluate All
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleReset}
                            disabled={evaluating || resetting}
                            className="flex items-center gap-1.5 text-red-600 hover:text-red-700"
                          >
                            <RotateCcw className="h-4 w-4" />
                            {resetting ? "Resetting..." : "Reset"}
                          </Button>
                        </>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {selectedSubmission.evaluated
                          ? "Visible to the student. You can still adjust any mark."
                          : "The student sees marks once every answer is graded."}
                      </span>
                    </div>
                  </div>

                  <div
                    className={`space-y-6 ${
                      detailLoading ? "opacity-50" : ""
                    }`}
                  >
                    {selectedSubmission.answers.map((ans) => {
                      const question = questionById.get(ans.qid);
                      const maxMarks = num(question?.marks_assigned);
                      const marks = num(ans.marks_obtained);
                      const isEditing = editing?.qid === ans.qid;

                      return (
                        <motion.div
                          key={ans.qid}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ duration: 0.3 }}
                        >
                          <Card className="overflow-hidden">
                            <CardHeader className="py-3 px-4 bg-muted/50 border-b">
                              <div className="flex items-center justify-between gap-2">
                                <h3 className="text-sm font-medium">
                                  Question {questionNumber.get(ans.qid) ?? "?"}
                                </h3>
                                <div className="flex items-center gap-2">
                                  {ans.status === "success" ? (
                                    <Badge
                                      variant="outline"
                                      className={`${scoreColor(
                                        marks,
                                        maxMarks
                                      )} text-white`}
                                    >
                                      {formatMarks(marks)}/
                                      {formatMarks(maxMarks)}
                                    </Badge>
                                  ) : ans.status === "failed" ? (
                                    <Badge variant="destructive">
                                      Evaluation failed
                                    </Badge>
                                  ) : (
                                    <Badge variant="outline">
                                      Not evaluated · {formatMarks(maxMarks)}{" "}
                                      marks
                                    </Badge>
                                  )}
                                  {!isEditing && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-7 px-2"
                                      onClick={() => startEditing(ans)}
                                      aria-label={`Edit marks for question ${
                                        questionNumber.get(ans.qid) ?? ""
                                      }`}
                                    >
                                      <Pencil className="h-3.5 w-3.5 mr-1" />
                                      {ans.status === "success"
                                        ? "Edit"
                                        : "Grade"}
                                    </Button>
                                  )}
                                </div>
                              </div>
                            </CardHeader>
                            <CardContent className="p-4">
                              <div className="space-y-4">
                                <div className="bg-muted/50 p-3 rounded border text-sm whitespace-pre-wrap">
                                  {ans.student_answer?.trim() ? (
                                    ans.student_answer
                                  ) : (
                                    <span className="text-muted-foreground/70 italic">
                                      No answer provided
                                    </span>
                                  )}
                                </div>

                                {isEditing && editing ? (
                                  <div className="space-y-3 border rounded p-3 bg-blue-50/40">
                                    <div className="flex items-center gap-2">
                                      <Label
                                        htmlFor={`edit-marks-${ans.qid}`}
                                        className="text-sm"
                                      >
                                        Marks
                                      </Label>
                                      <Input
                                        id={`edit-marks-${ans.qid}`}
                                        type="number"
                                        min={0}
                                        max={maxMarks}
                                        step={0.5}
                                        value={editing.marks}
                                        onChange={(e) =>
                                          setEditing({
                                            ...editing,
                                            marks: e.target.value,
                                          })
                                        }
                                        className="h-8 w-24 bg-card"
                                      />
                                      <span className="text-sm text-muted-foreground">
                                        of {formatMarks(maxMarks)}
                                      </span>
                                    </div>
                                    <div className="space-y-1">
                                      <Label
                                        htmlFor={`edit-feedback-${ans.qid}`}
                                        className="text-sm"
                                      >
                                        Feedback for the student
                                      </Label>
                                      <Textarea
                                        id={`edit-feedback-${ans.qid}`}
                                        value={editing.feedback}
                                        onChange={(e) =>
                                          setEditing({
                                            ...editing,
                                            feedback: e.target.value,
                                          })
                                        }
                                        className="min-h-[80px] bg-card"
                                      />
                                    </div>
                                    <div className="flex gap-2 justify-end">
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => setEditing(null)}
                                        disabled={savingEdit}
                                      >
                                        Cancel
                                      </Button>
                                      <Button
                                        size="sm"
                                        onClick={() => saveEdit(maxMarks)}
                                        disabled={savingEdit}
                                      >
                                        {savingEdit ? "Saving..." : "Save"}
                                      </Button>
                                    </div>
                                  </div>
                                ) : (
                                  <div>
                                    <h4 className="text-sm font-medium flex items-center gap-1.5 mb-2">
                                      <FileText className="h-4 w-4" /> Feedback
                                    </h4>
                                    <div className="text-sm text-muted-foreground bg-muted/50 p-3 rounded border min-h-[60px] whitespace-pre-wrap">
                                      {ans.feedback ||
                                        (ans.status === "failed"
                                          ? "The AI could not grade this answer. Run the evaluation again, or grade it yourself."
                                          : "No feedback yet")}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center px-4">
                  <User className="h-12 w-12 text-muted-foreground/70 mb-2" />
                  <h3 className="text-lg font-medium text-foreground mb-1">
                    {detailLoading ? "Loading submission..." : "No student selected"}
                  </h3>
                  <p className="text-muted-foreground max-w-md">
                    Please select a student from the dropdown above to view
                    their submission
                  </p>
                </div>
              )
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-center px-4">
                <FileText className="h-12 w-12 text-muted-foreground/70 mb-2" />
                <h3 className="text-lg font-medium text-foreground mb-1">
                  No submissions yet
                </h3>
                <p className="text-muted-foreground max-w-md">
                  This assessment hasn&apos;t received any student submissions
                  yet
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <PaperLeaderboardCard qpid={id} />
    </div>
  );
}
