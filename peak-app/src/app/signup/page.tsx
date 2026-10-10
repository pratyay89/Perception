import Link from "next/link";
import { GraphSearchCanvas } from "@/components/graph-search-canvas";
import { ThemeToggle } from "@/components/theme-toggle";
import { SignUpForm } from "./signup-form";

export default function Page() {
  return (
    <div className="relative isolate min-h-svh overflow-hidden bg-gradient-to-br from-black via-neutral-950 to-stone-900">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10">
        <GraphSearchCanvas />
      </div>

      <ThemeToggle className="absolute right-4 top-4 z-10 text-stone-200 hover:bg-white/10 hover:text-white md:right-6 md:top-6" />

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
        <p className="text-xs mt-8 text-stone-400">
          Powered by <span className="font-semibold">Groq</span> for fast
          inference
        </p>
      </div>
    </div>
  );
}
