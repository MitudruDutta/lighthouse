#!/usr/bin/env bash
# Local installation. Requires Docker with Compose; no host language runtimes needed.
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077

usage() {
  cat <<'HELP'
Lighthouse · local setup

Usage: ./setup.sh [option]

  --yes       Start without the optional API-key prompt
  --no-build  Start existing images without rebuilding
  --status    Show running services
  --stop      Stop services and keep your data
  --help      Show this help

Run without options to build and start Lighthouse.
Settings are saved in .env. App: localhost:3000 · Memory: localhost:3003 · Docs: localhost:3002
HELP
}
interactive=true
build=true
action=start
for arg in "$@"; do
  case "$arg" in
    --yes) interactive=false ;;
    --no-build) build=false ;;
    --status) action=status ;;
    --stop) action=stop ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown option: %s\nRun ./setup.sh --help for usage.\n' "$arg" >&2; exit 2 ;;
  esac
done
bold='' reset=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  bold=$'\033[1m'
  reset=$'\033[0m'
fi
step() { printf '\n%s%s%s\n' "$bold" "$*" "$reset"; }
note() { printf '  %s\n' "$*"; }
fail() { printf '\nSetup could not finish. %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail 'Install Docker Desktop or Docker Engine with Compose:
  https://docs.docker.com/get-docker/
  Then run ./setup.sh again.'
docker info >/dev/null 2>&1 || fail 'Docker is not available. Start Docker Desktop or the Docker service.
  On Linux, also check that your account can run docker info. Then run ./setup.sh again.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose is missing. Install the Compose plugin or update Docker Desktop.'
case "$action" in
  status) docker compose ps; exit 0 ;;
  stop) docker compose down; printf '\nLighthouse stopped. Your data is saved. Restart with ./setup.sh.\n'; exit 0 ;;
esac

printf '\n%sLighthouse%s\nConnected data. Shared memory.\n' "$bold" "$reset"
step '1 / 4 · Check requirements'
note 'Docker and Compose are ready.'

# Read only the named setting. Never execute configuration as shell code.
setting() {
  awk -v name="$1" 'index($0, name "=") == 1 {
    value = substr($0, length(name) + 2); sub(/\r$/, "", value)
    if (value ~ /^\047.*\047$/ || value ~ /^".*"$/) value = substr(value, 2, length(value)-2)
    result = value
  } END { printf "%s", result }' .env
}
set_setting() {
  local value=${2//\'/\\\'}
  awk -v name="$1" 'index($0, name "=") != 1' .env > .env.setup-tmp
  printf "%s='%s'\n" "$1" "$value" >> .env.setup-tmp
  mv .env.setup-tmp .env
}
new_token() { od -An -tx1 -N24 /dev/urandom | tr -d ' \n'; }

step '2 / 4 · Configure your workspace'
if [ ! -f .env ]; then
  cp .env.example .env
  note 'Created .env for this computer.'
else
  note 'Keeping your existing settings and data.'
fi
chmod 600 .env
if [ -z "$(setting LIGHTHOUSE_TOKEN)" ]; then
  token=$(new_token)
  set_setting LIGHTHOUSE_TOKEN "$token"
  users=$(setting LIGHTHOUSE_DESK_USERS)
  set_setting LIGHTHOUSE_DESK_USERS "$token=local/you${users:+,$users}"
fi
if [ -z "$(setting LIGHTHOUSE_DESK_USERS)" ]; then
  set_setting LIGHTHOUSE_DESK_USERS "$(setting LIGHTHOUSE_TOKEN)=local/you"
fi
if [ -z "$(setting LIGHTHOUSE_OPERATOR_TOKEN)" ]; then
  set_setting LIGHTHOUSE_OPERATOR_TOKEN "$(new_token)"
fi
note 'Local sign-in and private operator credentials are configured.'
model_key_name=LIGHTHOUSE_MODEL_KEY
case "$(setting LIGHTHOUSE_MODEL_PROVIDER)" in
  openai) model_key_name=OPENAI_API_KEY ;;
  anthropic) model_key_name=ANTHROPIC_API_KEY ;;
  gemini) model_key_name=GEMINI_API_KEY ;;
  groq) model_key_name=GROQ_API_KEY ;;
  deepseek) model_key_name=DEEPSEEK_API_KEY ;;
  mistral) model_key_name=MISTRAL_API_KEY ;;
  openrouter) model_key_name=OPENROUTER_API_KEY ;;
  commandcode) model_key_name=COMMANDCODE_API_KEY ;;
  ollama) model_key_name=OLLAMA_API_KEY ;;
