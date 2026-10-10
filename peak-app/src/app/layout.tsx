import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { LoadingProvider } from "@/components/providers/loading-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import "./globals.css";

// font configurations
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const inter = Inter({ subsets: ["latin"] });

//metadata configuration
export const metadata: Metadata = {
  title: "Perception",
  description: "A platform for evaluation",
};

type RootLayoutProps = Readonly<{
  children: React.ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} ${geistMono.variable} antialiased`}>
        <ThemeProvider>
          <LoadingProvider>
            {children}
            <Toaster richColors />
          </LoadingProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
