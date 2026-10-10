"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Black or ash-white theme. Follows the device setting until the user picks
 * one with the toggle; the choice is then remembered in this browser.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      storageKey="perception:theme"
    >
      {children}
    </NextThemesProvider>
  );
}
