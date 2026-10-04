import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Bilingual, Lang } from "@/lib/api/types";
import { en, type StringKey } from "./en";
import { es } from "./es";

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: StringKey) => string;
  tb: (text: Bilingual | null | undefined) => string;
  /** Inline bilingual string for screen-specific copy. */
  tr: (en: string, es: string) => string;
}

const Ctx = createContext<I18n | null>(null);
const KEY = "tenantly.lang";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const saved = window.localStorage.getItem(KEY);
    if (saved === "en" || saved === "es") setLangState(saved);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    window.localStorage.setItem(KEY, l);
  }, []);

  const value = useMemo<I18n>(
    () => ({
      lang,
      setLang,
      t: (key) => (lang === "es" ? es[key] : en[key]),
      tb: (text) => (text ? text[lang] || text.en : ""),
      tr: (enText, esText) => (lang === "es" ? esText : enText),
    }),
    [lang, setLang],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n must be used inside I18nProvider");
  return v;
}
