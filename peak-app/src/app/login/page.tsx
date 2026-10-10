import { GraphSearchCanvas } from "@/components/graph-search-canvas";
import { ThemeToggle } from "@/components/theme-toggle";
import { LoginForm } from "./login-form";

export default function LoginPage() {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="relative flex flex-col gap-4 p-6 md:p-10">
        <ThemeToggle className="absolute right-4 top-4 md:right-6 md:top-6" />
        <div className="flex flex-col justify-center gap-2 md:justify-start">
          <a href="#" className="flex items-center gap-2 font-medium">
            <img src="/logo.jpg" alt="Logo" className="h-8 w-8 rounded-lg" />
            <p className="text-3xl font-bold">Perception</p>
          </a>
          <p className="m-2 text-lg">
            A Platform for LLM-Based evaluation and feedback.
          </p>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-sm">
            <LoginForm />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Powered by <span className="font-semibold">Groq</span> for fast
          inference
        </p>
      </div>
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-black via-neutral-950 to-stone-900 lg:block">
        <GraphSearchCanvas className="absolute inset-0" />
        <div className="pointer-events-none absolute inset-x-0 top-0 p-10">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-stone-400">
            Every answer, evaluated
          </p>
          <p className="mt-3 max-w-md text-3xl font-semibold leading-tight text-white">
            Finding the shortest path from a question to fair, consistent
            feedback.
          </p>
        </div>
      </div>
    </div>
  );
}
