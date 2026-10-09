"use client";

import { useParams } from "next/navigation";
import { Loading } from "@/components/loading";
import { useSession } from "@/lib/auth";
import { TeacherView } from "../teacher-view";
import { StudentView } from "../student-view";

export default function QuestionPaperPage() {
  const params = useParams();
  const { session, loading } = useSession();

  if (loading || !session) return <Loading />;

  const id = typeof params.id === "string" ? params.id : "";

  return (
    <div className="m-8">
      {session.role === "teacher" ? (
        <TeacherView id={id} email={session.email} />
      ) : (
        <StudentView id={id} email={session.email} />
      )}
    </div>
  );
}
