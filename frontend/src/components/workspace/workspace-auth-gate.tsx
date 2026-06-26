"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/core/auth/AuthProvider";
import { authApiUrl } from "@/core/auth/client";
import { buildLoginUrl } from "@/core/auth/types";
import { isStaticWebsiteOnly } from "@/core/static-mode";

type GateState = "checking" | "ready" | "redirecting";

export function WorkspaceAuthGate({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const [state, setState] = useState<GateState>(
    isAuthenticated || isStaticWebsiteOnly() ? "ready" : "checking",
  );

  useEffect(() => {
    if (isStaticWebsiteOnly()) {
      setState("ready");
      return;
    }
    if (isAuthenticated) {
      setState("ready");
      return;
    }
    if (isLoading) return;

    let cancelled = false;
    setState("checking");

    void fetch(authApiUrl("/api/v1/auth/setup-status"), {
      credentials: "include",
      cache: "no-store",
    })
      .then(async (response) => {
        if (cancelled) return;
        let target = buildLoginUrl(pathname || "/workspace");
        if (response.ok) {
          const data = (await response.json()) as { needs_setup?: boolean };
          if (data.needs_setup) target = "/setup";
        }
        setState("redirecting");
        window.location.replace(target);
      })
      .catch(() => {
        if (cancelled) return;
        setState("redirecting");
        window.location.replace(buildLoginUrl(pathname || "/workspace"));
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, isLoading, pathname]);

  if (state !== "ready") {
    return (
      <div className="bg-background text-muted-foreground flex h-screen w-full items-center justify-center text-sm">
        Checking authentication...
      </div>
    );
  }

  return <>{children}</>;
}
