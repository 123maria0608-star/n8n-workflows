#!/usr/bin/env bash
# End-to-end demo on a laptop with no outside accounts.
#
#   1. Points every workflow's Config node at local mock APIs (Vapi, GoHighLevel,
#      Twilio) and a local SMTP sink.
#   2. Imports credentials + workflows into a throwaway n8n instance, activates
#      them, starts n8n.
#   3. Fires the same HTTP events the real services send, and shows what came
#      out the other end: mock API calls, emails, webhook responses.
#
# Requirements: Node 24+, `npm install` in this folder (pulls n8n and smtp-server).
# Usage:  bash demo/demo.sh          (from the repo root)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env.local ] && set -a && . ./.env.local && set +a   # ANTHROPIC_API_KEY for workflow 09

N8N="${N8N:-./node_modules/.bin/n8n}"
PORT=5678
# Postgres 17 + pgvector (brew install postgresql@17 pgvector). A throwaway cluster under demo/out.
PGBIN="${PGBIN:-/opt/homebrew/opt/postgresql@17/bin}"
[ -x "$PGBIN/pg_ctl" ] || PGBIN="$(dirname "$(command -v pg_ctl || echo /usr/local/bin/pg_ctl)")"
PGPORT=5433 PGDATA_DIR="$PWD/demo/out/pg"
PSQL="$PGBIN/psql -h localhost -p $PGPORT -U n8n -d n8ndemo -v ON_ERROR_STOP=1"
export N8N_USER_FOLDER="$PWD/demo/out/n8n"
export N8N_PORT=$PORT N8N_RUNNERS_ENABLED=true N8N_DIAGNOSTICS_ENABLED=false
export N8N_LOG_LEVEL=info N8N_SECURE_COOKIE=false N8N_ENCRYPTION_KEY=demo-only-not-a-secret
export N8N_PERSONALIZATION_ENABLED=false N8N_VERSION_NOTIFICATIONS_ENABLED=false
export MAIL_DIR="$PWD/demo/out/mail"
# `n8n execute` (CLI) runs beside the server, so its task-runner broker needs its own port.
EXEC="env N8N_RUNNERS_BROKER_PORT=5680 $N8N execute"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
post() { # post <path> <content-type> <data> [extra curl args]
  curl -s -o /tmp/n8n-demo-resp -w '%{http_code}' -X POST "http://localhost:$PORT/webhook/$1" -H "content-type: $2" --data "$3" "${@:4}"
}
show() { printf '  -> HTTP %s  %s\n' "$1" "$(head -c 200 /tmp/n8n-demo-resp)"; }

cleanup() { say "stopping"; kill "${PIDS[@]}" 2>/dev/null || true; wait 2>/dev/null || true; "$PGBIN/pg_ctl" -D "$PGDATA_DIR" stop -m fast >/dev/null 2>&1 || true; }
PIDS=()
trap cleanup EXIT

say "1/6  fresh instance"
rm -rf demo/out && mkdir -p demo/out/mail
node demo/prepare-demo.js

say "2/6  throwaway Postgres 17 with pgvector on port $PGPORT"
"$PGBIN/initdb" -D "$PGDATA_DIR" -U n8n --auth=trust >/dev/null
"$PGBIN/pg_ctl" -D "$PGDATA_DIR" -o "-p $PGPORT -k /tmp" -l "$PGDATA_DIR/pg.log" start >/dev/null
for i in $(seq 1 20); do "$PGBIN/pg_isready" -h localhost -p $PGPORT -q && break; sleep 0.5; done
"$PGBIN/createdb" -h localhost -p $PGPORT -U n8n n8ndemo
$PSQL -q -f demo/schema.sql
echo "  tables: $($PSQL -tAc "select string_agg(tablename, ', ') from pg_tables where schemaname='public'")  (pgvector $($PSQL -tAc "select extversion from pg_extension where extname='vector'"))"

say "3/6  import credentials + workflows, activate"
$N8N import:credentials --input=demo/out/build/credentials.json
$N8N import:workflow --separate --input=demo/out/build/workflows
for id in mpSpeedToLead001 mpEndOfCallWb002 mpMissedCall0003 mpFollowupCron04 mpErrorAlert0005 mpChatBot0000006 mpLookupWf000007 mpIndexer0000008 mpTicketTriage09; do
  $N8N publish:workflow --id=$id
done

