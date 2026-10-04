import { useRef, useState } from "react";
import { FileUp, Loader2, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Jurisdiction } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const LIMIT = 200_000;
export const AUTO = "__auto__";

export type UploadValues = {
  token: string;
  title: string;
  jurisdiction: string;
  url: string;
  text: string;
  format: string;
  autoPublish: boolean;
};

type Props = {
  values: UploadValues;
  onChange: (v: UploadValues) => void;
  jurisdictions: Jurisdiction[];
  error: string;
  running: boolean;
  reading: boolean;
  onReadFile: (file: File) => Promise<void>;
  onSubmit: () => void;
};

export function UploadPanel({ values, onChange, jurisdictions, error, running, reading, onReadFile, onSubmit }: Props) {
  const { tr } = useI18n();
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const set = <K extends keyof UploadValues>(k: K, v: UploadValues[K]) => onChange({ ...values, [k]: v });
  const drop = (f: File | undefined) => f && void onReadFile(f);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="grid gap-8 lg:grid-cols-12"
    >
      <div className="space-y-5 lg:col-span-7">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            drop(e.dataTransfer.files[0]);
          }}
          className={cn("flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors", drag ? "border-permit bg-sage-tint" : "border-hairline bg-sheet")}
        >
          {reading ? <Loader2 className="size-8 animate-spin text-permit" /> : <FileUp className="size-8 text-graphite" aria-hidden="true" />}
          <p className="text-base text-deed">{tr("Drag and drop a PDF, DOCX or TXT here", "Arrastre aquí un PDF, DOCX o TXT")}</p>
          <p className="text-sm text-graphite">{tr("or", "o")}{" "}
            <button type="button" className="text-permit underline underline-offset-2" onClick={() => fileRef.current?.click()}>{tr("choose a file", "elija un archivo")}</button>
          </p>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md,text/plain,application/pdf" className="sr-only" aria-label={tr("Choose a file", "Elija un archivo")} onChange={(e) => drop(e.target.files?.[0])} />
        </div>
        <div>
          <div className="flex items-baseline justify-between">
            <Label htmlFor="txt" className="flex items-center gap-1.5"><ScrollText className="size-4" aria-hidden="true" />{tr("Or paste the legal text", "O pegue el texto legal")}</Label>
            <span className={cn("text-xs tabular", values.text.length > LIMIT ? "text-destructive" : "text-graphite")}>{values.text.length.toLocaleString()} / 200,000</span>
          </div>
          <Textarea id="txt" value={values.text} onChange={(e) => onChange({ ...values, text: e.target.value, format: "text" })} className="mt-1.5 min-h-[260px] bg-sheet text-base" placeholder={tr("Section 1. No landlord shall…", "Sección 1. Ningún arrendador deberá…")} />
        </div>
      </div>
      <div className="space-y-5 lg:col-span-5">
        <div>
          <Label htmlFor="ttl">{tr("Document title", "Título del documento")}</Label>
          <Input id="ttl" value={values.title} onChange={(e) => set("title", e.target.value)} className="mt-1.5 h-11 bg-sheet" placeholder={tr("Example Housing Ordinance 2026", "Ordenanza de vivienda de ejemplo 2026")} />
        </div>
        <div>
          <Label>{tr("Jurisdiction", "Jurisdicción")}</Label>
          <Select value={values.jurisdiction} onValueChange={(v) => set("jurisdiction", v)}>
            <SelectTrigger className="mt-1.5 h-11 bg-sheet"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={AUTO}>{tr("Detect from the document", "Detectar a partir del documento")}</SelectItem>
              {jurisdictions.filter((j) => j.level !== "county").map((j) => <SelectItem key={j.id} value={j.label}>{j.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <p className="mt-1 text-xs text-graphite">{tr("Effective and enactment dates are read from the text.", "Las fechas de vigencia y promulgación se leen del texto.")}</p>
        </div>
        <div>
          <Label htmlFor="url">{tr("Source URL (optional)", "URL de la fuente (opcional)")}</Label>
          <Input id="url" type="url" value={values.url} onChange={(e) => set("url", e.target.value)} className="mt-1.5 h-11 bg-sheet" placeholder="https://" />
        </div>
        <div>
          <Label htmlFor="tok">{tr("Admin token", "Token de administrador")}</Label>
          <Input id="tok" type="password" autoComplete="off" value={values.token} onChange={(e) => set("token", e.target.value)} className="mt-1.5 h-11 max-w-sm bg-sheet" />
          <p className="mt-1 text-xs text-graphite">{tr("Kept in this browser tab only.", "Se guarda solo en esta pestaña.")}</p>
        </div>
        <div className="flex items-start gap-3 rounded-md border border-hairline bg-sheet p-3">
          <Switch id="auto" checked={values.autoPublish} onCheckedChange={(v) => set("autoPublish", v)} />
          <Label htmlFor="auto" className="text-base font-normal leading-snug">
            {tr("Publish automatically if validation and the Judge both pass with high confidence.", "Publicar automáticamente si la validación y el Juez aprueban con alta confianza.")}
            <span className="block text-sm text-graphite">{tr("Anything uncertain goes to human review instead.", "Todo lo dudoso pasa a revisión humana.")}</span>
          </Label>
        </div>
        {error && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-base text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={running || reading}>
          {running ? tr("Analyzing…", "Analizando…") : tr("Extract & Analyze Law", "Extraer y analizar la ley")}
        </Button>
      </div>
    </form>
  );
}
