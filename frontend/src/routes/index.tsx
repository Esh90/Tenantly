import { createFileRoute, Link } from "@tanstack/react-router";
import { AddressSearch } from "@/components/tenantly/AddressSearch";
import { MapPanel, type MapPoint } from "@/components/map/MapPanel";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { useI18n } from "@/lib/i18n";
import buildingPhoto from "@/assets/home-building.jpg";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Tenantly — What housing law reaches your door?" },
      {
        name: "description",
        content:
          "Type an apartment address in California, New Jersey or Massachusetts. See every rule that applies there, quoted from the law, for any date.",
      },
      { property: "og:title", content: "Tenantly — What housing law reaches your door?" },
      { property: "og:description", content: "Every rental rule that reaches an address, quoted from the law, for any date." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Home,
});

const SAMPLES = [
  { id: "A0016", street: "3515 Fillmore St, San Francisco", en: "Built before 1979", es: "Construido antes de 1979" },
  { id: "A0118", street: "18-34 Kingbird Rd, Dorchester", en: "Mailed as Dorchester", es: "Correo como Dorchester" },
  { id: "A0019", street: "3820 Haines St, San Diego", en: "Year built not in public records", es: "Año de construcción no está en registros" },
  { id: "A0002", street: "1031-1035 Clinton St, Hoboken", en: "Local ban, text not supplied", es: "Prohibición local, texto no proporcionado" },
  { id: "A0003", street: "876-878 S 14th St, Newark", en: "Bad ZIP handled", es: "Código postal erróneo manejado" },
];

const CITY_DOTS: MapPoint[] = [
  ["San Francisco", 37.7749, -122.4194], ["Oakland", 37.8044, -122.2712], ["Los Angeles", 34.0522, -118.2437],
  ["San Diego", 32.7157, -117.1611], ["Hoboken", 40.744, -74.0324], ["Jersey City", 40.7178, -74.0431],
  ["Newark", 40.7357, -74.1724], ["Boston", 42.3601, -71.0589], ["Cambridge", 42.3736, -71.1097], ["Somerville", 42.3876, -71.0995],
].map(([n, lat, lon]) => ({ id: String(n), label: String(n), lat: Number(lat), lon: Number(lon), kind: "city" as const }));

