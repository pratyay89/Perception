import Link from "next/link";
import { SignUpForm } from "./signup-form";

export default function Page() {
  return (
    <div className="relative min-h-svh">
      {/* Background Image */}
      <div className="absolute inset-0 -z-10">
        <img
          src="/signup-back.jpg"
          alt="Background"
          className="h-full w-full object-cover brightness-[0.7]"
        />
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
        <img
          src="https://groq.com/wp-content/uploads/2024/03/PBG-mark1-color.svg"
          alt="Powered by Groq for fast inference."
          className="h-32 w-32"
        />
      </div>
    </div>
  );
}
