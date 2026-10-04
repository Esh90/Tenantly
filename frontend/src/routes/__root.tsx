import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { useEffect } from "react";

import { reportLovableError } from "../lib/lovable-error-reporting";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { FallbackBanner } from "@/components/layout/FallbackBanner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { LawSheetsProvider } from "@/components/tenantly/LawSheets";

function NotFoundComponent() {
  const { t } = useI18n();
  return (
    <div className="mx-auto max-w-[1280px] px-5 pt-20 md:px-8 md:pt-28">
      <h1 className="text-3xl md:text-4xl text-deed">{t("notfound_title")}</h1>
      <p className="mt-4 text-body text-graphite prose-width">{t("notfound_body")}</p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Button asChild>
          <Link to="/">{t("go_home")}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/rules">{t("nav_rules")}</Link>
        </Button>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md">
        <h1 className="text-2xl text-foreground">This page didn't load</h1>
        <p className="mt-2 text-base text-muted-foreground">
          Something went wrong on our end. You can try again or go to the home page.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            onClick={() => {
              router.invalidate();
              reset();
            }}
          >
            Try again
          </Button>
          <Button variant="outline" asChild>
            <a href="/">Go to the home page</a>
          </Button>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function SkipLink() {
  const { t } = useI18n();
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[60] focus:rounded-md focus:bg-deed focus:px-4 focus:py-2 focus:text-primary-foreground"
    >
      {t("skip")}
    </a>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <TooltipProvider delayDuration={200}>
          <LawSheetsProvider>
          <div className="flex min-h-screen flex-col">
            <SkipLink />
            <Header />
            <FallbackBanner />
            <main id="main" tabIndex={-1} className="flex-1 focus:outline-none">
              <Outlet />
            </main>
            <Footer />
          </div>
          <Toaster />
          </LawSheetsProvider>
        </TooltipProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
