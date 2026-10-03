# Cloud Run pilot

| Piece | Runs as | Notes |
|---|---|---|
| `keel-web` (Next.js) | Cloud Run service, scales to 0 | The only origin the browser sees; `/api/*` is proxied to the API |
| `keel-api` (FastAPI) | Cloud Run service, scales to 0 | Runtime DB role `keel_app` (no BYPASSRLS); never sees the owner URL |
| `keel-worker` | Cloud Run Job, run every minute by Cloud Scheduler | `keel worker --drain`: empties the queue and exits, so nothing idles |
| `keel-migrate` | Cloud Run Job, run by each deploy | The only workload with the owner DB URL |
| Postgres | Neon (free tier) | pgvector, pg_trgm and citext; roles from `neon-bootstrap.sql` |
| Files | Cloudflare R2 (S3 API) | `KEEL_STORAGE_BACKEND=s3`; keys start with the org id |

**One-time setup**
1. On Neon: run `neon-bootstrap.sql` with your own passwords.
2. Create an R2 bucket and an access key scoped to it.
3. `PROJECT=… REGION=… GITHUB_REPO=owner/repo ./infra/cloudrun/bootstrap.sh`, then add the secret values and the
   GitHub repository variables it prints.

**Every deploy** (`.github/workflows/deploy.yml`, after CI is green on `main`, or run by hand): build and push the API
image → run `keel-migrate` → deploy the API → build the web image with the API URL → deploy web → deploy the worker
job → smoke test through the same-origin proxy.

**Not yet verified against a live project.** The manifests, bootstrap script and workflow are syntax-checked only; the
first real run is the test. If your organisation blocks `allUsers` invokers, the two `add-iam-policy-binding` steps in
`deploy.yml` fail; put the services behind a load balancer with IAP instead.
