import type { ReactNode } from "react";

export function PageHeader({ title, lede, aside, children }: { title: string; lede?: ReactNode; aside?: ReactNode; children?: ReactNode }) {
  return (
    <header className="border-b border-hairline pb-8 pt-12 md:pb-10 md:pt-16">
      <div className="grid gap-6 lg:grid-cols-12 lg:items-end">
        <div className="lg:col-span-8">
          <h1 className="text-[30px] leading-tight text-deed md:text-4xl">{title}</h1>
          {lede && <p className="mt-4 max-w-[62ch] text-lg leading-[1.5] text-graphite">{lede}</p>}
        </div>
        {aside && <div className="lg:col-span-4 lg:justify-self-end">{aside}</div>}
      </div>
      {children}
    </header>
  );
}

export function Page({ children, narrow }: { children: ReactNode; narrow?: boolean }) {
  return <div className={narrow ? "mx-auto max-w-[920px] px-5 md:px-8" : "mx-auto max-w-[1280px] px-5 md:px-8"}>{children}</div>;
}

export function SectionTitle({ title, sub, id }: { title: string; sub?: string; id?: string }) {
  return (
    <div className="border-b-2 border-deed pb-3" id={id}>
      <h2 className="text-xl text-deed md:text-2xl">{title}</h2>
      {sub && <p className="mt-1 max-w-[68ch] text-body text-graphite">{sub}</p>}
    </div>
  );
}
