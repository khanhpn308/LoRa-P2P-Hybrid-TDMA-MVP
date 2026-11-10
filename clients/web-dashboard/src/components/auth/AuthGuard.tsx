"use client";

import React, { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthContext";
import { Radio } from "lucide-react";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isLoginPage = pathname === "/login" || pathname?.startsWith("/login/");

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated && !isLoginPage) {
      router.replace("/login");
    } else if (isAuthenticated && isLoginPage) {
      router.replace("/");
    }
  }, [isAuthenticated, isLoading, isLoginPage, router]);

  // While initializing auth state, show loading canvas to prevent UI flicker and data leak
  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-canvas text-text-primary select-none">
        <div className="flex flex-col items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center animate-pulse">
            <Radio className="w-5 h-5" />
          </div>
          <div className="flex items-center gap-2 text-text-secondary text-xs">
            <div className="w-3.5 h-3.5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang kiểm tra phiên đăng nhập...</span>
          </div>
        </div>
      </div>
    );
  }

  // If unauthenticated on a protected route, block render and hold on loading screen until redirected
  if (!isAuthenticated && !isLoginPage) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-canvas text-text-primary select-none">
        <div className="flex flex-col items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center">
            <Radio className="w-5 h-5" />
          </div>
          <div className="flex items-center gap-2 text-text-secondary text-xs">
            <div className="w-3.5 h-3.5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang chuyển hướng đến trang đăng nhập...</span>
          </div>
        </div>
      </div>
    );
  }

  // If authenticated on login route, block render and hold on loading screen until redirected
  if (isAuthenticated && isLoginPage) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-canvas text-text-primary select-none">
        <div className="flex flex-col items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center">
            <Radio className="w-5 h-5" />
          </div>
          <div className="flex items-center gap-2 text-text-secondary text-xs">
            <div className="w-3.5 h-3.5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang chuyển hướng vào hệ thống...</span>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
