#!/usr/bin/env bash
# Create, or find, everything Lighthouse needs in one AWS Region, and start it on one EC2
# host. Safe to run again: each step uses what is there before it creates anything.
#
#   AWS=/path/to/aws PROFILE=lighthouse REGION=ap-south-1 deploy/aws/provision.sh
#
# Run it from the repository root in a shell with Docker (WSL on Windows). The settings it
# reads from the local .env: the model provider and Google sign-in. It never prints a secret.
set -euo pipefail
cd "$(dirname "$0")/../.."

AWS=${AWS:-aws}
PROFILE=${PROFILE:-lighthouse}
REGION=${REGION:-ap-south-1}
NAME=lighthouse
TYPE=${TYPE:-t3.small}
here=deploy/aws

aws() { "$AWS" --profile "$PROFILE" --region "$REGION" "$@" | tr -d '\r'; }
# A Windows aws.exe run from WSL needs Windows paths for file:// arguments.
file() { if [[ "$AWS" == *.exe ]] && command -v wslpath >/dev/null; then echo "file://$(wslpath -w "$1")"; else echo "file://$1"; fi; }
step() { printf '\n== %s\n' "$*"; }

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
TAG=${TAG:-$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . ':!deploy' || echo -dirty)}
echo "account $ACCOUNT, region $REGION, images $REGISTRY:$TAG"

step "ECR repositories"
for repo in lighthouse-backend lighthouse-screen lighthouse-memory-screen lighthouse-docs; do
  if ! aws ecr describe-repositories --repository-names "$repo" >/dev/null 2>&1; then
    aws ecr create-repository --repository-name "$repo" --image-scanning-configuration scanOnPush=true \
      --encryption-configuration encryptionType=AES256 --query repository.repositoryUri --output text
  fi
  # Keep the last ten images: storage is billed by the gigabyte.
  aws ecr put-lifecycle-policy --repository-name "$repo" --lifecycle-policy-text \
    '{"rules":[{"rulePriority":1,"description":"last ten","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},"action":{"type":"expire"}}]}' >/dev/null
done

