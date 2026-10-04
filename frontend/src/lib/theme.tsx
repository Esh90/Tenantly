import { useCallback, useEffect, useState } from "react";

const KEY = "tenantly.theme";
type Theme = "light" | "dark";

function apply(t: Theme) {
  document.documentElement.classList.toggle("dark", t === "dark");
}

/** Class-strategy dark mode: follows the system until the user chooses. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const saved = window.localStorage.getItem(KEY) as Theme | null;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const initial: Theme = saved ?? (mq.matches ? "dark" : "light");
    setTheme(initial);
    apply(initial);
    if (saved) return;
    const onChange = (e: MediaQueryListEvent) => {
      const t: Theme = e.matches ? "dark" : "light";
      setTheme(t);
      apply(t);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      window.localStorage.setItem(KEY, next);
      apply(next);
      return next;
    });
  }, []);

  return { theme, toggle };
}
