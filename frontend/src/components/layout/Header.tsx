import { useState } from "react";
import { useWatched } from "@/lib/watch";
import { Link, useRouterState } from "@tanstack/react-router";
import { Menu, Moon, Sun } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { AddressSearch } from "@/components/tenantly/AddressSearch";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import type { Lang } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const navLink =
  "relative inline-flex h-16 items-center text-[15px] text-graphite transition-colors hover:text-deed data-[status=active]:text-deed data-[status=active]:after:absolute data-[status=active]:after:inset-x-0 data-[status=active]:after:bottom-0 data-[status=active]:after:h-0.5 data-[status=active]:after:bg-deed";

function LangToggle() {
  const { lang, setLang, t } = useI18n();
  return (
    <ToggleGroup
      type="single"
      value={lang}
      onValueChange={(v) => v && setLang(v as Lang)}
      aria-label={t("lang_label")}
      className="rounded-md border border-hairline p-0.5"
    >
      {(["en", "es"] as const).map((l) => (
        <ToggleGroupItem
          key={l}
          value={l}
          className="h-8 min-w-9 rounded-sm px-2 text-sm font-medium text-graphite data-[state=on]:bg-deed data-[state=on]:text-primary-foreground"
        >
          {l.toUpperCase()}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}


export function Header() {
  const { t } = useI18n();
  const { theme, toggle } = useTheme();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isHome = pathname === "/";
  const { unseen } = useWatched();
  const [open, setOpen] = useState(false);

  const primary = [
    { to: "/rules", label: t("nav_rules") },
    { to: "/changes", label: t("nav_changes") },
    { to: "/about", label: t("nav_about") },
  ] as const;

  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-sheet">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-6 px-5 md:px-8">
        <Link to="/" aria-label="Tenantly home" className="shrink-0">
          <Logo />
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-6 lg:flex">
          {primary.map((n) => (
            <Link key={n.to} to={n.to} className={navLink}>
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="hidden min-w-0 flex-1 justify-center md:flex">
          {!isHome && <AddressSearch variant="compact" className="max-w-md" />}
        </div>
        <div className="flex-1 md:hidden" />

        <div className="hidden items-center gap-4 md:flex">
          <Link to="/watch" className={cn(navLink, "gap-1.5")}>
            {t("nav_watched")}
            {unseen && <span className="size-2 rounded-full bg-permit" aria-label="Unseen changes" />}
          </Link>
          <Link to="/proof" className={navLink}>
            {t("nav_proof")}
          </Link>
          <span className="h-6 w-px bg-hairline" aria-hidden="true" />
          <LangToggle />
          <button
            type="button"
            onClick={toggle}
            aria-label={t("theme_toggle")}
            className="inline-flex size-10 items-center justify-center rounded-md text-graphite hover:bg-muted hover:text-deed"
          >
            {theme === "dark" ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
          </button>
        </div>

        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <button
              type="button"
              aria-label={t("nav_menu")}
              className="inline-flex size-11 items-center justify-center rounded-md text-deed hover:bg-muted md:hidden"
            >
              <Menu className="size-5" />
            </button>
          </SheetTrigger>
          <SheetContent side="right" className="w-[88vw] max-w-sm bg-sheet p-0">
            <SheetTitle className="sr-only">{t("nav_menu")}</SheetTitle>
            <div className="border-b border-hairline px-5 py-4">
              <Logo />
            </div>
            {!isHome && (
              <div className="border-b border-hairline px-5 py-4">
                <AddressSearch variant="compact" />
              </div>
            )}
            <nav aria-label="Mobile" className="flex flex-col px-2 py-2">
              {[{ to: "/", label: t("nav_home") }, ...primary, { to: "/watch", label: t("nav_watched") }, { to: "/proof", label: t("nav_proof") }].map(
                (n) => (
                  <Link
                    key={n.to}
                    to={n.to}
                    onClick={() => setOpen(false)}
                    activeOptions={{ exact: n.to === "/" }}
                    className="flex min-h-11 items-center rounded-md px-3 text-lg text-deed hover:bg-muted data-[status=active]:font-semibold"
                  >
                    {n.label}
                  </Link>
                ),
              )}
            </nav>
            <div className="flex items-center justify-between border-t border-hairline px-5 py-4">
              <LangToggle />
              <button
                type="button"
                onClick={toggle}
                aria-label={t("theme_toggle")}
                className="inline-flex size-11 items-center justify-center rounded-md text-graphite hover:bg-muted"
              >
                {theme === "dark" ? <Sun className="size-5" /> : <Moon className="size-5" />}
              </button>
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}
