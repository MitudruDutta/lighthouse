#!/usr/bin/env bash
# Deploy the current code to the running host: push images tagged with this commit, record
# the tag in the settings, and have the host pull them and restart what changed. Through
# SSM Run Command: the host has no SSH.
#
#   AWS=/path/to/aws PROFILE=lighthouse REGION=ap-south-1 deploy/aws/update.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
AWS=${AWS:-aws}
PROFILE=${PROFILE:-lighthouse}
REGION=${REGION:-ap-south-1}
here=deploy/aws
aws() { "$AWS" --profile "$PROFILE" --region "$REGION" "$@" | tr -d '\r'; }
file() { if [[ "$AWS" == *.exe ]] && command -v wslpath >/dev/null; then echo "file://$(wslpath -w "$1")"; else echo "file://$1"; fi; }

TAG=${TAG:-$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . ':!deploy' || echo -dirty)}
aws ssm get-parameter --name /lighthouse/env --with-decryption --query Parameter.Value --output text > "$here/.env.aws"
chmod 600 "$here/.env.aws"
setting() { grep -E "^$1=" "$here/.env.aws" | tail -1 | cut -d= -f2-; }
REGISTRY=$(setting REGISTRY) TAG=$TAG APP_HOST=$(setting APP_HOST) MEMORY_HOST=$(setting MEMORY_HOST) \
  DOCS_HOST=$(setting DOCS_HOST) AWS=$AWS PROFILE=$PROFILE REGION=$REGION "$here/push-images.sh"
sed -i "s/^TAG=.*/TAG=$TAG/" "$here/.env.aws"
aws ssm put-parameter --name /lighthouse/env --type SecureString --overwrite --value "$(file "$here/.env.aws")" >/dev/null

INSTANCE=$(aws ec2 describe-instances --filters Name=tag:Name,Values=lighthouse Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
REGISTRY=$(setting REGISTRY)
COMMAND=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --comment "lighthouse $TAG" --query Command.CommandId --output text --parameters "commands=[
    \"cd /opt/lighthouse\",
    \"aws ssm get-parameter --region $REGION --name /lighthouse/env --with-decryption --query Parameter.Value --output text > .env\",
    \"aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REGISTRY\",
    \"docker compose -f docker-compose.yml -f docker-compose.aws.yml pull\",
    \"docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --no-build\",
    \"docker image prune -f\"
  ]")
aws ssm wait command-executed --command-id "$COMMAND" --instance-id "$INSTANCE" || true
aws ssm get-command-invocation --command-id "$COMMAND" --instance-id "$INSTANCE" \
  --query '[Status,StandardOutputContent,StandardErrorContent]' --output text | tail -20
echo "deployed $TAG to $INSTANCE: https://$(setting APP_HOST)"
