// Shapes of the backend API responses (see backend/app/*/schemas.py).
// Decimal values (marks) arrive as strings; use `num()` from "@/lib/format".

export type Role = "teacher" | "student";

export type PaperStatus = "draft" | "scheduled" | "open" | "closed";

export type EvaluationStatus = "pending" | "success" | "failed";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  email: string;
  role: Role;
  full_name: string;
}

export interface AssociatedUser {
  email: string;
  full_name: string;
}

export interface AssociationsResponse {
  associations: string[];
  users: AssociatedUser[];
}

export interface Usage {
  email: string;
  papers_created_balance: number;
  submissions_made_balance: number;
  llm_tokens_balance: number;
  papers_created_limit: number;
  submissions_made_limit: number;
  llm_tokens_limit: number;
}

export interface Question {
  qid: number;
  qpid: number;
  question_text: string;
  marks_assigned: string;
  sort_order: number;
  // Only present for teachers
  model_answer?: string | null;
  rubric?: string | null;
}

interface PaperBase {
  qpid: number;
  t_email: string;
  title: string;
  start_date: string;
  duration_minutes: number | null;
  total_marks: string;
  is_published: boolean;
  is_closed: boolean;
  status: PaperStatus;
}

// An entry of GET /papers
export interface PaperSummary extends PaperBase {
  created_at: string;
  question_count: number;
  // Teachers
  submission_count: number | null;
  evaluated_count: number | null;
  // Students
  teacher_name: string | null;
  attempted: boolean | null;
  evaluated: boolean | null;
  marks_obtained: string | null;
}

// GET /papers/{qpid}
export interface PaperDetail extends PaperBase {
  questions: Question[];
}

export interface Answer {
  qpid: number;
  s_email: string;
  qid: number;
  student_answer: string | null;
  marks_obtained: string;
  feedback: string | null;
  status: EvaluationStatus;
}

export interface SubmissionSummary {
  qpid: number;
  s_email: string;
  evaluated: boolean;
  total_marks_obtained: string;
  created_at: string;
  // Only present for teachers
  student_name?: string | null;
}

export interface SubmissionDetail extends SubmissionSummary {
  answers: Answer[];
}

// POST /evaluations/{qpid}/{s_email}
export interface EvaluationResult extends SubmissionDetail {
  graded_count: number;
  failed_count: number;
  pending_count: number;
  tokens_used: number;
  message: string | null;
}

// POST /evaluations/{qpid}
export interface PaperEvaluation {
  qpid: number;
  submission_count: number;
  evaluated_count: number;
  graded_count: number;
  failed_count: number;
  pending_count: number;
  tokens_used: number;
  message: string | null;
  submissions: SubmissionSummary[];
}

// GET /leaderboard/papers/{qpid}
export interface PaperLeaderboardEntry {
  rank: number;
  full_name: string;
  // Only teachers see other students' emails
  s_email: string | null;
  is_you: boolean;
  marks_obtained: string;
  percentage: number;
}

export interface PaperLeaderboard {
  qpid: number;
  title: string;
  total_marks: string;
  pending_count: number;
  entries: PaperLeaderboardEntry[];
}

// An entry of GET /leaderboard (one per class)
export interface ClassLeaderboardEntry {
  rank: number;
  full_name: string;
  s_email: string | null;
  is_you: boolean;
  papers_evaluated: number;
  marks_obtained: string;
  total_marks: string;
  percentage: number;
}

export interface ClassLeaderboard {
  t_email: string;
  teacher_name: string;
  papers_count: number;
  entries: ClassLeaderboardEntry[];
}
