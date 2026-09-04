#!/usr/bin/env bash
# The Docker version of the demo: n8n + Postgres(pgvector) in containers from
# docker-compose.yml, the mock APIs and mail sink on the laptop, workflows
# imported and published inside the container. Ends with the webhook URLs and
# the curl commands to paste into a terminal while you watch Executions.
#
# Needs a working `docker` (Docker Desktop, or `brew install colima docker
# docker-compose && colima start`).
#
#   bash demo/docker-demo.sh        # bring it up and fire one event
#   bash demo/docker-demo.sh down   # stop and delete the containers + volumes
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.local ] && set -a && . ./.env.local && set +a   # ANTHROPIC_API_KEY for workflow 09

export N8N_ENCRYPTION_KEY="${N8N_ENCRYPTION_KEY:-demo-only-not-a-secret-docker}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-n8n-demo-pw}"
# compose reads .env from the project dir, so plain `docker compose exec ...` works later from any shell
printf 'N8N_ENCRYPTION_KEY=%s\nPOSTGRES_PASSWORD=%s\n' "$N8N_ENCRYPTION_KEY" "$POSTGRES_PASSWORD" > .env
PORT=5678
say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
dc() { docker compose "$@"; }

if [ "${1:-}" = "down" ]; then
  dc down -v; pkill -f demo/mock-apis.js 2>/dev/null; pkill -f demo/smtp-sink.js 2>/dev/null; exit 0
fi

docker info >/dev/null 2>&1 || { echo "docker is not running. Start Docker Desktop or run: colima start"; exit 1; }
if lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1 && ! docker ps --format '{{.Ports}}' | grep -q ":$PORT->"; then
  echo "port $PORT is taken by something that is not Docker (the npm demo?). Stop it first: pkill -f 'n8n start'"; exit 1
fi

say "1/5  build the import set for Docker (mocks on host.docker.internal, Postgres in the postgres container)"
rm -rf demo/out/build demo/out/mail && mkdir -p demo/out/mail
DEMO_MOCK_HOST=host.docker.internal DEMO_PG_HOST=postgres DEMO_PG_PORT=5432 DEMO_PG_DB=n8n \
DEMO_PG_USER=n8n DEMO_PG_PASSWORD="$POSTGRES_PASSWORD" DEMO_N8N_BASE=http://localhost:5678 node demo/prepare-demo.js

say "2/5  docker compose up (n8n + postgres with pgvector)"
dc up -d
for i in $(seq 1 120); do curl -sf "http://localhost:$PORT/healthz" >/dev/null && break; sleep 1; done
curl -sf "http://localhost:$PORT/healthz" >/dev/null || { echo "n8n did not come up; docker compose logs n8n"; exit 1; }
dc exec -T postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q -f /docker-entrypoint-initdb.d/10-schema.sql >/dev/null 2>&1 || true
dc ps

say "3/5  import credentials + workflows inside the container, publish, restart"
dc exec -T n8n n8n import:credentials --input=/import/credentials.json
dc exec -T n8n n8n import:workflow --separate --input=/import/workflows
for id in $(node -e 'for (const f of require("fs").readdirSync("workflows")) if (f.endsWith(".json")) console.log(require("./workflows/"+f).id)'); do
  dc exec -T n8n n8n publish:workflow --id=$id >/dev/null
done
dc restart n8n >/dev/null
for i in $(seq 1 120); do curl -sf "http://localhost:$PORT/healthz" >/dev/null && break; sleep 1; done
for i in $(seq 1 60); do [ "$(dc logs n8n 2>/dev/null | grep -c 'Activated workflow')" -ge 13 ] && break; sleep 1; done
echo "  workflows activated: $(dc logs n8n 2>/dev/null | grep -c 'Activated workflow')"

say "4/5  owner account, API key for workflow 08, mocks + mail sink on the laptop"
curl -s -X POST "http://localhost:$PORT/rest/owner/setup" -H 'content-type: application/json' \
  -d '{"email":"demo@example.com","firstName":"Demo","lastName":"Owner","password":"Demo-pass-1234"}' >/dev/null || true
curl -s -c demo/out/cookies -X POST "http://localhost:$PORT/rest/login" -H 'content-type: application/json' \
  -d '{"emailOrLdapLoginId":"demo@example.com","password":"Demo-pass-1234"}' >/dev/null
APIKEY=$(curl -s -b demo/out/cookies -X POST "http://localhost:$PORT/rest/api-keys" -H 'content-type: application/json' \
  -d '{"label":"demo-indexer","expiresAt":null,"scopes":["workflow:list","workflow:read"]}' | node -e 'process.stdin.on("data",d=>console.log(JSON.parse(d).data.rawApiKey))')
