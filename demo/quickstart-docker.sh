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

if [ "${1:-}" = "down" ]; then docker rm -f n8n n8n-postgres; docker network rm n8n-net 2>/dev/null; exit 0; fi
docker info >/dev/null 2>&1 || { echo "docker is not running (colima start / Docker Desktop)"; exit 1; }

say "1/4  the containers: n8n (this is the whole install) and a Postgres for search"
docker compose stop >/dev/null 2>&1 || true            # the compose demo uses the same port
docker rm -f n8n n8n-postgres >/dev/null 2>&1 || true
docker network create n8n-net >/dev/null 2>&1 || true   # so the two containers can see each other by name
PGPW=n8n-demo-pw
docker run -d --name n8n-postgres --network n8n-net -v n8n_pgdata:/var/lib/postgresql/data \
  -e POSTGRES_USER=n8n -e POSTGRES_PASSWORD=$PGPW -e POSTGRES_DB=n8n \
  -v "$PWD/demo/schema.sql:/docker-entrypoint-initdb.d/10-schema.sql:ro" \
  pgvector/pgvector:pg17 >/dev/null
echo "docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n n8nio/n8n"
docker run -d --name n8n --network n8n-net -p $PORT:5678 -v n8n_data:/home/node/.n8n \
  -v "$PWD/demo/pdfs:/data/pdfs:ro" -e N8N_RESTRICT_FILE_ACCESS_TO=/data/pdfs \
  --add-host host.docker.internal:host-gateway \
  -e N8N_SECURE_COOKIE=false -e N8N_RUNNERS_ENABLED=true -e N8N_DIAGNOSTICS_ENABLED=false \
  -e N8N_ENCRYPTION_KEY=demo-only-not-a-secret-quickstart \
  -e N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true \
  n8nio/n8n >/dev/null
# The last flag: n8n wraps every webhook response in a "sandbox" Content-Security-Policy, which blocks
# the browser's PDF viewer and scripts on served pages. Workflows 12 and 13 set their own CSP instead.
for i in $(seq 1 60); do docker exec n8n-postgres pg_isready -U n8n -q 2>/dev/null && break; sleep 1; done
docker exec -i n8n-postgres psql -U n8n -d n8n -q < demo/schema.sql   # idempotent; the volume may be from an older run
for i in $(seq 1 120); do curl -sf "http://localhost:$PORT/healthz" >/dev/null && break; sleep 1; done
docker ps --filter name=n8n --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

say "2/4  copy the workflow files in, import, publish, restart"
DEMO_MOCK_HOST=host.docker.internal DEMO_PG_HOST=n8n-postgres DEMO_PG_PORT=5432 DEMO_PG_DB=n8n DEMO_PG_USER=n8n DEMO_PG_PASSWORD=$PGPW node demo/prepare-demo.js >/dev/null
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


say "the web page: index the PDFs (workflow 10) and the workflow list (08), then open /webhook/app"
# Workflow 08 reads n8n's own REST API, so it needs an API key: log in, mint one, store it in the credential.
curl -s -c demo/out/cookies -X POST "http://localhost:$PORT/rest/login" -H 'content-type: application/json' \
  -d '{"emailOrLdapLoginId":"demo@example.com","password":"Demo-pass-1234"}' >/dev/null
APIKEY=$(curl -s -b demo/out/cookies -X POST "http://localhost:$PORT/rest/api-keys" -H 'content-type: application/json' \
  -d "{\"label\":\"quickstart-$(date +%s)\",\"expiresAt\":null,\"scopes\":[\"workflow:list\",\"workflow:read\"]}" \
  | node -e 'let b="";process.stdin.on("data",d=>b+=d).on("end",()=>{try{console.log(JSON.parse(b).data.rawApiKey||"")}catch{console.log("")}})')
if [ -n "$APIKEY" ]; then
  curl -s -b demo/out/cookies -X PATCH "http://localhost:$PORT/rest/credentials/mpCredN8nApi0006" -H 'content-type: application/json' \
    -d "{\"name\":\"n8n API key (self)\",\"type\":\"httpHeaderAuth\",\"data\":{\"name\":\"X-N8N-API-KEY\",\"value\":\"$APIKEY\"}}" >/dev/null
else
  echo "  (could not mint an n8n API key; workflow 08 will reuse the previous one if any)"
fi
docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id mpDocsIngest0010 2>&1 | grep -E '"chunks"' | sed 's/^ */  /' || true
docker exec -e N8N_RUNNERS_BROKER_PORT=5681 n8n n8n execute --id mpIndexer0000008 2>&1 | grep -E '"indexed"' | sed 's/^ */  /' || true
echo "  $(docker exec n8n-postgres psql -U n8n -d n8n -tAc "select count(distinct name) || ' PDFs, ' || count(*) || ' chunks in docs' from docs")"
echo
echo "Open http://localhost:$PORT/webhook/app  (the page; search, triage, ask, open a PDF)"
echo "Open http://localhost:$PORT             (the editor: demo@example.com / Demo-pass-1234; click Executions)"
open "http://localhost:$PORT/webhook/app" 2>/dev/null || true
