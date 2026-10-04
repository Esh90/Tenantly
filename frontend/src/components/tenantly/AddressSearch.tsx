import { useQueryClient } from "@tanstack/react-query";
import { getTimeline } from "@/lib/api/api";
import { keys } from "@/lib/api/hooks";
import { useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { MapPin, Search } from "lucide-react";
import { createAddressSearcher, type AddressIndexItem } from "@/lib/api/api";
import { useAddressIndex, useResolveAddress } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  variant?: "hero" | "compact";
  className?: string;
  autoFocus?: boolean;
}

export function AddressSearch({ variant = "hero", className, autoFocus }: Props) {
  const { t, tr } = useI18n();
  const navigate = useNavigate();
  const { data, isLoading } = useAddressIndex();
  const resolve = useResolveAddress();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [notFound, setNotFound] = useState<AddressIndexItem[] | null>(null);
  const [geoDown, setGeoDown] = useState(false);
  const qc = useQueryClient();
  const prefetch = (id: string) => qc.prefetchQuery({ queryKey: keys.timeline(id), queryFn: () => getTimeline(id), staleTime: 5 * 60 * 1000 });
  const listId = useId();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const searcher = useMemo(() => (data ? createAddressSearcher(data) : null), [data]);
  const results = useMemo(() => (searcher ? searcher(q, variant === "hero" ? 7 : 6) : []), [searcher, q, variant]);
  const hero = variant === "hero";

  const go = (id: string) => {
    setOpen(false);
    setQ("");
    setNotFound(null);
    navigate({ to: "/a/$addressId", params: { addressId: id } });
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => { const n = Math.min(a + 1, results.length - 1); if (results[n]) prefetch(results[n].address_id); return n; });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const pick = open ? (results[active] ?? results[0]) : results[0];
    if (pick) return go(pick.address_id);
    if (!q.trim()) return inputRef.current?.focus();
    setOpen(false);
    try {
      const r = await resolve.mutateAsync(q);
      if (r.address && r.match_type !== "not_found") go(r.address.address_id);
      else setNotFound(r.candidates);
    } catch {
      setGeoDown(true);
    }
  };

  const showList = open && q.trim().length > 0 && !resolve.isPending;

  return (
    <form role="search" onSubmit={onSubmit} className={cn("relative w-full", className)}>
      <label htmlFor={inputId} className={hero ? "mb-2 block text-sm font-medium text-graphite" : "sr-only"}>
        {t("search_label")}
      </label>
      <div className={cn("flex w-full gap-2", hero ? "flex-col sm:flex-row" : "")}>
        <div className="relative flex-1">
          <Search
            className={cn("pointer-events-none absolute top-1/2 -translate-y-1/2 text-graphite", hero ? "left-4 size-5" : "left-3 size-4")}
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            id={inputId}
            type="text"
            role="combobox"
            aria-expanded={showList}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-describedby={notFound || geoDown ? `${inputId}-msg` : undefined}
            aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
            autoComplete="off"
            autoFocus={autoFocus}
            value={q}
            placeholder={hero ? t("search_placeholder") : t("search_compact_placeholder")}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
              setOpen(true);
              setNotFound(null);
              setGeoDown(false);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 120)}
            onKeyDown={onKey}
            className={cn(
              "w-full rounded-md border bg-sheet text-deed placeholder:text-graphite/80 transition-colors focus:border-permit focus:outline-none focus-visible:outline-2 focus-visible:outline-permit",
              hero ? "h-14 border-deed/40 pl-12 pr-4 text-body" : "h-11 border-hairline pl-9 pr-3 text-sm",
            )}
          />
        </div>
        {hero && (
          <Button type="submit" size="lg" className="h-14 px-7" disabled={resolve.isPending}>
            {resolve.isPending ? tr("Looking up", "Buscando") : t("search_submit")}
          </Button>
        )}
      </div>

      {geoDown && (
        <p id={`${inputId}-msg`} role="alert" className="mt-3 rounded-md border border-hairline bg-sheet px-4 py-3 text-base text-deed">
          {tr("Address lookup is unavailable right now. Sample addresses still work.", "La búsqueda de direcciones no está disponible ahora. Las direcciones de muestra siguen funcionando.")}
        </p>
      )}
      {notFound && (
        <div id={`${inputId}-msg`} role="status" className="mt-3 rounded-md border border-hairline bg-sheet px-4 py-3">
          <p className="text-base text-deed">
            {tr("We couldn't match this address. Check the street number, or pick a sample address.", "No pudimos encontrar esta dirección. Revise el número de la calle o elija una dirección de muestra.")}
          </p>
          {notFound.length > 0 ? (
            <>
              <p className="mt-1 text-sm text-graphite">{tr("Did you mean one of these?", "¿Quiso decir alguna de estas?")}</p>
              <ul className="mt-2 space-y-1">
                {notFound.map((c) => (
                  <li key={c.address_id}>
                    <button type="button" onClick={() => go(c.address_id)} onFocus={() => prefetch(c.address_id)} className="min-h-11 text-base text-permit underline-offset-4 hover:underline">
                      {c.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-1 text-sm text-graphite">{t("search_hint")}</p>
          )}
        </div>
      )}

      {showList && (
        <div
          className={cn(
            "absolute left-0 right-0 z-50 mt-2 overflow-hidden rounded-lg border border-hairline bg-popover shadow-float motion-safe:animate-in motion-safe:fade-in-0 duration-150",
            hero && "sm:right-[11.5rem]",
          )}
        >
          {isLoading ? (
            <p className="px-4 py-3 text-sm text-graphite">{t("search_loading")}</p>
          ) : results.length === 0 ? (
            <div className="px-4 py-3">
              <p className="text-sm text-deed">{tr("No sample address matches. Press Enter to look up any address in CA, NJ or MA.", "Ninguna dirección de muestra coincide. Presione Enter para buscar cualquier dirección en CA, NJ o MA.")}</p>
            </div>
          ) : (
            <ul id={listId} role="listbox" className="max-h-80 overflow-auto py-1">
              {results.map((r, i) => (
                <li
                  key={r.address_id}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    go(r.address_id);
                  }}
                  onMouseEnter={() => { setActive(i); prefetch(r.address_id); }}
                  className={cn("flex cursor-pointer items-start gap-3 px-4 py-2.5", i === active ? "bg-muted" : "")}
                >
                  <MapPin className="mt-1 size-4 shrink-0 text-graphite" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block truncate text-base text-deed">{r.label}</span>
                    {r.legal_city && r.legal_city !== r.postal_city && (
                      <span className="block text-sm text-graphite">{tr(`Legally in ${r.legal_city}`, `Legalmente en ${r.legal_city}`)}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </form>
  );
}
