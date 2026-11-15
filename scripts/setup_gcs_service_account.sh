#!/usr/bin/env bash
# Steps 7-10 of the original README ("Create Service Account" -> "Add Key"),
# done from the CLI instead of the console, with two hardening changes:
#   * the service account gets roles/storage.objectAdmin on THIS bucket only
#     (the README suggests project-wide Owner, which is far more than DVC needs);
#   * the key path is stored with `--local`, i.e. in .dvc/config.local, which
#     git ignores - the upstream repo committed a credentialpath into .dvc/config.
#
# This lab was run with Application Default Credentials (`gcloud auth
# application-default login`), which DVC picks up automatically. Use this script
# when a machine without your user login (e.g. CI) needs access.
#
# Usage: scripts/setup_gcs_service_account.sh [project] [bucket] [sa-name]
set -euo pipefail

PROJECT="${1:-cloud-runner-lab-513420}"
BUCKET="${2:-dvc-lab1-cc-segmentation-shivam}"
SA_NAME="${3:-dvc-lab1}"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
KEY_FILE="secrets/${SA_NAME}-key.json"

gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" \
  --display-name "DVC Lab 1 remote access"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member "serviceAccount:${SA_EMAIL}" --role roles/storage.objectAdmin

mkdir -p secrets && chmod 700 secrets
gcloud iam service-accounts keys create "$KEY_FILE" --iam-account "$SA_EMAIL"
chmod 600 "$KEY_FILE"

# README: `dvc remote modify <name> credentialpath <key.json>`  (kept out of git via --local)
dvc remote modify --local gcsremote credentialpath "$(pwd)/${KEY_FILE}"
echo "Done. Verify with: dvc status -c"
