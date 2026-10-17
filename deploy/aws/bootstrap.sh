#!/bin/bash
# First boot of the Lighthouse host (Amazon Linux 2023). provision.sh fills in the three
# values below and passes this file as the instance's user data. It runs once, as root.
set -euxo pipefail
exec > >(tee -a /var/log/lighthouse-bootstrap.log) 2>&1

REGION="__REGION__"
REGISTRY="__REGISTRY__"
FILES="__FILES__"  # docker-compose.yml, docker-compose.aws.yml, and Caddyfile, as base64 tar.gz

dnf install -y docker
systemctl enable --now docker

# Compose v2 is not packaged for Amazon Linux 2023: the release binary, checked against its
# published checksum.
plugins=/usr/local/lib/docker/cli-plugins
mkdir -p "$plugins"
base=https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64
curl -fsSL "$base" -o /tmp/docker-compose
echo "$(curl -fsSL "$base.sha256" | cut -d' ' -f1)  /tmp/docker-compose" | sha256sum -c -
install -m 755 /tmp/docker-compose "$plugins/docker-compose"

# 2 GB of memory: swap takes the peaks, such as FalkorDB rewriting its append-only file.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a

mkdir -p /opt/lighthouse
cd /opt/lighthouse
echo "$FILES" | base64 -d | tar -xz
# The settings, secrets included, live in SSM Parameter Store, never in this script.
aws ssm get-parameter --region "$REGION" --name /lighthouse/env --with-decryption \
  --query Parameter.Value --output text > .env
chmod 600 .env

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
compose="docker compose -f docker-compose.yml -f docker-compose.aws.yml"
$compose pull
$compose up -d --no-build
