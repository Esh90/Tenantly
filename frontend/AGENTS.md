<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture rules
- All data access goes through `src/lib/api/api.ts` (hooks in `hooks.ts`); components never call fetch — keeps one swap point.
- `src/config.ts` `API_BASE_URL` is the only mock/live switch; empty string routes `client.request` to the in-memory `mock.ts`.
- `src/lib/api/types.ts` mirrors the live API exactly; never edit shapes there, add helper types in `api.ts` instead.
- UI strings live in `src/lib/i18n/en.ts` and `es.ts`; API text arrives as Bilingual and is rendered with `tb()`.
- TanStack Router replaces React Router from the spec — the platform fixes the router.
