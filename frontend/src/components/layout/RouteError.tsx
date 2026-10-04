import { useEffect } from "react";
import { Link, useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { reportLovableError } from "@/lib/lovable-error-reporting";

/** Per-route error boundary: keeps header and footer, offers a reset. */
export function RouteError({ error, reset }: ErrorComponentProps) {
  const { tr } = useI18n();
  const router = useRouter();
  useEffect(() => {
    console.error(error);
    reportLovableError(error, { boundary: "tanstack_route_error_component" });
  }, [error]);
  return (
    <div className="mx-auto max-w-[1280px] px-5 pt-16 md:px-8 md:pt-24">
      <h1 className="text-3xl text-deed">{tr("This page didn't load", "Esta página no cargó")}</h1>
      <p role="alert" className="mt-3 max-w-[60ch] text-body text-graphite">
        {tr("Part of this page stopped working. Reload this section, or go back to the home page.", "Una parte de esta página dejó de funcionar. Recargue esta sección o vuelva a la página de inicio.")}
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Button onClick={() => { router.invalidate(); reset(); }}>{tr("Reload this section", "Recargar esta sección")}</Button>
        <Button asChild variant="outline"><Link to="/">{tr("Go to the home page", "Ir a la página de inicio")}</Link></Button>
      </div>
    </div>
  );
}
