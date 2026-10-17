#!/usr/bin/env bash
# Build the four images with the public addresses of the sites, and push them to ECR. The
# websites take those addresses when they are built (NEXT_PUBLIC_*), so these images are
# tagged apart from the local ones and never replace them. Needs REGISTRY, TAG, and the
# hosts; provision.sh and update.sh pass them.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${REGISTRY:?}" "${TAG:?}" "${APP_HOST:?}" "${MEMORY_HOST:?}" "${DOCS_HOST:?}"
AWS=${AWS:-aws}
PROFILE=${PROFILE:-lighthouse}
REGION=${REGION:-ap-south-1}

"$AWS" --profile "$PROFILE" --region "$REGION" ecr get-login-password | tr -d '\r' \
  | docker login --username AWS --password-stdin "$REGISTRY"

# One at a time: parallel builds have hung on this machine.
build() {
  local name=$1 context=$2 file=$3; shift 3
  echo "-- $name"
  docker build --progress quiet -f "$file" -t "$REGISTRY/$name:$TAG" "$@" "$context" >/dev/null
  docker push --quiet "$REGISTRY/$name:$TAG"
}
build lighthouse-backend . backend/Dockerfile
build lighthouse-screen frontend frontend/Dockerfile \
  --build-arg "NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL=https://$DOCS_HOST" \
  --build-arg "NEXT_PUBLIC_LIGHTHOUSE_MEMORY_URL=https://$MEMORY_HOST"
build lighthouse-memory-screen memory-site memory-site/Dockerfile \
  --build-arg "NEXT_PUBLIC_MEMORY_DOCS_URL=https://$DOCS_HOST"
build lighthouse-docs docs-site docs-site/Dockerfile \
  --build-arg "NEXT_PUBLIC_MEMORY_CONSOLE_URL=https://$MEMORY_HOST"
