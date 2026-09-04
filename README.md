# n8n workflows

Thirteen n8n workflows that run end to end on a laptop with one command, plus a web
page served by n8n itself that drives them: deterministic full-text search over PDFs
with the PDF shown in the page, a support-ticket triage form, and a chatbot. Twelve
need no outside accounts; the triage one calls a real LLM. Five are automations I run in production for small-business
clients (AI phone receptionists, speed-to-lead calling, missed-call rescue, CRM
write-backs), rebuilt as n8n. Three are a chatbot on top of them: ask which
workflow does what, get the answer from Postgres with pgvector, log the
conversation.

```bash
brew install postgresql@17 pgvector     # once
npm install                              # once, pulls n8n
bash demo/demo.sh                        # ~1 minute, prints everything it does
bash demo/serve.sh                       # then open http://localhost:5678
```

Or the two-container quick start (`docker run` n8n with SQLite, plus a Postgres for
search), which imports everything, fires a support ticket at workflow 09, indexes the
PDFs, and opens the page at `http://localhost:5678/webhook/app`:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env.local
bash demo/quickstart-docker.sh
```

![Ticket triage execution](docs/img/13-ticket-triage-execution.png)

Or the same thing with Postgres in Docker Compose, which is how a company would run it:

```bash
brew install colima docker docker-compose && colima start   # Docker without Docker Desktop
bash demo/docker-demo.sh                 # n8n + Postgres in containers, workflows imported, events fired
```

![Executions inside Docker](docs/img/12-docker-executions.png)

[docs/docker-demo-transcript.txt](docs/docker-demo-transcript.txt) is that run
on my machine: two containers, 8 workflows published from the n8n CLI inside the
container, a webhook answered through the container, the indexer and the chatbot
writing to the Postgres container.

[docs/run-it-yourself.md](docs/run-it-yourself.md) has the step-by-step.
[docs/demo-transcript.txt](docs/demo-transcript.txt) is what the demo printed
on my machine.

## The workflows

| # | Workflow | Trigger | What it does |
|---|----------|---------|--------------|
| 01 | [Speed-to-lead](workflows/01-speed-to-lead.json) | Webhook `POST /lead` (CRM or web form) | Verifies a shared secret, normalizes two payload shapes, runs guards (valid number, do-not-call, 6-hour dedupe), places an outbound AI call via Vapi within seconds, tags the CRM contact, responds 200 either way. |
| 02 | [End-of-call write-back](workflows/02-end-of-call-writeback.json) | Webhook (Vapi end-of-call report) | Turns the call's structured data into outcome tags (`ai-booked`, `ai-no-answer`, `needs-quote`) and a note on the GoHighLevel contact. The owner email is the backstop and fires even if the CRM call fails. |
| 03 | [Missed-call rescue](workflows/03-missed-call-rescue.json) | Webhook (Twilio call status, Twilio inbound SMS) | On an unanswered inbound call: text the caller back once a day at most, never if they texted STOP, email the owner, append to a log. |
| 04 | [Scheduled follow-up](workflows/04-scheduled-followup.json) | Cron `0 10 * * 1-5`, plus manual | Pulls contacts tagged `ai-no-answer`, decides per contact whether to call again (attempt cap, 6-day window, closed tags), paces the calls, tags `ai-attempt-N`, emails a summary. State lives in CRM tags. |
| 05 | [Error alerting](workflows/05-error-alerting.json) | Error Trigger | Shared error workflow for all the others. Throttles the same (workflow, node) failure to one alert an hour, emails on-call, posts to Slack if configured. |
| 06 | [Chatbot](workflows/06-chatbot-workflow-helper.json) | Chat Trigger (hosted chat page) | Hands each question to workflow 07, logs question, answer and similarity to Postgres `chat_log`, replies in the chat window. |
| 07 | [Lookup sub-workflow](workflows/07-lookup-workflow-subworkflow.json) | Called by 06 (Execute Workflow) | Embeds the question, `ORDER BY embedding <=> $1 LIMIT 3` in pgvector, returns the closest workflow with its cosine similarity. |
| 08 | [Indexer](workflows/08-index-workflows-to-postgres.json) | Cron nightly, plus manual | Reads every workflow from n8n's own REST API, builds a description (name, trigger, nodes, sticky notes), embeds it, upserts into `workflow_index`. |
| 09 | [Support ticket triage](workflows/09-support-ticket-triage.json) | Webhook `POST /ticket-triage` | Sends the ticket to Claude with a JSON schema (forced tool call), parses the structured triage (category, priority, sentiment, summary, suggested reply), answers the webhook with it. Needs `ANTHROPIC_API_KEY` in `.env.local`. |
| 10 | [Index PDFs](workflows/10-docs-ingest-pdfs.json) | Manual, nightly | Reads every PDF in `demo/pdfs`, extracts the text, splits it into chunks, upserts into `docs`. Postgres keeps a full-text index on it. |
| 11 | [Deterministic search](workflows/11-docs-search-api.json) | Webhook `POST /docs/search` | Keyword mode: `websearch_to_tsquery`, `ts_rank_cd`, `ts_headline` snippets. Exact mode: `ILIKE`. Same input, same rows, no model. |
| 12 | [Serve a PDF](workflows/12-docs-serve-pdf.json) | Webhook `GET /docs/file?name=` | Validates the name against the index, reads the file, responds with the binary as `application/pdf` inline. |
| 13 | [The web page](workflows/13-app-page.json) | Webhook `GET /app` | Responds with an HTML page whose buttons call 11, 12, 09 and the chat trigger, and draws the whole PDF with PDF.js next to the hits. No separate web server. |

![The page: exact-phrase search with the PDF rendered beside the hit](docs/img/14-app-search.jpg)

![The page: ticket triage](docs/img/15-app-triage.png)

![All eight workflows published](docs/img/00-workflows.png)

![Speed-to-lead](docs/img/01-speed-to-lead.png)

## What the demo proves

`demo/demo.sh` starts a throwaway Postgres, imports credentials and workflows
into a throwaway n8n, starts mock Vapi / GoHighLevel / Twilio servers and an
SMTP sink, then sends the same HTTP requests the real services send. Every
outcome is checked at the other end: which mock endpoints were hit with which
credentials, which emails arrived, which rows landed in Postgres.

| Event fired | What happened |
|---|---|
| New lead from the CRM | Vapi call placed, contact tagged `ai-attempt-1`, webhook answered `{"ok":true,"called":"+15555550101"}` |
| Same lead again inside 6 h | `{"skipped":"duplicate_within_6h"}`, no second call |
| Web-form shape, bad number | `{"skipped":"invalid_number"}`, still HTTP 200 so the sender does not retry |
| Wrong shared secret | HTTP 401, nothing runs |
| Vapi returns 500 | 3 attempts, execution fails, workflow 05 emails on-call within a second |
| Vapi end-of-call report, booked | `ai-booked` tag + note on the contact, "HOT" email to owner |
| Twilio no-answer callback | Rescue SMS, owner email, log row |
| Same caller again that day | Owner email says "no (already_texted_today)", no second SMS |
| Caller texts STOP, then misses a call | No SMS, reason `opted_out` |
| Follow-up cron run by hand | Calls Sam (attempt 3), skips Dana (booked in the step above), Luis (booked), Priya (attempt cap) |
| Indexer run by hand | 8 rows in `workflow_index`, each with a 256-dim vector |
| "what happens when a customer calls and nobody answers?" | Answer names workflow 03 with its similarity score, row written to `chat_log` |

![Executions](docs/img/06-executions.png)

Execution #5 is the deliberate failure. Open it in the editor and the failing
node is outlined in red with the 500 from the mock:

![Failed execution](docs/img/07-execution-error.png)

The chatbot, and the chat page it serves:

![Chatbot workflow](docs/img/08-chatbot.png)

![Chat page](docs/img/11-chat-page.png)

## How it is built

- **Config node, not `$env`.** Every workflow starts with a Set node holding
  URLs, secrets and emails. n8n Cloud blocks `$env` and Variables are paid;
  a Config node works everywhere. The demo rewrites those values to point at
  the mocks (`demo/prepare-demo.js`); the JSON in `workflows/` keeps the
  production values.
- **Credentials by name and id, never inline.** Six credentials, imported
  with `n8n import:credentials`, encrypted at rest with the instance key.
- **Guards before side effects.** Number validation, do-not-call, dedupe, and
  once-a-day checks run before the first outbound call or text.
- **State in the system of record.** Follow-up state is CRM tags, so the job
  and the CRM cannot disagree. Short-lived guards use workflow static data.
- **A backstop that always fires.** Owner email goes out even if the CRM API
  is down.
- **One error workflow for all of them**, wired through `settings.errorWorkflow`.
- **Parameterized SQL.** `$1, $2` placeholders in every Postgres node; the
  parameter list is an array expression so values with commas survive.
- **Sub-workflows for reuse.** 06 calls 07 with Execute Workflow; 07 can be
  called by anything else that needs "which workflow is this about?".
- **n8n as the web server.** Workflow 13 returns HTML from a Respond node. n8n
  wraps webhook responses in a sandbox CSP by default, which blocks the PDF
  viewer and scripts, so the run scripts set
  `N8N_INSECURE_DISABLE_WEBHOOK_IFRAME_SANDBOX=true` and the page renders PDFs
  with PDF.js instead of relying on the browser plugin.

## Reading list

- [docs/how-this-works.md](docs/how-this-works.md): webhooks, schedules,
  credentials, and when to use Zapier vs n8n vs code, with the client examples
  each decision came from.
- [docs/interview-prep.md](docs/interview-prep.md): Docker vs npm vs Cloud,
  multi-user and queue mode, sticky sessions, cosine similarity and pgvector.
- [docs/what-dad-did.md](docs/what-dad-did.md): the `docker run` + webhook +
  curl demo explained command by command, node by node, flag by flag.
- [docker-compose.yml](docker-compose.yml): the self-hosted production shape
  (n8n + Postgres/pgvector), with an optional queue-mode profile (Redis +
  workers). `demo/docker-demo.sh` drives it.

## Regenerating the JSON

The workflow files are generated by `demo/build-workflows.py` so the shared
pieces (Config node, embedding function, credential ids) stay identical across
all nine. Edit that file and run `npm run build`.
