# n8n workflows

Production automations I run for small-business clients (AI phone receptionists,
speed-to-lead callers, missed-call rescue, CRM write-backs), rebuilt as importable
[n8n](https://n8n.io) workflows. The originals are Node.js serverless functions on
Vercel; these are the same designs expressed as n8n nodes so a non-programmer can
open them, read them, and change a threshold without a deploy.

| # | Workflow | Trigger | What it does |
|---|----------|---------|--------------|
| 01 | [Speed-to-lead](workflows/01-speed-to-lead.json) | Webhook (CRM or web form) | Verifies a shared secret, normalizes two payload shapes into one lead, runs guards (valid number, do-not-call, 6-hour dedupe), places an outbound AI call via Vapi within seconds, tags the CRM contact `ai-attempt-1`, responds 200 either way. |
| 02 | [End-of-call write-back](workflows/02-end-of-call-writeback.json) | Webhook (Vapi end-of-call report) | Turns the call's structured data into outcome tags (`ai-booked`, `ai-no-answer`, `needs-quote`, …) plus a human-readable note on the GoHighLevel contact. The owner email is the backstop and fires even if the CRM call fails. |
| 03 | [Missed-call rescue](workflows/03-missed-call-rescue.json) | Webhook (Twilio call status) | On `no-answer`/`busy`/`failed` inbound calls: texts the caller back (once per day per number, never if opted out), emails the owner, appends to a Google Sheet. A second webhook records STOP/START so a plain Twilio number honours opt-outs. |
| 04 | [Scheduled follow-up](workflows/04-scheduled-followup.json) | Cron, weekdays 10:00 shop time | Pulls contacts tagged `ai-no-answer`, decides per contact whether to call again (max attempts, 6-day window, closed tags), paces calls 20 s apart, tags `ai-attempt-N`, emails a daily summary. State lives in CRM tags so the job and the CRM can never disagree. |
| 05 | [Error alerting](workflows/05-error-alerting.json) | Error Trigger | Shared error workflow for the others: builds a readable alert, throttles the same (workflow, node) failure to one per hour, emails on-call and posts to Slack. |

## Design rules these follow

- **Idempotent and safe to re-run.** Every write is a tag or a note keyed to a contact; re-running a failed execution does not double-call anyone.
- **Guards before side effects.** Number validation, do-not-call, and dedupe run before the first outbound call or text.
- **State in the system of record.** Follow-up state is CRM tags, not a second database, so nothing drifts.
- **A backstop that always fires.** Email goes out even if the CRM API is down. A CRM hiccup must never cost the shop a lead.
- **Secrets stay out of the JSON.** Credentials are referenced by name; everything else is `$env.*`. See below.
- **Every workflow points at `05-error-alerting`** via `settings.errorWorkflow`.

## Importing

Verified: all five import cleanly on n8n 2.37.9 (Node 24) via the CLI below, and every node type / typeVersion resolves against `n8n-nodes-base`.

```bash
# CLI
n8n import:workflow --separate --input=./workflows

# or in the editor: Workflow menu → Import from File
```

Then create these credentials (names must match): `Vapi API key` (Header Auth,
`Authorization: Bearer …`), `GoHighLevel API token` (Header Auth), `Twilio`,
`SMTP (Resend)`, `Google Sheets`.

Environment variables the workflows read:

```
LEAD_WEBHOOK_SECRET   VAPI_WEBHOOK_SECRET
VAPI_ASSISTANT_ID     VAPI_ASSISTANT_ID_FOLLOWUP   VAPI_PHONE_NUMBER_ID
GHL_LOCATION_ID       FOLLOWUP_MAX_ATTEMPTS=4      FOLLOWUP_WINDOW_DAYS=6
BUSINESS_NAME         OWNER_EMAIL   ONCALL_EMAIL   ALERT_FROM
CALL_LOG_SHEET_ID     SLACK_WEBHOOK_URL
```

n8n only exposes `$env` in expressions when `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

## Where these came from

The Node.js originals run in production for paying clients (auto detailing,
tree service, pressure washing, moving, a medspa). Vapi, Twilio and GoHighLevel
payload shapes in the Code nodes are copied from those services, not invented.
