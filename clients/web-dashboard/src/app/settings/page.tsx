"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Palette,
  Sun,
  Moon,
  Monitor,
  Globe,
  Clock,
  Check,
  ChevronDown,
  RotateCcw,
  CheckCircle2,
} from "lucide-react";

export type ThemeOption = "light" | "dark" | "system";
export type LanguageOption = "vi" | "en";
export type TimeFormatOption = "24h" | "12h";

interface TimezoneItem {
  id: string;
  label: string;
  utcOffset: string;
  description: string;
}

const TIMEZONES: TimezoneItem[] = [
  {
    id: "Asia/Ho_Chi_Minh",
    label: "UTC+07:00 · Việt Nam",
    utcOffset: "+07:00",
    description: "Giờ chuẩn Đông Dương (ICT)",
  },
  {
    id: "UTC",
    label: "UTC+00:00 · GMT / UTC",
    utcOffset: "+00:00",
    description: "Giờ chuẩn phối hợp quốc tế",
  },
  {
    id: "Asia/Singapore",
    label: "UTC+08:00 · Singapore",
    utcOffset: "+08:00",
    description: "Giờ chuẩn Singapore / Tây Úc",
  },
  {
    id: "Asia/Tokyo",
    label: "UTC+09:00 · Tokyo",
    utcOffset: "+09:00",
    description: "Giờ chuẩn Nhật Bản (JST)",
  },
];

