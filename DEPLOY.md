# Deploying Tenantly

Three pieces, all free-tier:

| Piece | Where | Why |
|---|---|---|
| API (FastAPI, in memory, no model on lookups) | Render free web service, from `render.yaml` | Runs the Docker image straight from this repository |
| Web app (`frontend/`) | Lovable publish, custom domain `tenantlyrent.me` | Already built there |
| Fallback data | jsDelivr over the `snapshot-v0.3` tag | The app keeps working when the free API instance is asleep |

## 1. API on Render
1. Render dashboard, **New, Blueprint**, pick the `Esh90/Tenantly` repository. It reads `render.yaml`.
2. When asked, enter the secrets (copy the values from your local `.env`; never commit them):
   `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `RESEND_API_KEY`, and `ALERT_FROM`.
   Leave `PUBLIC_INGEST_ENABLED=true` for judging (no token). If you lock the API later, set
   `ADMIN_TOKEN=tenantly-demo` (the value documented in the README).
   In Render this is **Service → Environment Variables**:
   `RESEND_API_KEY=<secret>`. Set `PUBLIC_APP_URL` to the public web origin so notification links
   return to the affected property's analysis.
3. Wait for the first build (a few minutes). The API is then at `https://tenantly-api.onrender.com`
   (Render shows the exact URL). Check `https://<url>/v1/health` and `https://<url>/docs`.
4. In the GitHub repository, **Settings, Secrets and variables, Actions, Variables**: add `API_BASE_URL`
   with that URL. The `keepwarm` workflow then pings it every 10 minutes so the free instance rarely sleeps.

Spend protection: lookups never call a model. Hackathon demo ingestion is public and its only
usage cap is `INGEST_BUDGET_USD`; set `PUBLIC_INGEST_ENABLED=false` after judging to disable public
ingestion. When the paid budget is used up or the primary provider fails, the free Groq model takes
over, and every quote is still verified byte for byte. If both providers fail, the job visibly
fails without publishing anything.

Watched addresses and notification attempts use SQLite at `ALERT_DB_PATH` (default:
`artifacts/watch/alerts.sqlite3`). For persistence across Render deploys/restarts, attach a Render
persistent disk and set `ALERT_DB_PATH=/var/data/alerts.sqlite3`. Without a disk, Render's ephemeral
filesystem can be replaced during a deploy.

## 2. Web app
1. In Lovable, project settings, environment variables:
   `VITE_API_BASE_URL` = the Render URL, `VITE_SNAPSHOT_BASE_URL` =
   `https://cdn.jsdelivr.net/gh/Esh90/Tenantly@snapshot-v0.3/artifacts/web`.
2. Publish, then **Settings, Domains**, connect `tenantlyrent.me`. Lovable shows the DNS records
   (an A record and a TXT record); add them in Namecheap, Advanced DNS.
3. No map key is needed: the map uses OpenFreeMap tiles.
4. Never add `RESEND_API_KEY` to Lovable or Vercel. The browser calls Tenantly's API; only the Render
   backend calls Resend.

## 3. After new data
`make all` regenerates everything; commit, then publish a new snapshot tag (orphan `snapshot` branch) and
update `VITE_SNAPSHOT_BASE_URL`.