say "4/6  start mocks, mail sink, n8n"
node demo/mock-apis.js & PIDS+=($!)
node demo/smtp-sink.js & PIDS+=($!)
$N8N start > demo/out/n8n.log 2>&1 & PIDS+=($!)
for i in $(seq 1 90); do curl -sf "http://localhost:$PORT/healthz" >/dev/null && break; sleep 1; done
curl -sf "http://localhost:$PORT/healthz" >/dev/null || { echo "n8n did not start; see demo/out/n8n.log"; exit 1; }
# healthz answers before webhooks are registered; wait for all five activations.
for i in $(seq 1 60); do [ "$(grep -c 'Activated workflow' demo/out/n8n.log)" -ge 9 ] && break; sleep 1; done
grep -c 'Activated workflow' demo/out/n8n.log | sed 's/^/  workflows activated: /' 
# First-run owner account so the editor at http://localhost:5678 opens without the setup screen.
curl -s -X POST "http://localhost:$PORT/rest/owner/setup" -H 'content-type: application/json' \
  -d '{"email":"demo@example.com","firstName":"Demo","lastName":"Owner","password":"Demo-pass-1234"}' >/dev/null || true
echo "  n8n is up at http://localhost:$PORT  (login demo@example.com / Demo-pass-1234)"
# Workflow 08 calls n8n's own public API, so it needs an API key: log in, mint one, store it in the credential.
curl -s -c demo/out/cookies -X POST "http://localhost:$PORT/rest/login" -H 'content-type: application/json' \
  -d '{"emailOrLdapLoginId":"demo@example.com","password":"Demo-pass-1234"}' >/dev/null
APIKEY=$(curl -s -b demo/out/cookies -X POST "http://localhost:$PORT/rest/api-keys" -H 'content-type: application/json' \
  -d '{"label":"demo-indexer","expiresAt":null,"scopes":["workflow:list","workflow:read"]}' | node -e 'process.stdin.on("data",d=>console.log(JSON.parse(d).data.rawApiKey))')
curl -s -b demo/out/cookies -X PATCH "http://localhost:$PORT/rest/credentials/mpCredN8nApi0006" -H 'content-type: application/json' \
  -d "{\"name\":\"n8n API key (self)\",\"type\":\"httpHeaderAuth\",\"data\":{\"name\":\"X-N8N-API-KEY\",\"value\":\"$APIKEY\"}}" >/dev/null
echo "  n8n API key minted and stored in credential 'n8n API key (self)'"

say "5/6  fire the events the real services would send"
S='x-webhook-secret: demo-secret'

echo "a) New lead from the CRM (GoHighLevel payload shape)"
show "$(post lead application/json '{"contact_id":"c_101","first_name":"Dana","last_name":"R","phone":"(555) 555-0101","customData":{"service":"ceramic coating","vehicle":"Tesla Model 3"}}' -H "$S")"

echo "b) Same lead posted again within 6h  -> dedupe guard skips it"
show "$(post lead application/json '{"contact_id":"c_101","first_name":"Dana","phone":"5555550101"}' -H "$S")"

echo "c) Web-form payload shape, bad phone number -> invalid_number, still HTTP 200"
show "$(post lead application/json '{"name":"Web Form Person","phone":"12345","service":"tint"}' -H "$S")"

echo "d) Wrong shared secret -> 401, nothing runs"
show "$(post lead application/json '{"contact_id":"c_999","phone":"5555550199"}' -H 'x-webhook-secret: wrong')"

echo "e) Vapi returns 500 for this number (mock outage) -> 3 tries, execution fails, error workflow emails on-call"
show "$(post lead application/json '{"contact_id":"c_555","first_name":"Outage","phone":"5555550000"}' -H "$S")"
pause() { sleep "${1:-3}"; }   # real events are seconds apart; static-data guards are read at execution start

echo "f) Vapi end-of-call report: booked -> CRM tags + note + owner email"
show "$(post vapi/end-of-call application/json '{"message":{"type":"end-of-call-report","endedReason":"customer-ended-call","summary":"Dana booked a ceramic coating for Tuesday 2pm.","call":{"metadata":{"contactId":"c_101"},"customer":{"number":"+15555550101"}},"analysis":{"structuredData":{"reached":"customer","booked":true,"appointment":"Tue 2pm","service":"ceramic coating","vehicle":"Tesla Model 3"}}}}' -H 'x-vapi-secret: demo-secret')"

pause
echo "g) Twilio status callback: inbound call, no-answer -> rescue SMS + owner email + log"
show "$(post twilio/call-status application/x-www-form-urlencoded 'CallSid=CA001&From=%2B15555550199&To=%2B19082198027&Direction=inbound&DialCallStatus=no-answer')"