step "Elastic IP"
ALLOCATION=$(aws ec2 describe-addresses --filters "Name=tag:Name,Values=$NAME" --query 'Addresses[0].AllocationId' --output text)
if [ "$ALLOCATION" = "None" ]; then
  ALLOCATION=$(aws ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" --query AllocationId --output text)
fi
IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOCATION" --query 'Addresses[0].PublicIp' --output text)
# sslip.io names resolve to the address they spell, so each site has a host name with HTTPS.
DOMAIN=${DOMAIN:-${IP//./-}.sslip.io}
APP_HOST=app.$DOMAIN MEMORY_HOST=memory.$DOMAIN DOCS_HOST=docs.$DOMAIN API_HOST=api.$DOMAIN
echo "address $IP: https://$APP_HOST"

step "Settings in SSM Parameter Store (/lighthouse/env)"
if aws ssm get-parameter --name /lighthouse/env >/dev/null 2>&1 && [ -z "${RESET_ENV:-}" ]; then
  echo "kept the settings that are there (RESET_ENV=1 writes new ones)"
  aws ssm get-parameter --name /lighthouse/env --with-decryption --query Parameter.Value --output text > "$here/.env.aws"
  sed -i "s/^TAG=.*/TAG=$TAG/" "$here/.env.aws"
else
  local_value() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -E "s/^'(.*)'$/\1/" || true; }
  secret() { od -An -tx1 -N24 /dev/urandom | tr -d ' \n'; }
  {
    for key in LIGHTHOUSE_MODEL_PROVIDER LIGHTHOUSE_MODEL_URL LIGHTHOUSE_MODEL LIGHTHOUSE_MODEL_KEY \
               LIGHTHOUSE_MODEL_PROTOCOL LIGHTHOUSE_MODEL_REASONING GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET \
               AISSTREAM_API_KEY; do
      value=$(local_value "$key"); [ -n "$value" ] && echo "$key=$value"
    done
    echo "REGISTRY=$REGISTRY"
    echo "TAG=$TAG"
    echo "APP_HOST=$APP_HOST"
    echo "MEMORY_HOST=$MEMORY_HOST"
    echo "DOCS_HOST=$DOCS_HOST"
    echo "API_HOST=$API_HOST"
    echo "LIGHTHOUSE_APP_URL=https://$APP_HOST"
    echo "MEMORY_SITE_URL=https://$MEMORY_HOST"
    echo "LIGHTHOUSE_DOCS_URL=https://$DOCS_HOST"
    echo "MEMORY_PUBLIC_API=https://$API_HOST"
    echo "FALKORDB_PASSWORD=$(secret)"
    echo "LIGHTHOUSE_PROXY_TOKEN=$(secret)"
    echo "LIGHTHOUSE_OPERATOR_TOKEN=$(secret)"
    # No token that signs in by itself: on the internet, everyone signs in with an account.
    echo "LIGHTHOUSE_TOKEN="
    echo "LIGHTHOUSE_DESK_USERS="
  } > "$here/.env.aws"
fi
chmod 600 "$here/.env.aws"
aws ssm put-parameter --name /lighthouse/env --type SecureString --overwrite \
  --value "$(file "$here/.env.aws")" >/dev/null

step "Images"
REGISTRY=$REGISTRY TAG=$TAG APP_HOST=$APP_HOST MEMORY_HOST=$MEMORY_HOST DOCS_HOST=$DOCS_HOST \
  AWS=$AWS PROFILE=$PROFILE REGION=$REGION "$here/push-images.sh"

step "Instance role"
if ! aws iam get-role --role-name lighthouse-host >/dev/null 2>&1; then
  aws iam create-role --role-name lighthouse-host --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name lighthouse-host --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam attach-role-policy --role-name lighthouse-host --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
fi
# Only its own settings: the one parameter, in this Region.
aws iam put-role-policy --role-name lighthouse-host --policy-name read-settings --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParameter\",\"Resource\":\"arn:aws:ssm:$REGION:$ACCOUNT:parameter/lighthouse/env\"}]}"
if ! aws iam get-instance-profile --instance-profile-name lighthouse-host >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name lighthouse-host >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name lighthouse-host --role-name lighthouse-host
  sleep 10  # a new instance profile takes a moment before EC2 can use it
fi

step "Security group: HTTP and HTTPS only, no SSH"
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
GROUP=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME-web" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$GROUP" = "None" ]; then
  GROUP=$(aws ec2 create-security-group --group-name "$NAME-web" --vpc-id "$VPC" \
    --description "Lighthouse: HTTP and HTTPS from anywhere" --query GroupId --output text)
  for port in 80 443; do
    aws ec2 authorize-security-group-ingress --group-id "$GROUP" --ip-permissions \
      "IpProtocol=tcp,FromPort=$port,ToPort=$port,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]" >/dev/null
  done
fi

step "Instance"
INSTANCE=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$INSTANCE" = "None" ]; then
  AMI=$(aws ec2 describe-images --owners amazon --filters "Name=name,Values=al2023-ami-2023.*-kernel-*-x86_64" \
    "Name=state,Values=available" --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
  files=$(tar -cz docker-compose.yml -C "$here" docker-compose.aws.yml Caddyfile | base64 -w0)
  sed -e "s|__REGION__|$REGION|" -e "s|__REGISTRY__|$REGISTRY|" -e "s|__FILES__|$files|" "$here/bootstrap.sh" > "$here/.user-data"
  INSTANCE=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" \
    --iam-instance-profile Name=lighthouse-host --security-group-ids "$GROUP" \
    --credit-specification CpuCredits=standard \
    --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
    --user-data "$(file "$here/.user-data")" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" "ResourceType=volume,Tags=[{Key=Name,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text)
  rm -f "$here/.user-data"
  echo "launched $INSTANCE ($TYPE, $AMI)"
  aws ec2 wait instance-running --instance-ids "$INSTANCE"
else
  echo "using $INSTANCE: for new images, run deploy/aws/update.sh"
fi
aws ec2 associate-address --allocation-id "$ALLOCATION" --instance-id "$INSTANCE" >/dev/null

step "Ready"
echo "The first start takes a few minutes. Then:"
echo "  https://$APP_HOST  https://$MEMORY_HOST  https://$DOCS_HOST  https://$API_HOST/docs"
echo "Google sign-in: add https://$APP_HOST/api/auth/google/callback and https://$MEMORY_HOST/api/auth/google/callback"
echo "  to the OAuth client's authorized redirect URIs."
