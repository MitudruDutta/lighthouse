#!/usr/bin/env bash
# Build the backend image and push it to ECR, tagged apart from the local one so it never
# replaces it. The websites are built by Vercel. Needs REGISTRY and TAG; provision.sh and
# update.sh pass them.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${REGISTRY:?}" "${TAG:?}"
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
