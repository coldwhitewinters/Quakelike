#!/usr/bin/env bash
# deploy.sh - Deploy Quakelike to Azure Container Apps
#
# First-time setup:
#   ./deploy.sh
#
# Redeploy after code changes:
#   ./deploy.sh --update
#
# Options:
#   --update      Rebuild image and update existing deployment (skip infra provisioning)
#   -g NAME       Resource group name        (default: quakelike-rg)
#   -l LOCATION   Azure region               (default: westeurope)
#   -a NAME       Container app name         (default: quakelike)
#   -r NAME       ACR registry name          (default: quakelikeacr)
#   -s NAME       Storage account name       (default: quakelikestorage)
#   -e NAME       Container Apps env name    (default: quakelike-env)

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
RESOURCE_GROUP="quakelike-rg"
LOCATION="westeurope"
APP_NAME="quakelike"
ACR_NAME="quakelikeacr"
STORAGE_ACCOUNT="quakelikestorage"
ENVIRONMENT_NAME="quakelike-env"
FILE_SHARE_NAME="saves"
STORAGE_MOUNT_NAME="saves-mount"
UPDATE_ONLY=false

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --update) UPDATE_ONLY=true; shift ;;
    -g) RESOURCE_GROUP="$2"; shift 2 ;;
    -l) LOCATION="$2"; shift 2 ;;
    -a) APP_NAME="$2"; shift 2 ;;
    -r) ACR_NAME="$2"; shift 2 ;;
    -s) STORAGE_ACCOUNT="$2"; shift 2 ;;
    -e) ENVIRONMENT_NAME="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

ACR_SERVER="${ACR_NAME}.azurecr.io"
IMAGE="${ACR_SERVER}/${APP_NAME}:latest"

# ── Prerequisites ──────────────────────────────────────────────────────────────
echo "==> Checking prerequisites..."

if ! command -v az &>/dev/null; then
  echo "ERROR: Azure CLI not found. Install from https://aka.ms/installazurecli" >&2
  exit 1
fi
if ! az account show &>/dev/null; then
  echo "ERROR: Not logged in. Run: az login" >&2
  exit 1
fi
if [[ ! -f "Dockerfile" ]]; then
  echo "ERROR: Run this script from the repository root." >&2
  exit 1
fi

echo "    Subscription: $(az account show --query name -o tsv)"
echo "    Resource group: ${RESOURCE_GROUP}"
echo "    Location: ${LOCATION}"
echo "    App: ${APP_NAME}"
echo ""

# ── Update-only path (rebuild image + restart app) ────────────────────────────
if [[ "$UPDATE_ONLY" == true ]]; then
  echo "==> Rebuilding and pushing image..."
  az acr build --registry "${ACR_NAME}" --image "${APP_NAME}:latest" .

  echo "==> Updating container app..."
  az containerapp update \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --image "${IMAGE}" \
    --output none

  APP_URL=$(az containerapp show \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv)

  echo ""
  echo "================================================================"
  echo "  Update complete!"
  echo "  App URL: https://${APP_URL}"
  echo "================================================================"
  exit 0
fi

# ── Full deployment ────────────────────────────────────────────────────────────

echo "==> Installing Container Apps CLI extension..."
az extension add --name containerapp --upgrade --yes 2>/dev/null || true

echo "==> Creating resource group..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

echo "==> Creating Azure Container Registry..."
az acr create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --admin-enabled true \
  --location "${LOCATION}" \
  --output none

echo "==> Building and pushing Docker image..."
az acr build \
  --registry "${ACR_NAME}" \
  --image "${APP_NAME}:latest" \
  .

echo "==> Creating storage account..."
az storage account create \
  --name "${STORAGE_ACCOUNT}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --sku Standard_LRS \
  --output none

STORAGE_KEY=$(az storage account keys list \
  --resource-group "${RESOURCE_GROUP}" \
  --account-name "${STORAGE_ACCOUNT}" \
  --query "[0].value" \
  --output tsv)

echo "==> Creating file share for game saves..."
az storage share create \
  --name "${FILE_SHARE_NAME}" \
  --account-name "${STORAGE_ACCOUNT}" \
  --account-key "${STORAGE_KEY}" \
  --quota 5 \
  --output none

echo "==> Creating Container Apps Environment..."
az containerapp env create \
  --name "${ENVIRONMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

echo "==> Attaching Azure Files storage to environment..."
az containerapp env storage set \
  --name "${ENVIRONMENT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --storage-name "${STORAGE_MOUNT_NAME}" \
  --azure-file-account-name "${STORAGE_ACCOUNT}" \
  --azure-file-account-key "${STORAGE_KEY}" \
  --azure-file-share-name "${FILE_SHARE_NAME}" \
  --access-mode ReadWrite \
  --output none

echo "==> Retrieving ACR credentials..."
ACR_USERNAME=$(az acr credential show \
  --name "${ACR_NAME}" \
  --query username \
  --output tsv)
ACR_PASSWORD=$(az acr credential show \
  --name "${ACR_NAME}" \
  --query "passwords[0].value" \
  --output tsv)

echo "==> Creating Container App..."
if az containerapp show --name "${APP_NAME}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
  echo "    Container App already exists, skipping create."
else
  az containerapp create \
    --name "${APP_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --environment "${ENVIRONMENT_NAME}" \
    --image "${IMAGE}" \
    --registry-server "${ACR_SERVER}" \
    --registry-username "${ACR_USERNAME}" \
    --registry-password "${ACR_PASSWORD}" \
    --target-port 8080 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1.0Gi \
    --env-vars FLASK_DEBUG=false CORS_ORIGINS=https://placeholder.invalid \
    --output none
fi

echo "==> Attaching saves volume and fixing CORS..."
APP_URL=$(az containerapp show \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

# Export current app definition, patch it, and apply
TMPFILE=$(mktemp /tmp/quakelike-app-XXXXXX.yaml)
trap 'rm -f "${TMPFILE}"' EXIT
az containerapp show \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --output yaml > "${TMPFILE}"

# Update CORS_ORIGINS (only needed on first deploy; on re-runs the placeholder is already gone)
if grep -q "placeholder.invalid" "${TMPFILE}"; then
  sed -i "s|value: https://placeholder.invalid|value: https://${APP_URL}|g" "${TMPFILE}"
fi

# Inject volumeMounts into container if not already present
if ! grep -q "volumeMounts" "${TMPFILE}"; then
  sed -i "s|      resources:|      volumeMounts:\n      - mountPath: /app/saves\n        volumeName: saves-vol\n      resources:|g" "${TMPFILE}"
fi

# Inject volumes block if not already present
if ! grep -q "storageType: AzureFile" "${TMPFILE}"; then
  sed -i "s|    terminationGracePeriodSeconds: null|    terminationGracePeriodSeconds: null\n    volumes:\n    - name: saves-vol\n      storageType: AzureFile\n      storageName: ${STORAGE_MOUNT_NAME}|g" "${TMPFILE}"
fi

az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --yaml "${TMPFILE}" \
  --output none

rm -f "${TMPFILE}"

echo ""
echo "================================================================"
echo "  Deployment complete!"
echo "  App URL: https://${APP_URL}"
echo "  Resource group: ${RESOURCE_GROUP}"
echo "  ACR: ${ACR_SERVER}"
echo "  Storage: ${STORAGE_ACCOUNT}/${FILE_SHARE_NAME}"
echo ""
echo "  To redeploy after code changes:"
echo "    ./deploy.sh --update"
echo ""
echo "  To tear down all resources:"
echo "    az group delete --name ${RESOURCE_GROUP} --yes --no-wait"
echo "================================================================"