curl -s -b demo/out/cookies -X PATCH "http://localhost:$PORT/rest/credentials/mpCredN8nApi0006" -H 'content-type: application/json' \
  -d "{\"name\":\"n8n API key (self)\",\"type\":\"httpHeaderAuth\",\"data\":{\"name\":\"X-N8N-API-KEY\",\"value\":\"$APIKEY\"}}" >/dev/null
pkill -f demo/mock-apis.js 2>/dev/null || true; pkill -f demo/smtp-sink.js 2>/dev/null || true
MAIL_DIR="$PWD/demo/out/mail" nohup node demo/smtp-sink.js > demo/out/smtp.log 2>&1 &
nohup node demo/mock-apis.js > demo/out/mocks.log 2>&1 &
sleep 1
echo "  editor:  http://localhost:$PORT   (demo@example.com / Demo-pass-1234)"

say "5/5  index the workflows into Postgres (08), then one lead event, so Executions has something in it"
# `n8n execute` runs beside the server inside the same container; give its task-runner broker its own port.
dc exec -T -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id mpIndexer0000008 2>&1 | grep -E '"indexed"' | sed 's/^ */  /' || true
dc exec -T -e N8N_RUNNERS_BROKER_PORT=5681 n8n n8n execute --id mpDocsIngest0010 2>&1 | grep -E '"chunks"' | sed 's/^ */  /' || true
echo "  page: http://localhost:$PORT/webhook/app"
echo "  $(dc exec -T postgres psql -U n8n -d n8n -tAc 'select count(*) from workflow_index') workflows in Postgres workflow_index"
curl -s -X POST "http://localhost:$PORT/webhook/lead" -H 'content-type: application/json' -H 'x-webhook-secret: demo-secret' \
  -d '{"contact_id":"c_101","first_name":"Dana","last_name":"R","phone":"(555) 555-0101","customData":{"service":"ceramic coating","vehicle":"Tesla Model 3"}}'
echo

CHAT_ID=$(node -e 'const w=require("./workflows/06-chatbot-workflow-helper.json");console.log(w.nodes.find(n=>n.type.endsWith("chatTrigger")).webhookId)')
cat <<EOF

Everything is up. Open http://localhost:$PORT, click Executions in the left bar, and paste these one at a time:

# a new lead from the CRM  ->  workflow 01 (watch it appear in Executions)
curl -X POST http://localhost:$PORT/webhook/lead -H 'content-type: application/json' -H 'x-webhook-secret: demo-secret' \\
  -d '{"contact_id":"c_104","first_name":"Sam","phone":"5555550104","customData":{"service":"tint"}}'

# the same lead again inside 6 hours  ->  skipped by the dedupe guard
curl -X POST http://localhost:$PORT/webhook/lead -H 'content-type: application/json' -H 'x-webhook-secret: demo-secret' \\
  -d '{"contact_id":"c_104","first_name":"Sam","phone":"5555550104"}'

# wrong secret  ->  401
curl -i -X POST http://localhost:$PORT/webhook/lead -H 'content-type: application/json' -H 'x-webhook-secret: nope' -d '{}'

# a missed call from Twilio  ->  workflow 03 texts back (see demo/out/mocks.log) and emails (demo/out/mail)
curl -X POST http://localhost:$PORT/webhook/twilio/call-status \\
  -d 'CallSid=CA9&From=%2B15555550177&To=%2B19082198027&Direction=inbound&DialCallStatus=no-answer'

# Vapi outage  ->  workflow 01 fails on purpose, workflow 05 emails on-call
curl -X POST http://localhost:$PORT/webhook/lead -H 'content-type: application/json' -H 'x-webhook-secret: demo-secret' \\
  -d '{"contact_id":"c_555","first_name":"Outage","phone":"5555550000"}'

# index the workflows into Postgres (workflow 08), then ask the chatbot (06 -> 07 -> Postgres)
docker compose exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id mpIndexer0000008 | grep -E '"indexed"'
open http://localhost:$PORT/webhook/$CHAT_ID/chat

# what Postgres holds
docker compose exec postgres psql -U n8n -d n8n -c 'select id, name, trigger from workflow_index order by id'
docker compose exec postgres psql -U n8n -d n8n -c 'select id, left(question,50) q, similarity from chat_log'

# the containers themselves
docker compose ps
docker compose logs -f n8n

# tear it all down
bash demo/docker-demo.sh down
EOF
