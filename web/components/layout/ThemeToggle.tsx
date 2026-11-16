"use client";

import { Moon, Sun } from "lucide-react";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const toggle = () => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      // localStorage unavailable (private mode, disabled storage) — theme just won't persist.
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      title="Toggle color theme"
      aria-label="Toggle color theme"
      className={`flex size-10 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground ${className}`}
    >
      <Sun size={18} className="hidden dark:block" />
      <Moon size={18} className="block dark:hidden" />
    </button>
  );
}
