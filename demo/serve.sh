#!/usr/bin/env bash
# Bring the demo back up without re-running it: Postgres, mocks, mail sink, n8n.
# Then open http://localhost:5678 (demo@example.com / Demo-pass-1234).
set -euo pipefail
cd "$(dirname "$0")/.."
N8N="${N8N:-./node_modules/.bin/n8n}"
PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@17/bin}"
export N8N_USER_FOLDER="$PWD/demo/out/n8n" N8N_PORT=5678 N8N_RUNNERS_ENABLED=true N8N_DIAGNOSTICS_ENABLED=false
export N8N_LOG_LEVEL=info N8N_SECURE_COOKIE=false N8N_ENCRYPTION_KEY=demo-only-not-a-secret
export N8N_PERSONALIZATION_ENABLED=false N8N_VERSION_NOTIFICATIONS_ENABLED=false MAIL_DIR="$PWD/demo/out/mail"
[ -d demo/out/pg ] || { echo "run bash demo/demo.sh first"; exit 1; }
"$PGBIN/pg_isready" -h localhost -p 5433 -q || "$PGBIN/pg_ctl" -D "$PWD/demo/out/pg" -o "-p 5433 -k /tmp" -l "$PWD/demo/out/pg/pg.log" start >/dev/null
node demo/mock-apis.js & node demo/smtp-sink.js &
trap 'kill $(jobs -p) 2>/dev/null; "$PGBIN/pg_ctl" -D "$PWD/demo/out/pg" stop -m fast >/dev/null 2>&1' EXIT
CHAT_ID=$(node -e 'const w=require("./workflows/06-chatbot-workflow-helper.json");console.log(w.nodes.find(n=>n.type.endsWith("chatTrigger")).webhookId)')
echo "editor: http://localhost:5678   chat: http://localhost:5678/webhook/$CHAT_ID/chat   (Ctrl-C stops everything)"
exec $N8N start
