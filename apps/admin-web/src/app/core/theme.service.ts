import { Injectable, signal } from "@angular/core";

const THEME_STORAGE_KEY = "raghub-theme";

/**
 * Single source of truth for the light/dark theme, shared by the public
 * pages (landing, guides, auth entry) and the admin console layout.
 * Persists the choice in localStorage and mirrors it to
 * `document.documentElement.dataset["theme"]` so CSS can react to
 * `html[data-theme="dark"]`.
 */
@Injectable({ providedIn: "root" })
export class ThemeService {
  readonly darkMode = signal(false);

  constructor() {
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    const prefersDark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    this.darkMode.set(storedTheme ? storedTheme === "dark" : prefersDark);
    this.applyTheme();
  }

  toggleTheme(): void {
    this.darkMode.update((isDark) => !isDark);
    localStorage.setItem(
      THEME_STORAGE_KEY,
      this.darkMode() ? "dark" : "light",
    );
    this.applyTheme();
  }

  private applyTheme(): void {
    document.documentElement.dataset["theme"] = this.darkMode()
      ? "dark"
      : "light";
  }
}
