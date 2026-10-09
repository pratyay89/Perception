"use client";
import { useParams } from "next/navigation";
import { PaperForm } from "@/components/paper-form";

export default function EditPaperPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";

  return <PaperForm paperId={id} />;
}
