import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { useI18n } from "@/lib/i18n";
import buildingPhoto from "@/assets/home-building.jpg";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About Tenantly" },
      { name: "description", content: "What Tenantly is, what it isn't, how evidence is graded, and where its information comes from." },
      { property: "og:title", content: "About Tenantly" },
      { property: "og:description", content: "What Tenantly is, what it isn't, and where its information comes from." },
    ],
  }),
  component: AboutPage,
});

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3 border-t border-hairline py-10 md:grid-cols-12 md:gap-10">
      <h2 className="text-xl text-deed md:col-span-4">{title}</h2>
      <div className="space-y-3 text-body text-deed md:col-span-8 [&_p]:max-w-[68ch]">{children}</div>
    </section>
  );
}

function AboutPage() {
  const { tr, t } = useI18n();
  const tiers: [string, string, string][] = [
    ["A", tr("Official text", "Texto oficial"), tr("We quote the law itself, character for character.", "Citamos la ley misma, carácter por carácter.")],
    ["B", tr("Official guidance", "Guía oficial"), tr("We quote guidance the government published about the law, not the law.", "Citamos la guía publicada por el gobierno, no la ley.")],
    ["C", tr("Text not supplied", "Texto no proporcionado"), tr("The law's text wasn't in our sources. Other materials show it exists, so we list it without quoting it as law.", "El texto no estaba en nuestras fuentes. Otros materiales muestran que existe; la listamos sin citarla como ley.")],
    ["C1", tr("Single source, unconfirmed", "Fuente única, sin confirmar"), tr("Only one supplied source mentions it, and we couldn't confirm it elsewhere.", "Solo una fuente la menciona y no pudimos confirmarla.")],
  ];
  return (
    <Page>
      <PageHeader title={tr("About Tenantly", "Acerca de Tenantly")} lede={tr("Tenantly tells renters which housing laws reach their apartment address on a given date, and shows the official words behind every rule.", "Tenantly indica qué leyes de vivienda alcanzan una dirección en una fecha dada y muestra las palabras oficiales de cada regla.")} />
      <div className="grid gap-10 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <Row title={tr("What Tenantly is", "Qué es Tenantly")}>
            <p>{tr("A reading of state and city housing law for three states and ten cities, matched to real buildings by map boundaries and public records. It covers rent increases, eviction protections, security deposits, application fees, tenant screening and rent-setting software.", "Una lectura de la ley de vivienda estatal y municipal para tres estados y diez ciudades, aplicada a edificios reales por límites del mapa y registros públicos.")}</p>
          </Row>
          <Row title={tr("What it isn't", "Qué no es")}>
            <ul className="list-disc space-y-2 pl-5">
              <li>{tr("Not legal advice. It describes what the law says, not what you should do.", "No es asesoría legal. Describe lo que dice la ley, no lo que usted debe hacer.")}</li>
              <li>{tr("Not a compliance certification for landlords.", "No es una certificación de cumplimiento para propietarios.")}</li>
              <li>{tr("It never suggests ways around a rule.", "Nunca sugiere formas de evadir una regla.")}</li>
            </ul>
          </Row>
          <Row title={tr("Evidence, explained", "La evidencia, explicada")}>
            <dl className="divide-y divide-hairline border-y border-hairline">
              {tiers.map(([k, l, d]) => (
                <div key={k} className="grid gap-1 py-4 sm:grid-cols-[13rem_1fr]">
                  <dt className="font-semibold">{l}</dt>
                  <dd className="text-base text-graphite">{d}</dd>
                </div>
              ))}
            </dl>
          </Row>
          <Row title={tr("Where the data comes from", "De dónde vienen los datos")}>
            <p>{tr("Law text and guidance from the project's starter pack of official documents. Addresses placed with the U.S. Census geocoder, with OpenStreetMap as a fallback. Building facts from county assessor rolls.", "Texto legal y guías del paquete inicial de documentos oficiales. Direcciones ubicadas con el geocodificador del Censo de EE. UU., con OpenStreetMap como respaldo. Datos de edificios de los registros del tasador.")}</p>
            <p className="text-graphite">{tr("Sources retrieved October 1, 2026.", "Fuentes obtenidas el 1 de octubre de 2026.")}</p>
          </Row>
          <Row title={tr("Contact", "Contacto")}>
            <p>{tr("Found a mistake in a rule or a building record? Write to corrections@tenantly.example and include the address or rule.", "¿Encontró un error? Escriba a corrections@tenantly.example e incluya la dirección o regla.")}</p>
          </Row>
          <p className="border-t border-deed/70 pt-5 text-base font-medium text-deed">{t("disclaimer")}</p>
        </div>
        <figure className="hidden lg:col-span-4 lg:block">
          <div className="sticky top-[88px] pt-10">
            <img src={buildingPhoto} alt="Apartment building facade with bay windows" width={1280} height={1600} loading="lazy" className="aspect-[3/4] w-full rounded-lg border border-hairline object-cover" />
            <figcaption className="mt-3 text-sm text-graphite">{tr("The law reaches people through buildings. Tenantly starts from the address.", "La ley llega a las personas a través de los edificios. Tenantly empieza por la dirección.")}</figcaption>
          </div>
        </figure>
      </div>
    </Page>
  );
}