function Home() {
  const { tr, t } = useI18n();
  const coverage = [
    { state: "California", cities: "San Francisco, Los Angeles, San Diego, Oakland", note: tr("State cap yields to older local ordinances", "El tope estatal cede ante ordenanzas locales") },
    { state: "New Jersey", cities: "Hoboken, Newark, Jersey City", note: tr("New rent-software act starts July 1, 2027", "Nueva ley de software empieza el 1 de julio de 2027") },
    { state: "Massachusetts", cities: "Boston, Cambridge, Somerville", note: tr("Cities may not adopt rent control", "Las ciudades no pueden adoptar control de rentas") },
  ];
  const steps = [
    { n: 1, title: tr("We read the official text", "Leemos el texto oficial"), body: tr("Statutes, ordinances and official guidance for each state and city, saved on October 1, 2026.", "Leyes, ordenanzas y guías oficiales de cada estado y ciudad, guardadas el 1 de octubre de 2026.") },
    { n: 2, title: tr("We keep only rules we can quote word for word", "Solo conservamos reglas que podemos citar palabra por palabra"), body: tr("Every rule carries the exact passage it came from. If the quote isn't in the law, the rule is thrown away.", "Cada regla lleva el pasaje exacto de donde vino. Si la cita no está en la ley, la regla se descarta.") },
    { n: 3, title: tr("We check them against your building and date", "Las comparamos con su edificio y fecha"), body: tr("The legal city, the year built, the unit count and each rule's start date decide what reaches you.", "La ciudad legal, el año de construcción, las unidades y la fecha de inicio de cada regla deciden qué le alcanza.") },
  ];

  return (
    <>
      <section className="mx-auto grid max-w-[1280px] gap-12 px-5 pb-16 pt-12 md:px-8 lg:grid-cols-12 lg:gap-14 lg:pb-24 lg:pt-20">
        <div className="lg:col-span-7">
          <h1 className="max-w-[15ch] text-[34px] leading-[1.12] text-deed md:text-[44px]">
            {tr("What housing law reaches your door?", "¿Qué ley de vivienda llega a su puerta?")}
          </h1>
          <p className="mt-5 max-w-[56ch] text-lg leading-[1.5] text-graphite">
            {tr(
              "Type an apartment address in California, New Jersey or Massachusetts. See every rule that applies there, quoted from the law, for any date.",
              "Escriba una dirección en California, Nueva Jersey o Massachusetts. Vea cada regla que aplica allí, citada de la ley, para cualquier fecha.",
            )}
          </p>

          <div className="mt-9 max-w-[660px] rounded-lg border border-hairline bg-sheet p-4 sm:p-5">
            <AddressSearch variant="hero" />
          </div>

          <div className="mt-10 max-w-[660px]">
            <h2 className="text-sm font-semibold text-graphite">{tr("Try one of these", "Pruebe una de estas")}</h2>
            <ul className="mt-2 divide-y divide-hairline border-y border-hairline">
              {SAMPLES.map((s) => (
                <li key={s.id}>
                  <Link to="/a/$addressId" params={{ addressId: s.id }} className="group flex flex-col gap-0.5 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                    <span className="text-base font-medium text-deed underline-offset-4 group-hover:text-permit group-hover:underline">{s.street}</span>
                    <span className="text-sm text-graphite">{tr(s.en, s.es)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <aside className="lg:col-span-5" aria-label={tr("Coverage", "Cobertura")}>
          <figure className="overflow-hidden rounded-lg border border-hairline bg-sheet">
            <MapPanel points={CITY_DOTS} fit="points" padding={36} height={300} ariaLabel={tr("Map of the ten cities Tenantly covers", "Mapa de las diez ciudades que cubre Tenantly")} />
            <figcaption className="border-t border-hairline px-4 py-2.5 text-sm text-graphite">
              {tr("Ten cities in three states, 500 sample buildings.", "Diez ciudades en tres estados, 500 edificios de muestra.")}
            </figcaption>
          </figure>
          <table className="mt-6 w-full text-left">
            <caption className="sr-only">{tr("Coverage by state", "Cobertura por estado")}</caption>
            <thead>
              <tr className="border-b-2 border-deed text-sm text-graphite">
                <th className="py-2 pr-3 font-medium">{tr("State", "Estado")}</th>
                <th className="py-2 pr-3 font-medium">{tr("Cities covered", "Ciudades")}</th>
                <th className="hidden py-2 font-medium sm:table-cell">{tr("Notes", "Notas")}</th>
              </tr>
            </thead>
            <tbody>
              {coverage.map((c) => (
                <tr key={c.state} className="border-b border-hairline align-top">
                  <td className="py-3 pr-3 text-base font-semibold text-deed">{c.state}</td>
                  <td className="py-3 pr-3 text-sm text-deed">{c.cities}<span className="mt-1 block text-graphite sm:hidden">{c.note}</span></td>
                  <td className="hidden py-3 text-sm text-graphite sm:table-cell">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </aside>
      </section>

      <section className="border-y border-hairline bg-sheet">
        <div className="mx-auto grid max-w-[1280px] gap-12 px-5 py-16 md:px-8 lg:grid-cols-12 lg:py-24">
          <div className="lg:col-span-5">
            <h2 className="text-2xl text-deed md:text-3xl">{tr("How Tenantly reads the law", "Cómo lee Tenantly la ley")}</h2>
            <figure className="mt-8 hidden lg:block">
              <img src={buildingPhoto} alt="Four-story apartment building with bay windows and a fire escape" width={1280} height={1600} loading="lazy" className="aspect-[4/5] w-full max-w-[400px] rounded-lg border border-hairline object-cover" />
              <figcaption className="mt-3 flex items-start gap-3 text-sm text-graphite">
                <span className="mt-2 h-px w-8 shrink-0 bg-graphite" aria-hidden="true" />
                {tr("Built 1926, 21 units. One of the sample buildings Tenantly reads against.", "Construido en 1926, 21 unidades. Uno de los edificios de muestra.")}
              </figcaption>
            </figure>
          </div>
          <div className="lg:col-span-7">
            <ol>
              {steps.map((s) => (
                <li key={s.n} className="grid grid-cols-[2.75rem_1fr] gap-4 border-t border-hairline py-7 first:border-t-0 first:pt-0">
                  <span className="flex size-9 items-center justify-center rounded-full border border-deed text-base font-semibold text-deed tabular">{s.n}</span>
                  <div>
                    <h3 className="text-xl text-deed">{s.title}</h3>
                    <p className="mt-2 text-body text-graphite prose-width">{s.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <figure className="ledger-rail mt-4 border-l-deed pl-5">
              <blockquote className="law-quote text-deed">
                "A landlord may not demand or receive security, however denominated,{" "}
                <mark className="mark-highlight">in an amount or value in excess of an amount equal to one month's rent</mark>."
              </blockquote>
              <figcaption className="mt-2 text-sm text-graphite">Cal. Civ. Code § 1950.5(c)(1)</figcaption>
            </figure>

            <div className="mt-12 border-t border-hairline pt-7">
              <div className="flex flex-wrap items-center gap-3">
                <ResultPill result="unknown" />
                <h3 className="text-lg text-deed">{tr("What \u201cCan't tell yet\u201d means", "Qué significa \u201cAún no se sabe\u201d")}</h3>
              </div>
              <p className="mt-2 text-body text-graphite prose-width">
                {tr(
                  "Some rules depend on a fact public records don't hold, like the year a building was finished. Tenantly shows which fact is missing and lets you add it, instead of guessing.",
                  "Algunas reglas dependen de un dato que los registros públicos no tienen, como el año en que se terminó un edificio. Tenantly muestra qué dato falta y le permite agregarlo, en vez de adivinar.",
                )}
              </p>
            </div>
          </div>
        </div>
      </section>

      <p className="mx-auto mt-14 max-w-[1280px] px-5 text-base font-medium text-deed md:px-8">{t("disclaimer")}</p>
    </>
  );
}
