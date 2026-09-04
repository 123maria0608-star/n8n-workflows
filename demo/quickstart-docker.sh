#!/usr/bin/env bash
# The plain "docker run" way: one n8n container, SQLite inside it, no compose.
# This is the n8n quick start most tutorials show, and it is the way the
# Support Ticket Triage demo (workflow 09) was first shown to me.
#
#   bash demo/quickstart-docker.sh          # start, import, publish, fire one ticket
#   bash demo/quickstart-docker.sh down     # remove the container (the n8n_data volume stays)
#
# Needs: docker running, and ANTHROPIC_API_KEY in the environment or in .env.local
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.local ] && set -a && . ./.env.local && set +a
: "${ANTHROPIC_API_KEY:?put ANTHROPIC_API_KEY=sk-ant-... in .env.local}"
PORT=5678
say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

if [ "${1:-}" = "down" ]; then docker rm -f n8n; exit 0; fi
docker info >/dev/null 2>&1 || { echo "docker is not running (colima start / Docker Desktop)"; exit 1; }

say "1/4  the container (this is the whole install)"
docker compose stop >/dev/null 2>&1 || true            # the compose demo uses the same port
docker rm -f n8n >/dev/null 2>&1 || true
echo "docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n"
docker run -d --name n8n -p $PORT:5678 -v n8n_data:/home/node/.n8n \
  --add-host host.docker.internal:host-gateway \
  -e N8N_SECURE_COOKIE=false -e N8N_RUNNERS_ENABLED=true -e N8N_DIAGNOSTICS_ENABLED=false \
  -e N8N_ENCRYPTION_KEY=demo-only-not-a-secret-quickstart \
  n8nio/n8n >/dev/null
for i in $(seq 1 120); do curl -sf "http://localhost:$PORT/healthz" >/dev/null && break; sleep 1; done
docker ps --filter name=n8n --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

say "2/4  copy the workflow files in, import, publish, restart"
DEMO_MOCK_HOST=host.docker.internal node demo/prepare-demo.js >/dev/null
docker exec -u root n8n rm -rf /tmp/import; docker cp demo/out/build n8n:/tmp/import; docker exec -u root n8n chown -R node:node /tmp/import
docker exec n8n n8n import:credentials --input=/tmp/import/credentials.json
docker exec n8n n8n import:workflow --separate --input=/tmp/import/workflows
for f in workflows/*.json; do
  id=$(node -e 'console.log(require("./'"$f"'").id)')
  docker exec n8n n8n publish:workflow --id=$id >/dev/null
done
docker restart n8n >/dev/null
# healthz answers before webhooks are registered. The webhook path itself tells us when n8n is ready:
# "Cannot GET" = still booting, the JSON 404 about GET vs POST = registered.
# "not registered for GET requests" is the message a live POST-only webhook gives to a GET.
# "is not registered." (no GET/POST hint) means n8n is still booting. Wait for the first one.
for i in $(seq 1 120); do curl -s "http://localhost:$PORT/webhook/ticket-triage" | grep -q 'not registered for GET' && break; sleep 1; done
curl -s "http://localhost:$PORT/webhook/ticket-triage" | grep -q 'not registered for GET' && echo "  webhooks live" || { echo "  webhooks did not come up; see: docker logs n8n"; exit 1; }
curl -s -X POST "http://localhost:$PORT/rest/owner/setup" -H 'content-type: application/json' \
  -d '{"email":"demo@example.com","firstName":"Demo","lastName":"Owner","password":"Demo-pass-1234"}' >/dev/null || true

say "3/4  a browser sends GET, the node wants POST: this is the 404 you will see if you open the URL"
curl -s "http://localhost:$PORT/webhook/ticket-triage"; echo

say "4/4  the real thing: POST a ticket from the terminal"
cat <<'CMD'
curl -X POST http://localhost:5678/webhook/ticket-triage \
  -H "Content-Type: application/json" \
  -d '{"ticket": "I was charged twice this month and your app keeps logging me out. Fix this or I am cancelling."}'
CMD
curl -s -X POST "http://localhost:$PORT/webhook/ticket-triage" \
  -H "Content-Type: application/json" \
  -d '{"ticket": "I was charged twice this month and your app keeps logging me out. Fix this or I am cancelling."}' \
  | node -e 'process.stdin.on("data",d=>{try{console.log(JSON.stringify(JSON.parse(d),null,2))}catch{console.log(d.toString())}})'

echo
echo "Now open http://localhost:$PORT (demo@example.com / Demo-pass-1234), open workflow 09, click Executions."
echo "Every curl you run shows up there with the webhook input, the raw model reply, and the parsed triage."
