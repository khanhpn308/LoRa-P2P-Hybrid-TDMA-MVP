"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter } from "next/navigation";
import { LoginRequest } from "@/types/api";
import { useAuth } from "@/lib/auth/AuthContext";
import { ApiClientError } from "@/lib/api/client";
import {
  Radio,
  User,
  Lock,
  Eye,
  EyeOff,
  Sun,
  Moon,
  AlertCircle,
  ArrowRight,
} from "lucide-react";

function LoginContent() {
  const router = useRouter();
  const { login } = useAuth();

  const [username, setUsername] = useState("admin01");
  const [password, setPassword] = useState("password123");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lang, setLang] = useState<"vi" | "en">("vi");
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const savedLang = (localStorage.getItem("lang") as "vi" | "en") || "vi";
    setLang(savedLang);

    const savedTheme = localStorage.getItem("theme");
    const isDark = savedTheme === "dark" || (!savedTheme && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDarkMode(isDark);
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const toggleDarkMode = () => {
    const next = !darkMode;
    setDarkMode(next);
    localStorage.setItem("theme", next ? "dark" : "light");
    if (next) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  };

  const handleLangToggle = (selectedLang: "vi" | "en") => {
    setLang(selectedLang);
    localStorage.setItem("lang", selectedLang);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!username.trim() || !password.trim()) {
      setErrorMsg(lang === "vi" ? "Vui lòng nhập đầy đủ tài khoản và mật khẩu." : "Please enter both username and password.");
      return;
    }

    setIsLoading(true);

    const loginPayload: LoginRequest = {
      username: username.trim(),
      password: password.trim(),
    };

    try {
      await login(loginPayload);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.status === 401) {
          setErrorMsg(
            lang === "vi"
              ? "Tài khoản hoặc mật khẩu không chính xác. Vui lòng thử lại."
              : "Invalid username or password. Please try again."
          );
        } else {
          setErrorMsg(err.message);
        }
      } else {
        setErrorMsg(
          lang === "vi"
            ? "Không thể kết nối đến máy chủ Backend. Vui lòng thử lại sau."
            : "Cannot connect to Backend server. Please try again later."
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-text-primary flex flex-col justify-between p-6 sm:p-8 select-none transition-colors duration-150">
      {/* Top Header Bar */}
      <header className="w-full flex items-center justify-between pb-4">
        {/* Brand Lockup (DESIGN.md §6) */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center">
            <Radio className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="text-[15px] font-semibold text-text-primary leading-tight">
              IIoT LoRa Network
            </span>
            <span className="text-[11px] text-text-secondary leading-tight mt-0.5">
              {lang === "vi" ? "Trạm giám sát" : "Monitoring Station"}
            </span>
          </div>
        </div>

        {/* Right Controls: Language Switcher + Theme Toggle */}
        <div className="flex items-center gap-3">
          {/* Language Switcher */}
          <div className="flex items-center p-0.5 rounded-lg bg-canvas border border-border">
            <button
              type="button"
              onClick={() => handleLangToggle("vi")}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                lang === "vi"
                  ? "bg-chrome text-interactive shadow-sm border border-border"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              VI
            </button>
            <button
              type="button"
              onClick={() => handleLangToggle("en")}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                lang === "en"
                  ? "bg-chrome text-interactive shadow-sm border border-border"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              EN
            </button>
          </div>

          {/* Theme Toggle */}
          <button
            type="button"
            onClick={toggleDarkMode}
            className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary bg-canvas border border-border hover:bg-canvas/80 transition-colors"
            title={lang === "vi" ? "Chuyển giao diện Sáng / Tối" : "Toggle Light / Dark mode"}
          >
            {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* Main Centered Login Card - Max width 420px strictly matching Stitch screen 41775afdc219441fb31d80648c579e99 */}
      <main className="flex-1 flex items-center justify-center py-10">
        <div className="w-full max-w-[420px] bg-chrome rounded-xl border border-border p-8 shadow-none flex flex-col gap-6 animate-in fade-in zoom-in-95 duration-200">
          {/* Form Header */}
          <div className="flex flex-col">
            <h1 className="text-2xl font-semibold text-text-primary tracking-tight">
              {lang === "vi" ? "Đăng nhập" : "Sign In"}
            </h1>
            <p className="text-xs text-text-secondary mt-1">
              {lang === "vi"
                ? "Truy cập hệ thống điều hành mạng LoRa P2P Hybrid TDMA"
                : "Access the LoRa P2P Hybrid TDMA operations portal"}
            </p>
          </div>

          {/* Error Banner if any */}
          {errorMsg && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-state-critical text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Industrial Login Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Field: Username */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="login-username" className="text-xs font-medium text-text-primary">
                {lang === "vi" ? "Tài khoản" : "Username"}
              </label>
              <div className="relative flex items-center">
                <User className="absolute left-3 w-4 h-4 text-text-secondary pointer-events-none" />
                <input
                  id="login-username"
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={lang === "vi" ? "Nhập tài khoản" : "Enter username"}
                  className="w-full h-11 pl-10 pr-3 rounded-lg border border-border bg-canvas text-text-primary text-sm placeholder:text-text-secondary/60 focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-all"
                />
              </div>
            </div>

            {/* Field: Password */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="login-password" className="text-xs font-medium text-text-primary">
                {lang === "vi" ? "Mật khẩu" : "Password"}
              </label>
              <div className="relative flex items-center">
                <Lock className="absolute left-3 w-4 h-4 text-text-secondary pointer-events-none" />
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={lang === "vi" ? "Nhập mật khẩu" : "Enter password"}
                  className="w-full h-11 pl-10 pr-10 rounded-lg border border-border bg-canvas text-text-primary text-sm placeholder:text-text-secondary/60 focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-all font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  className="absolute right-2.5 w-7 h-7 flex items-center justify-center text-text-secondary hover:text-text-primary transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Demo Hint */}
            <div className="text-[11px] text-text-secondary bg-canvas p-2.5 rounded-lg border border-border flex items-center justify-between">
              <span>{lang === "vi" ? "Mẫu tài khoản mặc định:" : "Default demo account:"}</span>
              <span className="font-mono font-semibold text-text-primary">admin01</span>
            </div>

            {/* Submit Button */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full h-11 bg-interactive hover:bg-interactive-hover disabled:opacity-60 text-white text-sm font-semibold rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-interactive"
              >
                {isLoading ? (
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <span>{lang === "vi" ? "Đăng nhập" : "Sign In"}</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full flex items-center justify-center pt-4">
        <p className="text-xs text-text-secondary text-center">
          © 2026 IIoT LoRa Network · {lang === "vi" ? "Trạm giám sát SCADA sự cố công nghiệp" : "Industrial Event Monitoring SCADA Station"}
        </p>
      </footer>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="flex items-center gap-3 text-text-secondary text-sm">
            <div className="w-5 h-5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang tải màn hình đăng nhập...</span>
          </div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}

