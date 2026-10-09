"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSession } from "@/lib/auth";
import { useLoading } from "@/components/providers/loading-provider";

export default function Home() {
  const router = useRouter();
  const { setIsLoading } = useLoading();

  useEffect(() => {
    setIsLoading(true);
    router.replace(getSession() ? "/dashboard" : "/login");

    return () => {
      setIsLoading(false);
    };
  }, [router, setIsLoading]);

  return null;
}
