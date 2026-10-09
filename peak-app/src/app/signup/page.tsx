import Link from "next/link";
import { GraphSearchCanvas } from "@/components/graph-search-canvas";
import { SignUpForm } from "./signup-form";

export default function Page() {
  return (
    <div className="relative isolate min-h-svh overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10">
        <GraphSearchCanvas />
      </div>

      {/* Content */}
      <div className="relative flex min-h-svh w-full flex-col items-center p-6 md:p-10">
        <div className="mb-16">
          <Link href="/" className="flex items-center gap-3 font-medium">
            <img src="/logo.jpg" alt="Logo" className="h-10 w-10 rounded-lg" />
            <p className="text-3xl font-bold text-white">Perception</p>{" "}
          </Link>
        </div>
        <div className="w-full max-w-md">
          <SignUpForm />
        </div>
        <p className="text-xs mt-8 text-slate-300/80">
          Powered by <span className="font-semibold">Groq</span> for fast
          inference
        </p>
      </div>
    </div>
  );
}