esac
if [ -z "$(setting "$model_key_name")" ]; then
  if $interactive && [ -t 0 ]; then
    printf '\n  Optional: connect the Desk assistant. Monitoring works without a model.\n'
    printf '  Enter the API key for the provider configured in .env.\n'
    printf '  Press Enter to skip and configure it later.\n'
    read -r -s -p '  API key (hidden): ' key || key=''
    printf '\n'
    if [ -n "$key" ]; then
      set_setting "$model_key_name" "$key"
      unset key
    fi
  fi
  if [ -z "$(setting "$model_key_name")" ]; then
    note 'Desk assistant skipped. Add a model key to .env when you are ready.'
  fi
fi

mkdir -p .lighthouse
chmod 700 .lighthouse
log_file="$PWD/.lighthouse/setup.log"
step '3 / 4 · Start services'
note 'First setup may take several minutes to download and build images.'
note "Build details: $log_file"
compose_args=(up -d)
if $build; then compose_args+=(--build); fi
docker compose "${compose_args[@]}" > "$log_file" 2>&1 &
compose_pid=$!
trap 'kill "$compose_pid" 2>/dev/null || true; printf "\nSetup interrupted. Settings and data are saved. Run ./setup.sh again.\n"; exit 130' INT TERM
if [ -t 1 ]; then
  while kill -0 "$compose_pid" 2>/dev/null; do
    printf '.'
    sleep 2
  done
  printf '\n'
fi
if ! wait "$compose_pid"; then
  if grep -Eqi 'port is already allocated|address already in use' "$log_file"; then
    fail "A required port is in use. Change the matching port in .env, then retry.
  If changing SCREEN_PORT or DOCS_PORT, also update LIGHTHOUSE_APP_URL or LIGHTHOUSE_DOCS_URL.
  Details: $log_file"
  fi
  fail "Docker could not start the services. Check Docker's disk space and network access, then retry.
  Details: $log_file
  Service status: ./setup.sh --status"
fi
trap - INT TERM
note 'All eight services started.'

step '4 / 4 · Check readiness'
note 'Waiting for the graph API, workspaces, Memory API, and documentation.'
# Node runs inside the screen image: users only need Docker on their computer.
ready=false
for ((attempt=0; attempt<36; attempt++)); do
  if docker compose exec -T screen node -e '
    Promise.all(["http://api:8100/readyz", "http://127.0.0.1:3000/dashboard", "http://docs:3002/", "http://memory-api:8200/readyz", "http://memory-screen:3003/"].map(async url => {
      const response = await fetch(url, { signal: AbortSignal.timeout(3000), redirect: "error" });
      if (!response.ok) throw new Error("Not ready");
      await response.arrayBuffer();
    })).then(() => process.exit(0)).catch(() => process.exit(1));
  ' >> "$log_file" 2>&1; then
    ready=true
    break
  fi
  sleep 2
done
$ready || fail "One or more services are still starting or unavailable.
  Check ./setup.sh --status and docker compose logs --tail 50.
  Setup log: $log_file
  Your settings and data are saved; run ./setup.sh again to retry."
screen_address=$(docker compose port screen 3000)
docs_address=$(docker compose port docs 3002)
screen_port=${screen_address##*:}
docs_port=${docs_address##*:}
memory_address=$(docker compose port memory-screen 3003)
memory_port=${memory_address##*:}
printf '\n%sLighthouse is ready.%s\n\n' "$bold" "$reset"
printf '  Open app     http://localhost:%s\n' "$screen_port"
printf '  Memory       http://localhost:%s\n' "$memory_port"
printf '  Read docs    http://localhost:%s\n\n' "$docs_port"
note 'Public data imports continue in the background. Check Source health in the workspace.'
note 'Stop: ./setup.sh --stop    Status: ./setup.sh --status'
printf '\n'
