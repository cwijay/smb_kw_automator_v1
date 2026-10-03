#!/usr/bin/env bash
# One-time GCP setup for the Keel pilot. Safe to re-run: existing resources are left alone.
# Needs: gcloud (logged in as a project owner), a Neon database, an R2 bucket with an access key.
#
#   PROJECT=my-project REGION=us-central1 GITHUB_REPO=owner/repo ./infra/cloudrun/bootstrap.sh
#
# Afterwards, set the GitHub repository variables it prints, add the secret values, and push to main.
set -euo pipefail
: "${PROJECT:?set PROJECT}" "${REGION:?set REGION}" "${GITHUB_REPO:?set GITHUB_REPO (owner/repo)}"
gc() { gcloud --project "$PROJECT" "$@"; }
exists() { "$@" >/dev/null 2>&1; }

gc services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

exists gc artifacts repositories describe keel --location "$REGION" ||
  gc artifacts repositories create keel --repository-format docker --location "$REGION"

# Service accounts: runtime (api, web, worker), migrator (owner DB URL only), deployer (GitHub Actions).
for sa in keel-runtime keel-migrator keel-deployer; do
  exists gc iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" ||
    gc iam service-accounts create "$sa"
done
RUNTIME="keel-runtime@$PROJECT.iam.gserviceaccount.com"
MIGRATOR="keel-migrator@$PROJECT.iam.gserviceaccount.com"
DEPLOYER="keel-deployer@$PROJECT.iam.gserviceaccount.com"

# Secrets (values added separately, never in this script or in git).
RUNTIME_SECRETS="keel-database-url keel-s3-access-key-id keel-s3-secret-access-key keel-openai-api-key keel-google-api-key"
for s in $RUNTIME_SECRETS keel-database-owner-url; do
  exists gc secrets describe "$s" || gc secrets create "$s" --replication-policy automatic
done
for s in $RUNTIME_SECRETS; do
  gc secrets add-iam-policy-binding "$s" --member "serviceAccount:$RUNTIME" --role roles/secretmanager.secretAccessor >/dev/null
done
for s in keel-database-url keel-database-owner-url; do
  gc secrets add-iam-policy-binding "$s" --member "serviceAccount:$MIGRATOR" --role roles/secretmanager.secretAccessor >/dev/null
done

# Deployer: push images, deploy services/jobs, act as the two runtime identities.
for role in roles/run.admin roles/artifactregistry.writer; do
  gc projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$DEPLOYER" --role "$role" >/dev/null
done
for sa in "$RUNTIME" "$MIGRATOR"; do
  gc iam service-accounts add-iam-policy-binding "$sa" --member "serviceAccount:$DEPLOYER" \
    --role roles/iam.serviceAccountUser >/dev/null
done

# GitHub OIDC (Workload Identity Federation): no long-lived keys in GitHub.
exists gc iam workload-identity-pools describe github --location global ||
  gc iam workload-identity-pools create github --location global
exists gc iam workload-identity-pools providers describe github --location global --workload-identity-pool github ||
  gc iam workload-identity-pools providers create-oidc github --location global --workload-identity-pool github \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref \
    --attribute-condition "assertion.repository == '$GITHUB_REPO' && assertion.ref == 'refs/heads/main'"
NUMBER=$(gc projects describe "$PROJECT" --format 'value(projectNumber)')
POOL="projects/$NUMBER/locations/global/workloadIdentityPools/github"
gc iam service-accounts add-iam-policy-binding "$DEPLOYER" --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/$POOL/attribute.repository/$GITHUB_REPO" >/dev/null

# Scheduler runs the worker job every minute (it drains the queue and exits).
exists gc iam service-accounts describe "keel-scheduler@$PROJECT.iam.gserviceaccount.com" ||
  gc iam service-accounts create keel-scheduler
gc projects add-iam-policy-binding "$PROJECT" --role roles/run.invoker \
  --member "serviceAccount:keel-scheduler@$PROJECT.iam.gserviceaccount.com" >/dev/null
exists gc scheduler jobs describe keel-worker --location "$REGION" ||
  gc scheduler jobs create http keel-worker --location "$REGION" --schedule "* * * * *" --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/keel-worker:run" \
    --oauth-service-account-email "keel-scheduler@$PROJECT.iam.gserviceaccount.com"

cat <<OUT

Done. Next:
1. Add secret values, e.g.  printf %s "postgresql+psycopg://keel_app:...@.../neondb?sslmode=require" | gcloud --project $PROJECT secrets versions add keel-database-url --data-file=-
   (keel-database-owner-url uses keel_owner; run neon-bootstrap.sql on Neon first.)
2. GitHub repository variables (Settings → Secrets and variables → Actions → Variables):
   GCP_PROJECT=$PROJECT  GCP_REGION=$REGION
   GCP_WIF_PROVIDER=$POOL/providers/github
   GCP_DEPLOY_SA=$DEPLOYER
   KEEL_S3_BUCKET=<r2 bucket>  KEEL_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
3. Push to main. deploy.yml runs after CI is green. The first run creates keel-worker; the scheduler
   created above starts it every minute from then on.
OUT
