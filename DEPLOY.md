# Deploying Tenantly

Three pieces, all free-tier:

| Piece | Where | Why |
|---|---|---|
| API (FastAPI, in memory, no model on lookups) | Render free web service, from `render.yaml` | Runs the Docker image straight from this repository |
| Web app (`frontend/`) | Lovable publish, custom domain `tenantlyrent.me` | Already built there |
| Fallback data | jsDelivr over the `snapshot-v0.3` tag | The app keeps working when the free API instance is asleep |

## 1. API on Render
1. Render dashboard, **New, Blueprint**, pick the `Esh90/Tenantly` repository. It reads `render.yaml`.
2. When asked, enter the three secrets (copy the values from your local `.env`; never commit them):
   `ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, `GROQ_API_KEY`.
3. Wait for the first build (a few minutes). The API is then at `https://tenantly-api.onrender.com`
   (Render shows the exact URL). Check `https://<url>/v1/health` and `https://<url>/docs`.
4. In the GitHub repository, **Settings, Secrets and variables, Actions, Variables**: add `API_BASE_URL`
   with that URL. The `keepwarm` workflow then pings it every 10 minutes so the free instance rarely sleeps.

Spend protection: lookups never call a model. Ingest is admin-only (`X-Admin-Token`) and capped by
`INGEST_BUDGET_USD`; when the paid budget is used up the free Groq model takes over, and every quote is
still verified byte for byte.

## 2. Web app
1. In Lovable, project settings, environment variables:
   `VITE_API_BASE_URL` = the Render URL, `VITE_SNAPSHOT_BASE_URL` =
   `https://cdn.jsdelivr.net/gh/Esh90/Tenantly@snapshot-v0.3/artifacts/web`.
2. Publish, then **Settings, Domains**, connect `tenantlyrent.me`. Lovable shows the DNS records
   (an A record and a TXT record); add them in Namecheap, Advanced DNS.
3. No map key is needed: the map uses OpenFreeMap tiles.

## 3. After new data
`make all` regenerates everything; commit, then publish a new snapshot tag (orphan `snapshot` branch) and
update `VITE_SNAPSHOT_BASE_URL`.
