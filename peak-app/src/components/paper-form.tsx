"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { PlusCircle, Trash2, Save, ArrowLeft, HelpCircle } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Loading } from "@/components/loading";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";

import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { formatMarks, num, toDateTimeLocal } from "@/lib/format";
import type { PaperDetail } from "@/lib/types";

interface QuestionDraft {
  // Stable key for React; not sent to the server
  key: number;
  // Set for questions that already exist on the server
  qid?: number;
  question: string;
  answer: string;
  rubric: string;
  marks: string;
}

const DEFAULT_MARKS = "10";

let nextKey = 1;
const emptyQuestion = (): QuestionDraft => ({
  key: nextKey++,
  question: "",
  answer: "",
  rubric: "",
  marks: DEFAULT_MARKS,
});

interface PaperFormProps {
  /** When given, the form edits this paper instead of creating a new one. */
  paperId?: string;
}

export function PaperForm({ paperId }: PaperFormProps) {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession({ role: "teacher" });
  const isEdit = Boolean(paperId);

  const [loadingPaper, setLoadingPaper] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [startDate, setStartDate] = useState(() => toDateTimeLocal(new Date()));
  const [duration, setDuration] = useState("");
  const [published, setPublished] = useState(true);
  const [questions, setQuestions] = useState<QuestionDraft[]>(() => [
    emptyQuestion(),
  ]);

  // Load the paper when editing
  useEffect(() => {
    if (!isEdit || !session) return;
    let mounted = true;

    (async () => {
      try {
        const { data } = await api.get<PaperDetail>(`/papers/${paperId}`);
        if (!mounted) return;
        setTitle(data.title);
        setStartDate(toDateTimeLocal(new Date(data.start_date)));
        setDuration(data.duration_minutes ? String(data.duration_minutes) : "");
        setPublished(data.is_published);
        setQuestions(
          data.questions.length > 0
            ? data.questions.map((q) => ({
                key: nextKey++,
                qid: q.qid,
                question: q.question_text,
                answer: q.model_answer || "",
                rubric: q.rubric || "",
                marks: formatMarks(q.marks_assigned),
              }))
            : [emptyQuestion()]
        );
      } catch (error) {
        toast.error(errorMessage(error, "Failed to load the paper"));
        router.push("/dashboard");
      } finally {
        if (mounted) setLoadingPaper(false);
      }
    })();

    return () => {
      mounted = false;
    };
  }, [isEdit, paperId, session, router]);

  function addQuestion() {
    setQuestions((prev) => [...prev, emptyQuestion()]);
  }

  function removeQuestion(key: number) {
    setQuestions((prev) => prev.filter((q) => q.key !== key));
  }

  function handleQuestionChange(
    key: number,
    field: "question" | "answer" | "rubric" | "marks",
    value: string
  ) {
    setQuestions((prev) =>
      prev.map((q) => (q.key === key ? { ...q, [field]: value } : q))
    );
  }

  const totalMarks = questions.reduce((sum, q) => sum + num(q.marks), 0);

  async function handleSubmit() {
    if (!title.trim()) {
      toast.error("Please enter a title");
      return;
    }
    if (questions.some((q) => !q.question.trim())) {
      toast.error("Please fill in every question");
      return;
    }
    if (questions.some((q) => !(num(q.marks) > 0))) {
      toast.error("Every question needs marks greater than 0");
      return;
    }
    const start = new Date(startDate);
    if (Number.isNaN(start.getTime())) {
      toast.error("Please choose a valid start date and time");
      return;
    }
    const durationMinutes = duration.trim() ? Number(duration) : null;
    if (
      durationMinutes !== null &&
      (!Number.isInteger(durationMinutes) || durationMinutes <= 0)
    ) {
      toast.error("Duration must be a whole number of minutes");
      return;
    }

    const payload = {
      title: title.trim(),
      start_date: start.toISOString(),
      duration_minutes: durationMinutes,
      is_published: published,
      questions: questions.map((q, index) => ({
        ...(q.qid ? { qid: q.qid } : {}),
        question_text: q.question.trim(),
        model_answer: q.answer.trim() || null,
        rubric: q.rubric.trim() || null,
        marks_assigned: num(q.marks),
        sort_order: index + 1,
      })),
    };

    setSaving(true);
    try {
      if (isEdit) {
        await api.patch(`/papers/${paperId}`, payload);
        toast.success("Paper updated successfully!");
      } else {
        await api.post("/papers", payload);
        toast.success(
          published ? "Paper created and published!" : "Paper saved as a draft"
        );
      }
      router.push("/dashboard");
    } catch (error) {
      toast.error(errorMessage(error, "Could not save the paper"));
    } finally {
      setSaving(false);
    }
  }

  if (sessionLoading || !session || loadingPaper) {
    return <Loading />;
  }

  return (
    <div className="min-h-screen bg-background py-12">
      <div className="max-w-4xl mx-auto px-4">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-foreground mb-2">
            {isEdit ? "Edit Assessment" : "Create New Assessment"}
          </h1>
          <p className="text-muted-foreground">
            Design your questions and provide model answers and rubrics
          </p>
        </div>

        {/* Main Content */}
        <Card className="shadow-lg border-0 overflow-hidden mb-8">
          <CardHeader className="bg-card border-b border-border px-6 py-5">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label
                  htmlFor="paper-title"
                  className="text-sm font-medium text-foreground"
                >
                  Assessment Title
                </Label>
                <Input
                  id="paper-title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a descriptive title"
                  className="text-lg font-medium focus-visible:ring-primary"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label
                    htmlFor="paper-start"
                    className="text-sm font-medium text-foreground"
                  >
                    Opens for students at
                  </Label>
                  <Input
                    id="paper-start"
                    type="datetime-local"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="paper-duration"
                    className="text-sm font-medium text-foreground"
                  >
                    Time limit in minutes (optional)
                  </Label>
                  <Input
                    id="paper-duration"
                    type="number"
                    min={1}
                    step={1}
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    placeholder="No limit"
                  />
                </div>
              </div>

              <label className="flex items-start gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4"
                  checked={published}
                  onChange={(e) => setPublished(e.target.checked)}
                />
                <span>
                  <span className="font-medium">Publish</span>
                  <span className="block text-xs text-muted-foreground">
                    Published papers are visible to your students from the
                    opening time. Leave unticked to keep it as a draft.
                  </span>
                </span>
              </label>
            </div>
          </CardHeader>

          <CardContent className="p-6 bg-card space-y-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-semibold text-foreground">Questions</h2>
              <div className="text-sm text-muted-foreground">
                {questions.length} question(s) · {formatMarks(totalMarks)} marks
              </div>
            </div>

            <Separator className="my-4" />

            <div className="space-y-6">
              {questions.map((q, index) => (
                <motion.div
                  key={q.key}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <Card className="border border-border shadow-sm overflow-hidden">
                    <CardHeader className="bg-muted/50 px-4 py-3 flex flex-row items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="h-6 w-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-medium">
                          {index + 1}
                        </div>
                        <h3 className="font-medium text-foreground">
                          Question {index + 1}
                        </h3>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <Label
                            htmlFor={`marks-${q.key}`}
                            className="text-sm text-muted-foreground"
                          >
                            Marks
                          </Label>
                          <Input
                            id={`marks-${q.key}`}
                            type="number"
                            min={0.5}
                            step={0.5}
                            value={q.marks}
                            onChange={(e) =>
                              handleQuestionChange(
                                q.key,
                                "marks",
                                e.target.value
                              )
                            }
                            className="h-8 w-20 bg-card"
                          />
                        </div>
                        {questions.length > 1 && (
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Remove question ${index + 1}`}
                            onClick={() => removeQuestion(q.key)}
                            className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="p-4 space-y-4">
                      <div className="space-y-2">
                        <Label
                          htmlFor={`question-${q.key}`}
                          className="text-sm font-medium text-foreground flex items-center gap-1"
                        >
                          Question{" "}
                          <HelpCircle className="h-3 w-3 text-muted-foreground/70" />
                        </Label>
                        <Textarea
                          id={`question-${q.key}`}
                          value={q.question}
                          onChange={(e) =>
                            handleQuestionChange(
                              q.key,
                              "question",
                              e.target.value
                            )
                          }
                          placeholder="Enter your question here"
                          className="min-h-[100px] resize-none focus-visible:ring-primary"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label
                          htmlFor={`answer-${q.key}`}
                          className="text-sm font-medium text-foreground flex items-center gap-1"
                        >
                          Model Answer{" "}
                          <HelpCircle className="h-3 w-3 text-muted-foreground/70" />
                        </Label>
                        <Textarea
                          id={`answer-${q.key}`}
                          value={q.answer}
                          onChange={(e) =>
                            handleQuestionChange(q.key, "answer", e.target.value)
                          }
                          placeholder="Enter the expected answer here. The AI compares each student's answer with it. Students never see it."
                          className="min-h-[100px] resize-none focus-visible:ring-primary"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label
                          htmlFor={`rubric-${q.key}`}
                          className="text-sm font-medium text-foreground flex items-center gap-1"
                        >
                          Rubric (optional){" "}
                          <HelpCircle className="h-3 w-3 text-muted-foreground/70" />
                        </Label>
                        <Textarea
                          id={`rubric-${q.key}`}
                          value={q.rubric}
                          onChange={(e) =>
                            handleQuestionChange(q.key, "rubric", e.target.value)
                          }
                          placeholder="How the marks are awarded, e.g. '2 marks for the definition, 3 marks for an example'. Without a rubric the AI grades on accuracy, completeness, relevance and clarity."
                          className="min-h-[70px] resize-none focus-visible:ring-primary"
                        />
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </CardContent>

          <CardFooter className="flex justify-between p-6 bg-muted/50 border-t border-border">
            <Button
              variant="outline"
              onClick={addQuestion}
              className="flex items-center gap-1"
            >
              <PlusCircle className="h-4 w-4" /> Add Question
            </Button>
          </CardFooter>
        </Card>

        {/* Action Buttons */}
        <div className="flex gap-4 justify-end mt-6">
          <Button
            variant="outline"
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1 border-border"
            disabled={saving}
          >
            <ArrowLeft className="h-4 w-4" /> Cancel
          </Button>

          <Button
            onClick={handleSubmit}
            disabled={saving}
            className="flex items-center gap-1 bg-primary hover:bg-primary/90"
          >
            <Save className="h-4 w-4" />{" "}
            {saving
              ? "Saving..."
              : isEdit
              ? "Save Changes"
              : published
              ? "Save & Publish"
              : "Save Draft"}
          </Button>
        </div>
      </div>
    </div>
  );
}