function SettingsContent() {
  const [mounted, setMounted] = useState<boolean>(false);
  const [language, setLanguage] = useState<LanguageOption>("vi");
  const [themeMode, setThemeMode] = useState<ThemeOption>("system");
  const [timezone, setTimezone] = useState<string>("Asia/Ho_Chi_Minh");
  const [timeFormat, setTimeFormat] = useState<TimeFormatOption>("24h");

  // Dropdown states
  const [isLangOpen, setIsLangOpen] = useState<boolean>(false);
  const [isTzOpen, setIsTzOpen] = useState<boolean>(false);

  // Notification Toast state
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const langRef = useRef<HTMLDivElement>(null);
  const tzRef = useRef<HTMLDivElement>(null);

  // Live preview clock
  const [currentTime, setCurrentTime] = useState<Date>(new Date());

  useEffect(() => {
    setMounted(true);
    // Read saved preferences from localStorage
    const savedLang = (localStorage.getItem("lang") as LanguageOption) || "vi";
    const savedTheme = (localStorage.getItem("theme") as ThemeOption) || "system";
    const savedTz = localStorage.getItem("timezone") || "Asia/Ho_Chi_Minh";
    const savedFormat = (localStorage.getItem("time_format") as TimeFormatOption) || "24h";

    setLanguage(savedLang);
    setThemeMode(savedTheme);
    setTimezone(savedTz);
    setTimeFormat(savedFormat);

    // Live clock timer
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    // Click outside handler for dropdowns
    const handleClickOutside = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) {
        setIsLangOpen(false);
      }
      if (tzRef.current && !tzRef.current.contains(e.target as Node)) {
        setIsTzOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      clearInterval(interval);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const showToast = (message: string) => {
    if (toastTimeoutRef.current) {
      clearTimeout(toastTimeoutRef.current);
    }
    setToastMessage(message);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  };

  const handleLanguageChange = (lang: LanguageOption) => {
    setLanguage(lang);
    setIsLangOpen(false);
    localStorage.setItem("lang", lang);
    showToast(
      lang === "vi"
        ? "Đã lưu tùy chọn ngôn ngữ: Tiếng Việt"
        : "Language updated: English"
    );
  };

  const handleThemeChange = (mode: ThemeOption) => {
    setThemeMode(mode);
    localStorage.setItem("theme", mode);

    let isDark: boolean;
    if (mode === "dark") {
      isDark = true;
    } else if (mode === "light") {
      isDark = false;
    } else {
      isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    }

    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }

    window.dispatchEvent(new Event("theme-change"));

    const labels: Record<ThemeOption, string> = {
      light: language === "vi" ? "Giao diện Sáng" : "Light mode",
      dark: language === "vi" ? "Giao diện Tối" : "Dark mode",
      system: language === "vi" ? "Giao diện theo Hệ thống" : "System mode",
    };
    showToast(`${language === "vi" ? "Đã chuyển sang" : "Switched to"} ${labels[mode]}`);
  };

  const handleTimezoneChange = (tzId: string) => {
    setTimezone(tzId);
    setIsTzOpen(false);
    localStorage.setItem("timezone", tzId);
    const selected = TIMEZONES.find((t) => t.id === tzId);
    showToast(
      language === "vi"
        ? `Đã cập nhật múi giờ: ${selected?.label || tzId}`
        : `Timezone updated: ${selected?.label || tzId}`
    );
  };

  const handleTimeFormatChange = (format: TimeFormatOption) => {
    setTimeFormat(format);
    localStorage.setItem("time_format", format);
    showToast(
      language === "vi"
        ? `Đã chọn định dạng: ${format === "24h" ? "24 giờ (14:30)" : "12 giờ (02:30 PM)"}`
        : `Time format updated: ${format}`
    );
  };

  const handleResetDefaults = () => {
    handleLanguageChange("vi");
    handleThemeChange("system");
    handleTimezoneChange("Asia/Ho_Chi_Minh");
    handleTimeFormatChange("24h");
    showToast(
      language === "vi"
        ? "Đã khôi phục toàn bộ cài đặt mặc định của hệ thống"
        : "All system settings restored to default"
    );
  };

  // Format sample time preview
  const formatTimePreview = () => {
    if (!mounted) return "14:30:00";
    try {
      return currentTime.toLocaleTimeString("en-US", {
        timeZone: timezone === "Asia/Ho_Chi_Minh" ? "Asia/Ho_Chi_Minh" : timezone,
        hour12: timeFormat === "12h",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return currentTime.toLocaleTimeString();
    }
  };

  const activeTimezoneItem =
    TIMEZONES.find((t) => t.id === timezone) || TIMEZONES[0];

  return (
    <AppShell activeRoute="settings">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-4 py-3 rounded-lg shadow-lg border border-border text-sm font-medium animate-in fade-in slide-in-from-bottom-2 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">
            {language === "vi" ? "Cài đặt" : "Settings"}
          </h1>
          <p className="text-xs text-text-secondary mt-1">
            {language === "vi"
              ? "Tùy biến ngôn ngữ, chủ đề giao diện và quy chuẩn hiển thị thời gian cho trạm giám sát"
              : "Customize language, display theme, and time format for the monitoring station"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleResetDefaults}
            className="h-9 px-3 text-xs font-medium rounded-lg border border-border text-text-secondary hover:text-text-primary hover:bg-canvas flex items-center gap-1.5 transition-colors"
            title={language === "vi" ? "Khôi phục thiết lập gốc" : "Reset all settings to default"}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{language === "vi" ? "Khôi phục mặc định" : "Reset defaults"}</span>
          </button>
        </div>
      </div>

      {/* Main Settings Grid - 800px max width strictly matching Stitch reference */}
      <div className="w-full max-w-[800px] flex flex-col gap-5">
        {/* CONTAINER 1: Giao diện (Appearance & Localization) */}
        <section className="bg-chrome rounded-lg border border-border p-6 shadow-none">
          {/* Card Title */}
          <div className="flex items-center gap-2.5 pb-4 border-b border-border">
            <Palette className="w-5 h-5 text-interactive" />
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                {language === "vi" ? "Giao diện" : "Appearance & Language"}
              </h2>
              <p className="text-xs text-text-secondary mt-0.5">
                {language === "vi"
                  ? "Tùy chỉnh ngôn ngữ hiển thị và chủ đề màu sắc cho toàn bộ trạm giám sát"
                  : "Display language and color theme preferences for the monitoring station"}
              </p>
            </div>
          </div>

          <div className="divide-y divide-border">
            {/* Setting 1: Ngôn ngữ (Language) */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5">
              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary">
                  {language === "vi" ? "Ngôn ngữ" : "Language"}
                </span>
                <span className="text-xs text-text-secondary mt-0.5">
                  {language === "vi"
                    ? "Ngôn ngữ hiển thị trên giao diện điều khiển và các bảng trạng thái"
                    : "Display language across dashboard controls and status tables"}
                </span>
              </div>

              {/* Language Selector Dropdown */}
              <div className="relative inline-block text-left" ref={langRef}>
                <button
                  type="button"
                  onClick={() => setIsLangOpen(!isLangOpen)}
                  aria-expanded={isLangOpen}
                  aria-haspopup="listbox"
                  className="h-10 min-w-[220px] bg-canvas border border-border rounded-lg px-3 py-2 text-sm font-medium text-text-primary flex items-center justify-between gap-2 hover:bg-canvas/80 focus:outline-none focus:ring-2 focus:ring-interactive/20 focus:border-interactive transition-colors"
                >
                  <span className="flex items-center gap-2.5">
                    <Globe className="w-4 h-4 text-text-secondary" />
                    <span>{language === "vi" ? "Tiếng Việt" : "English"}</span>
                  </span>
                  <ChevronDown
                    className={`w-4 h-4 text-text-secondary transition-transform duration-150 ${
                      isLangOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {isLangOpen && (
                  <ul
                    role="listbox"
                    className="absolute right-0 mt-1 min-w-[220px] w-full bg-chrome border border-border rounded-lg shadow-md py-1 z-30 animate-in fade-in zoom-in-95 duration-100"
                  >
                    <li
                      role="option"
                      aria-selected={language === "vi"}
                      onClick={() => handleLanguageChange("vi")}
                      className={`px-3 py-2 text-sm cursor-pointer flex items-center justify-between transition-colors ${
                        language === "vi"
                          ? "bg-sidebar-selected text-interactive font-medium"
                          : "text-text-primary hover:bg-canvas"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-text-secondary uppercase w-5">VI</span>
                        <span>Tiếng Việt</span>
                      </span>
                      {language === "vi" && <Check className="w-4 h-4 text-interactive" />}
                    </li>

                    <li
                      role="option"
                      aria-selected={language === "en"}
                      onClick={() => handleLanguageChange("en")}
                      className={`px-3 py-2 text-sm cursor-pointer flex items-center justify-between transition-colors ${
                        language === "en"
                          ? "bg-sidebar-selected text-interactive font-medium"
                          : "text-text-primary hover:bg-canvas"
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-text-secondary uppercase w-5">EN</span>
                        <span>English</span>
                      </span>
                      {language === "en" && <Check className="w-4 h-4 text-interactive" />}
                    </li>
                  </ul>
                )}
              </div>
            </div>

            {/* Setting 2: Chủ đề (Theme: Light / Dark / System) */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-5">
              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary">
                  {language === "vi" ? "Chủ đề" : "Theme"}
                </span>
                <span className="text-xs text-text-secondary mt-0.5">
                  {language === "vi"
                    ? "Tùy chọn chế độ hiển thị Sáng, Tối hoặc tự động đồng bộ theo hệ điều hành"
                    : "Select Light, Dark, or automatically match your operating system appearance"}
                </span>
              </div>

              {/* Segmented Radio Group for Theme */}
              <div
                role="radiogroup"
                aria-label={language === "vi" ? "Tùy chọn chủ đề" : "Theme options"}
                className="inline-flex items-center gap-1.5 p-1 bg-canvas border border-border rounded-lg"
              >
                {/* Sáng / Light */}
                <button
                  type="button"
                  role="radio"
                  aria-checked={themeMode === "light"}
                  onClick={() => handleThemeChange("light")}
                  className={`h-9 px-3.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-all duration-150 ${
                    themeMode === "light"
                      ? "bg-chrome text-interactive shadow-sm border border-border font-semibold"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <Sun className={`w-3.5 h-3.5 ${themeMode === "light" ? "text-amber-500" : ""}`} />
                  <span>{language === "vi" ? "Sáng" : "Light"}</span>
                </button>

                {/* Tối / Dark */}
                <button
                  type="button"
                  role="radio"
                  aria-checked={themeMode === "dark"}
                  onClick={() => handleThemeChange("dark")}
                  className={`h-9 px-3.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-all duration-150 ${
                    themeMode === "dark"
                      ? "bg-chrome text-interactive shadow-sm border border-border font-semibold"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <Moon className={`w-3.5 h-3.5 ${themeMode === "dark" ? "text-blue-400" : ""}`} />
                  <span>{language === "vi" ? "Tối" : "Dark"}</span>
                </button>

                {/* Hệ thống / System */}
                <button
                  type="button"
                  role="radio"
                  aria-checked={themeMode === "system"}
                  onClick={() => handleThemeChange("system")}
                  className={`h-9 px-3.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition-all duration-150 ${
                    themeMode === "system"
                      ? "bg-chrome text-interactive shadow-sm border border-border font-semibold"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <Monitor className="w-3.5 h-3.5" />
                  <span>{language === "vi" ? "Hệ thống" : "System"}</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* CONTAINER 2: Thời gian (Time & Regional Format) */}
        <section className="bg-chrome rounded-lg border border-border p-6 shadow-none">
          {/* Card Title */}
          <div className="flex items-center gap-2.5 pb-4 border-b border-border">
            <Clock className="w-5 h-5 text-interactive" />
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                {language === "vi" ? "Thời gian" : "Time & Regional"}
              </h2>
              <p className="text-xs text-text-secondary mt-0.5">
                {language === "vi"
                  ? "Quy chuẩn múi giờ và định dạng hiển thị cho các mốc thời gian sự kiện, cảnh báo"
                  : "Timezone and format standards for event timestamps, alerts, and TDMA frames"}
              </p>
            </div>
          </div>

          <div className="divide-y divide-border">
            {/* Setting 3: Múi giờ (Timezone) */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 py-5">
              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary">
                  {language === "vi" ? "Múi giờ" : "Timezone"}
                </span>
                <span className="text-xs text-text-secondary mt-0.5">
                  {language === "vi"
                    ? "Múi giờ hiển thị mốc thời gian sự kiện lỗi và bản ghi SCADA"
                    : "Timezone applied to telemetry events, fault timestamps, and logs"}
                </span>
              </div>

              {/* Timezone Selector Dropdown */}
              <div className="relative inline-block text-left" ref={tzRef}>
                <button
                  type="button"
                  onClick={() => setIsTzOpen(!isTzOpen)}
                  aria-expanded={isTzOpen}
                  aria-haspopup="listbox"
                  className="h-10 min-w-[260px] bg-canvas border border-border rounded-lg px-3 py-2 text-sm font-medium text-text-primary flex items-center justify-between gap-2 hover:bg-canvas/80 focus:outline-none focus:ring-2 focus:ring-interactive/20 focus:border-interactive transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-text-secondary" />
                    <span className="font-mono text-xs font-semibold tracking-tight">
                      {activeTimezoneItem.label}
                    </span>
                  </span>
                  <ChevronDown
                    className={`w-4 h-4 text-text-secondary transition-transform duration-150 ${
                      isTzOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {isTzOpen && (
                  <ul
                    role="listbox"
                    className="absolute right-0 mt-1 min-w-[280px] w-full bg-chrome border border-border rounded-lg shadow-md py-1 z-30 animate-in fade-in zoom-in-95 duration-100"
                  >
                    {TIMEZONES.map((tz) => {
                      const isSelected = tz.id === timezone;
                      return (
                        <li
                          key={tz.id}
                          role="option"
                          aria-selected={isSelected}
                          onClick={() => handleTimezoneChange(tz.id)}
                          className={`px-3 py-2.5 text-xs cursor-pointer flex items-center justify-between transition-colors ${
                            isSelected
                              ? "bg-sidebar-selected text-interactive font-medium"
                              : "text-text-primary hover:bg-canvas"
                          }`}
                        >
                          <div className="flex flex-col">
                            <span className="font-mono font-medium text-text-primary">
                              {tz.label}
                            </span>
                            <span className="text-[11px] text-text-secondary mt-0.5">
                              {tz.description}
                            </span>
                          </div>
                          {isSelected && <Check className="w-4 h-4 text-interactive shrink-0 ml-2" />}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>

            {/* Setting 4: Định dạng giờ (Time Format: 24h / 12h) */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-5">
              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary">
                  {language === "vi" ? "Định dạng giờ" : "Time Format"}
                </span>
                <span className="text-xs text-text-secondary mt-0.5">
                  {language === "vi"
                    ? "Định dạng thời gian hiển thị (ví dụ 14:30:00 hoặc 02:30:00 PM)"
                    : "Display time representation (e.g. 14:30:00 vs 02:30:00 PM)"}
                </span>
              </div>

              <div className="flex flex-col sm:items-end gap-2">
                {/* Segmented Radio Group */}
                <div
                  role="radiogroup"
                  aria-label={language === "vi" ? "Tùy chọn định dạng giờ" : "Time format options"}
                  className="inline-flex items-center gap-1.5 p-1 bg-canvas border border-border rounded-lg"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={timeFormat === "24h"}
                    onClick={() => handleTimeFormatChange("24h")}
                    className={`h-9 px-4 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                      timeFormat === "24h"
                        ? "bg-chrome text-interactive shadow-sm border border-border font-semibold"
                        : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    <span>{language === "vi" ? "24 giờ" : "24 Hours"}</span>
                  </button>

                  <button
                    type="button"
                    role="radio"
                    aria-checked={timeFormat === "12h"}
                    onClick={() => handleTimeFormatChange("12h")}
                    className={`h-9 px-4 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                      timeFormat === "12h"
                        ? "bg-chrome text-interactive shadow-sm border border-border font-semibold"
                        : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    <span>{language === "vi" ? "12 giờ (AM/PM)" : "12 Hours (AM/PM)"}</span>
                  </button>
                </div>

                {/* Live Preview Sample */}
                <div className="flex items-center gap-2 text-[11px] text-text-secondary">
                  <span>{language === "vi" ? "Mẫu hiển thị trực tiếp:" : "Live sample:"}</span>
                  <span className="font-mono px-2 py-0.5 bg-canvas border border-border rounded text-text-primary font-medium">
                    {formatTimePreview()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="flex items-center gap-3 text-text-secondary text-sm">
            <div className="w-5 h-5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang tải cài đặt hệ thống...</span>
          </div>
        </div>
      }
    >
      <SettingsContent />
    </Suspense>
  );
}