pause
echo "h) Same caller misses again the same day -> no second text, owner still emailed"
show "$(post twilio/call-status application/x-www-form-urlencoded 'CallSid=CA002&From=%2B15555550199&To=%2B19082198027&Direction=inbound&DialCallStatus=busy')"

echo "i) Someone texts STOP, then misses a call -> opted out, no text"
pause
show "$(post twilio/inbound-sms application/x-www-form-urlencoded 'From=%2B15555550198&To=%2B19082198027&Body=STOP')"
pause
show "$(post twilio/call-status application/x-www-form-urlencoded 'CallSid=CA003&From=%2B15555550198&To=%2B19082198027&Direction=inbound&DialCallStatus=no-answer')"

pause
echo "j) Answered call -> not a missed call, nothing happens"
show "$(post twilio/call-status application/x-www-form-urlencoded 'CallSid=CA004&From=%2B15555550197&To=%2B19082198027&Direction=inbound&DialCallStatus=completed')"

sleep 6   # let the retries in (e) and the async writes finish

say "6/6  what came out the other end"
echo "Mock API calls received (method path -> who called it):"
curl -s http://localhost:4010/_requests | node -e '
  const r = JSON.parse(require("fs").readFileSync(0, "utf8"));
  for (const x of r) console.log(`  ${x.method.padEnd(4)} ${x.path.padEnd(48)} auth=${x.auth}`);
  console.log(`  ${r.length} requests total`);'
echo
echo "Emails delivered to the SMTP sink:"
python3 - <<'PY'
import email, glob, os
from email.header import decode_header, make_header
for f in sorted(glob.glob("demo/out/mail/*.eml")):
    m = email.message_from_file(open(f))
    print(f"  {os.path.basename(f)}  to={m['To']}  subject={make_header(decode_header(m['Subject']))}")
PY

echo
echo "Now the scheduled follow-up. It normally fires weekdays at 10:00; run it once by hand."
echo "Dana booked in step (f), so the CRM tag ai-booked now closes her out; Sam is the one still to chase."
echo "  (n8n execute runs the workflow from its trigger, exactly like the schedule would)"
$EXEC --id mpFollowupCron04 2>&1 | grep -E '"(status|finished|startedAt|stoppedAt)"' | sed 's/^ */  /' || true
echo
echo "Follow-up pass email:"
for f in demo/out/mail/*.eml; do
  if grep -qi '^Subject: Follow-up pass' "$f"; then awk 'f{print} /^\r?$/{f=1}' "$f" | tr -d '\r' | head -20; fi
done

say "chatbot: index the workflows into Postgres, then ask it questions"
echo "Workflow 08 (indexer): n8n API -> describe -> vector -> upsert into workflow_index"
$EXEC --id mpIndexer0000008 2>&1 | grep -E '"indexed"|"status": "(success|error)"' | sed 's/^ */  /' || true
echo "  rows in workflow_index: $($PSQL -tAc 'select count(*) from workflow_index')"
echo
echo "Talk to workflow 06 the way the chat page does (POST to the Chat Trigger's URL):"
CHAT_ID=$(node -e 'const w=require("./workflows/06-chatbot-workflow-helper.json");console.log(w.nodes.find(n=>n.type.endsWith("chatTrigger")).webhookId)')
ask() {
  printf '\n  Q: %s\n' "$1"
  curl -s -X POST "http://localhost:$PORT/webhook/$CHAT_ID/chat" -H 'content-type: application/json' \
    -d "{\"sessionId\":\"demo-session\",\"action\":\"sendMessage\",\"chatInput\":$(node -e 'console.log(JSON.stringify(process.argv[1]))' "$1")}" \
    | node -e 'process.stdin.on("data",d=>{try{console.log("  A: "+JSON.parse(d).output.replace(/\n/g,"\n     "))}catch{console.log("  A: "+d)}})'
}
ask "what happens when a customer calls and nobody answers?"
ask "how do the daily follow-up calls decide who to call again?"
ask "where do alerts go when a workflow fails?"
echo
echo "What Postgres now holds (chat_log joined to workflow_index):"
$PSQL -c "select c.id, left(c.question,45) as question, w.name as matched, round(c.similarity::numeric,3) as sim, c.asked_at::time(0) from chat_log c left join workflow_index w on w.id = c.matched_workflow_id order by c.id"
echo "Chat page for a human: http://localhost:$PORT/webhook/$CHAT_ID/chat  (while n8n is running)"

echo
echo "Done. Executions, with every node's input and output, are in demo/out/n8n/.n8n/database.sqlite"
echo "Browse them or open the chat page:  bash demo/serve.sh"
