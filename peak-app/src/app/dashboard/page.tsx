"use client";
import { useSession } from "@/lib/auth";
import { Loading } from "@/components/loading";
import { StudentDashboard } from "./student-view";
import { TeacherDashboard } from "./teacher-view";

export default function DashboardPage() {
  const { session, loading } = useSession();

  if (loading || !session) return <Loading />;

  return session.role === "teacher" ? (
    <TeacherDashboard email={session.email} />
  ) : (
    <StudentDashboard email={session.email} />
  );
}
