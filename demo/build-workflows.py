#!/usr/bin/env python3
"""Generate the workflow JSON files in ../workflows.

Everything configurable (API base URLs, shared secrets, emails, pacing) lives in
a single "Config" Set node at the top of each workflow. That is the portable
way to do it: n8n Cloud blocks $env in expressions, and Variables are a paid
feature. The demo script points those same Config values at local mock servers
by editing the JSON before import (see prepare-demo.js), so production JSON and
demo JSON are the same files with different Config values.

Run:  python3 demo/build-workflows.py
"""
import json, os, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "workflows"
OUT.mkdir(exist_ok=True)

# Production defaults. The demo overrides the *Base URLs and secrets.
CONFIG = {
    "vapiBase": "https://api.vapi.ai",
    "ghlBase": "https://services.leadconnectorhq.com",
    "twilioBase": "https://api.twilio.com",
    "logBase": "https://your-log-endpoint.example.com",
    "leadWebhookSecret": "CHANGE-ME",
    "vapiWebhookSecret": "CHANGE-ME",
    "vapiAssistantId": "asst_speed_to_lead",
    "vapiAssistantIdFollowup": "asst_follow_up",
    "vapiPhoneNumberId": "pn_xxx",
    "ghlLocationId": "loc_xxx",
    "twilioAccountSid": "ACxxxxxxxx",
    "businessName": "Reflections Mobile Detailing",
    "ownerEmail": "owner@example.com",
    "oncallEmail": "maria@example.com",
    "alertFrom": "alerts@example.com",
    "slackWebhookUrl": "",
    "followupMaxAttempts": 4,
    "followupWindowDays": 6,
    "paceSeconds": 20,
    "n8nBase": "http://localhost:5678",
    "anthropicBase": "https://api.anthropic.com",
    "triageModel": "claude-sonnet-5",
    "docsDir": "/data/pdfs",
}

import uuid
def node(name, typ, ver, pos, params, **extra):
    d = {"parameters": params, "name": name, "type": typ, "typeVersion": ver, "position": pos}
    # Webhook-style nodes need a webhookId or n8n registers the path as
    # <workflowId>/<node name>/<path> instead of just <path>. The editor sets
    # this for you; hand-written JSON has to. Stable per node name.
    if typ in ("n8n-nodes-base.webhook", "n8n-nodes-base.wait", "@n8n/n8n-nodes-langchain.chatTrigger"):
        d["webhookId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "n8n-workflows/" + name))
    d.update(extra)
    return d

def config_node(pos=[220, 300], keys=None):
    keys = keys or list(CONFIG)
    assigns = []
    for k in keys:
        v = CONFIG[k]
        assigns.append({"id": k, "name": k, "value": v, "type": "number" if isinstance(v, (int, float)) else "string"})
    return node("Config", "n8n-nodes-base.set", 3.4, pos,
                {"assignments": {"assignments": assigns}, "includeOtherFields": True, "options": {}})

def C(key):
    return f"$('Config').item.json.{key}"

def sticky(content, pos, w=420, h=160):
    return node("Sticky Note", "n8n-nodes-base.stickyNote", 1, pos, {"content": content, "width": w, "height": h})

# Fixed ids so the other four can point at the error workflow by id, and so
# re-importing updates in place instead of creating duplicates.
IDS = {"01": "mpSpeedToLead001", "02": "mpEndOfCallWb002", "03": "mpMissedCall0003",
       "04": "mpFollowupCron04", "05": "mpErrorAlert0005", "06": "mpChatBot0000006",
       "07": "mpLookupWf000007", "08": "mpIndexer0000008", "09": "mpTicketTriage09",
       "10": "mpDocsIngest0010", "11": "mpDocsSearch0011", "12": "mpDocsFile00012", "13": "mpAppPage000013"}
CRED_IDS = {"Vapi API key": "mpCredVapi000001", "GoHighLevel API token": "mpCredGhl0000002",
            "Twilio (basic auth)": "mpCredTwilio0003", "SMTP (Resend)": "mpCredSmtp000004",
            "Postgres (workflow index)": "mpCredPg00000005", "n8n API key (self)": "mpCredN8nApi0006",
            "Anthropic API key": "mpCredAnthropic7"}

def wf(num, name, nodes, conns, settings=None):
    i = 0
    for n in nodes:
        if n["type"] == "n8n-nodes-base.stickyNote":
            i += 1
            n["name"] = f"Note {i}"
        for ctype, c in (n.get("credentials") or {}).items():
            c["id"] = CRED_IDS[c["name"]]
    settings = dict(settings or {"executionOrder": "v1"})
    if num != "05":
        settings["errorWorkflow"] = IDS["05"]
    return {"id": IDS[num], "name": name, "nodes": nodes, "connections": conns, "active": False,
            "settings": settings}

def L(b):
    return {"node": b, "type": "main", "index": 0}

def IF(name, pos, conds, combinator="and"):
    return node(name, "n8n-nodes-base.if", 2.2, pos,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                "conditions": conds, "combinator": combinator}, "options": {}})

def cond(id, left, op, right="", typ="string", single=False):
    c = {"id": id, "leftValue": left, "rightValue": right, "operator": {"type": typ, "operation": op}}
    if single:
        c["operator"]["singleValue"] = True
    return c

def http(name, pos, method, url, body=None, cred=None, headers=None, retry=True, on_error=None, query=None, form=None):
    p = {"method": method, "url": url, "options": {}}
    if retry:
        p["options"]["retry"] = {"maxTries": 3, "waitBetweenTries": 1500}
    if cred:
        p["authentication"] = "genericCredentialType"
        p["genericAuthType"] = cred[0]
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}
    if query:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
    if body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    if form is not None:
        p["sendBody"] = True
        p["contentType"] = "form-urlencoded"
        p["bodyParameters"] = {"parameters": [{"name": k, "value": v} for k, v in form.items()]}
    extra = {}
    if cred:
        extra["credentials"] = {cred[0]: {"name": cred[1]}}
    if on_error:
        extra["onError"] = on_error
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, **extra)

GHL_HDR = {"Version": "2021-07-28"}
GHL_CRED = ("httpHeaderAuth", "GoHighLevel API token")
VAPI_CRED = ("httpHeaderAuth", "Vapi API key")
TWILIO_CRED = ("httpBasicAuth", "Twilio (basic auth)")
SMTP = {"smtp": {"name": "SMTP (Resend)"}}

def email(name, pos, subject, text, to, execute_once=False):
    extra = {"credentials": SMTP}
    if execute_once:
        extra["executeOnce"] = True
    return node(name, "n8n-nodes-base.emailSend", 2.1, pos,
                {"fromEmail": "={{ " + C("alertFrom") + " }}", "toEmail": "={{ " + C(to) + " }}",
                 "subject": subject, "emailFormat": "text", "text": text, "options": {}}, **extra)

def dump(fname, w):
    (OUT / fname).write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n")
    print("wrote", fname, len(w["nodes"]), "nodes")

# ───────────────────────── 01 speed-to-lead ─────────────────────────
n = [
    sticky("## Speed-to-lead\nA new lead lands (CRM workflow or web form) → verify it really came from us → normalize → guards → call them within seconds → tag the CRM contact.\n\nThe webhook answers 200 for skipped leads too. A non-2xx would make the CRM retry and re-send the same lead.", [0, 40], 560, 170),
    node("New lead webhook", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "POST", "path": "lead", "responseMode": "responseNode", "options": {}}),
    config_node([220, 300]),
    IF("Verify shared secret", [440, 300],
       [cond("secret", "={{ $json.headers['x-webhook-secret'] }}", "equals", "={{ " + C("leadWebhookSecret") + " }}")]),
    node("Reject 401", "n8n-nodes-base.respondToWebhook", 1.1, [660, 480],
         {"respondWith": "json", "responseBody": "={{ { error: 'bad secret' } }}", "options": {"responseCode": 401}}),
    node("Normalize lead", "n8n-nodes-base.code", 2, [660, 200], {"jsCode": r"""
// Two callers, one path: a CRM workflow webhook (GoHighLevel shape) and a
// plain web form. Both end up as the same lead object.
const b = $input.first().json.body || {};
const c = b.customData || b.custom_data || {};
const first = b.first_name || b.firstName || (b.name || '').split(' ')[0] || '';
const last  = b.last_name  || b.lastName  || (b.name ? b.name.split(' ').slice(1).join(' ') : '');
const raw   = String(b.phone || c.phone || '').replace(/[^\d+]/g, '');
const phone = raw.startsWith('+') ? raw
            : raw.length === 10 ? '+1' + raw
            : raw.length === 11 && raw.startsWith('1') ? '+' + raw : '';
return [{ json: {
  contactId: b.contact_id || b.id || null,
  name: `${first} ${last}`.trim() || 'there',
  phone,
  service: b.service || c.service || '',
  vehicle: b.vehicle || c.vehicle || '',
  source:  b.source  || c.source  || (b.customData ? 'ghl' : 'web-form'),
  receivedAt: new Date().toISOString(),
}}];
"""}),
    node("Guards: valid number, DNC, dedupe", "n8n-nodes-base.code", 2, [880, 200], {"jsCode": r"""
// Never call a malformed number, a do-not-call number, or the same number
// twice inside the window. Workflow static data is n8n's built-in per-workflow
// store: it survives restarts and needs no database.
const lead = $input.first().json;
const store = $getWorkflowStaticData('global');
store.recent = store.recent || {};
store.dnc    = store.dnc    || [];
const now = Date.now(), WINDOW = 6 * 60 * 60 * 1000;
for (const k of Object.keys(store.recent)) if (now - store.recent[k] > WINDOW) delete store.recent[k];

let reason = null;
if (!/^\+1\d{10}$/.test(lead.phone))     reason = 'invalid_number';
else if (store.dnc.includes(lead.phone))  reason = 'do_not_call';
else if (store.recent[lead.phone])        reason = 'duplicate_within_6h';
if (!reason) store.recent[lead.phone] = now;
return [{ json: { ...lead, ok: !reason, skipReason: reason } }];
"""}),
    IF("Passes guards?", [1100, 200], [cond("ok", "={{ $json.ok }}", "true", typ="boolean", single=True)]),
    http("Place AI outbound call (Vapi)", [1320, 100], "POST", "={{ " + C("vapiBase") + " }}/call",
         body="={{ JSON.stringify({\n  assistantId: " + C("vapiAssistantId") + ",\n  phoneNumberId: " + C("vapiPhoneNumberId") + ",\n  customer: { number: $json.phone, name: $json.name },\n  assistantOverrides: { variableValues: { name: $json.name, service: $json.service, vehicle: $json.vehicle } },\n  metadata: { contactId: $json.contactId, source: $json.source }\n}) }}",
         cred=VAPI_CRED),
    http("Tag contact: ai-attempt-1", [1540, 100], "POST",
         "={{ " + C("ghlBase") + " }}/contacts/{{ $('Normalize lead').item.json.contactId }}/tags",
         body="={{ JSON.stringify({ tags: ['ai-called', 'ai-attempt-1'] }) }}", cred=GHL_CRED, headers=GHL_HDR),
    node("Respond 200 (called)", "n8n-nodes-base.respondToWebhook", 1.1, [1760, 100],
         {"respondWith": "json", "responseBody": "={{ { ok: true, called: $('Normalize lead').item.json.phone, callId: $('Place AI outbound call (Vapi)').item.json.id } }}", "options": {}}),
    node("Respond 200 (skipped)", "n8n-nodes-base.respondToWebhook", 1.1, [1320, 340],
         {"respondWith": "json", "responseBody": "={{ { ok: true, skipped: $json.skipReason } }}", "options": {}}),
]
c = {
    "New lead webhook": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Verify shared secret")]]},
    "Verify shared secret": {"main": [[L("Normalize lead")], [L("Reject 401")]]},
    "Normalize lead": {"main": [[L("Guards: valid number, DNC, dedupe")]]},
    "Guards: valid number, DNC, dedupe": {"main": [[L("Passes guards?")]]},
    "Passes guards?": {"main": [[L("Place AI outbound call (Vapi)")], [L("Respond 200 (skipped)")]]},
    "Place AI outbound call (Vapi)": {"main": [[L("Tag contact: ai-attempt-1")]]},
    "Tag contact: ai-attempt-1": {"main": [[L("Respond 200 (called)")]]},
}
dump("01-speed-to-lead.json", wf("01", "01 Speed-to-lead: webhook, AI call, CRM tag", n, c))

# ───────────────────────── 02 end-of-call write-back ─────────────────────────
n = [
    sticky("## End-of-call write-back\nVapi POSTs a report when a call ends. Turn its structured data into CRM tags the shop's own nurture automation branches on, plus a note a human can read in ten seconds.\n\nThe owner email is the backstop: it fires even when the CRM API fails (those two nodes are set to continue on error).", [0, 40], 560, 170),
    node("Vapi end-of-call webhook", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "POST", "path": "vapi/end-of-call", "responseMode": "onReceived", "options": {}}),
    config_node([220, 300]),
    IF("Is a real end-of-call report?", [440, 300], [
        cond("secret", "={{ $json.headers['x-vapi-secret'] }}", "equals", "={{ " + C("vapiWebhookSecret") + " }}"),
        cond("type", "={{ $json.body.message.type }}", "equals", "end-of-call-report")]),
    node("Extract outcome + tags", "n8n-nodes-base.code", 2, [660, 200], {"jsCode": r"""
const msg = $input.first().json.body.message;
const d = msg.analysis?.structuredData || {};
const call = msg.call || {};
const contactId = call.metadata?.contactId || null;
const endedReason = msg.endedReason || '';

const tags = ['ai-call-complete'];
if (d.booked) tags.push('ai-booked');
else if (d.needs_owner_callback) tags.push('ai-needs-callback');
else if (d.reached === 'voicemail') tags.push('ai-voicemail');
else if (d.reached === 'wrong_number') tags.push('ai-wrong-number');
else if (d.reached === 'no_answer' || /no-answer|did-not-answer/i.test(endedReason)) tags.push('ai-no-answer');
else tags.push('ai-reached-no-booking');
if (d.price_deferred) tags.push('needs-quote');
if (d.in_service_area === false) tags.push('out-of-area');
if (d.do_not_call) tags.push('ai-do-not-call');

const note = [
  'AI speed-to-lead call',
  d.reached ? `Reached: ${d.reached}` : null,
  `Service: ${d.service || '—'}`,
  d.vehicle ? `Vehicle: ${d.vehicle}` : null,
  d.quoted_price ? `Quoted: ${d.quoted_price}` : null,
  d.price_deferred ? 'PRICE NOT QUOTED. Owner needs to send the number.' : null,
  d.booked ? `BOOKED: ${d.appointment || 'time not captured'}` : 'Not booked',
  d.objection ? `Hesitation: ${d.objection}` : null,
  d.needs_owner_callback ? `CALL THEM BACK: ${d.callback_reason || ''}` : null,
  endedReason ? `Ended: ${endedReason}` : null,
  msg.summary ? `\n${msg.summary}` : null,
  msg.recordingUrl ? `Recording: ${msg.recordingUrl}` : null,
].filter(Boolean).join('\n');

return [{ json: {
  contactId, tags, note,
  hot: !!(d.booked || d.needs_owner_callback),
  customer: call.customer?.number || '',
  outcome: tags[1] || 'unknown',
}}];
"""}),
    IF("Has CRM contact?", [880, 200], [cond("cid", "={{ $json.contactId }}", "notEmpty", single=True)]),
    http("Add outcome tags", [1100, 100], "POST", "={{ " + C("ghlBase") + " }}/contacts/{{ $json.contactId }}/tags",
         body="={{ JSON.stringify({ tags: $json.tags }) }}", cred=GHL_CRED, headers=GHL_HDR, on_error="continueRegularOutput"),
    http("Add call note", [1320, 100], "POST",
         "={{ " + C("ghlBase") + " }}/contacts/{{ $('Extract outcome + tags').item.json.contactId }}/notes",
         body="={{ JSON.stringify({ body: $('Extract outcome + tags').item.json.note }) }}", cred=GHL_CRED, headers=GHL_HDR, on_error="continueRegularOutput"),
    email("Email owner (backstop, always fires)", [1540, 200],
          "={{ ($('Extract outcome + tags').item.json.hot ? 'HOT ' : '') + 'AI call ' + $('Extract outcome + tags').item.json.outcome + ' ' + $('Extract outcome + tags').item.json.customer }}",
          "={{ $('Extract outcome + tags').item.json.note }}", "ownerEmail"),
]
c = {
    "Vapi end-of-call webhook": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Is a real end-of-call report?")]]},
    "Is a real end-of-call report?": {"main": [[L("Extract outcome + tags")], []]},
    "Extract outcome + tags": {"main": [[L("Has CRM contact?")]]},
    "Has CRM contact?": {"main": [[L("Add outcome tags")], [L("Email owner (backstop, always fires)")]]},
    "Add outcome tags": {"main": [[L("Add call note")]]},
    "Add call note": {"main": [[L("Email owner (backstop, always fires)")]]},
}
dump("02-end-of-call-writeback.json", wf("02", "02 End-of-call write-back: Vapi report to CRM tags, note, email", n, c))

# ───────────────────────── 03 missed-call rescue ─────────────────────────
n = [
    sticky("## Missed-call rescue\nA customer calls the shop and nobody answers (no-answer, busy, or failed). Twilio POSTs a status callback after every call; on a missed inbound call, text the caller back once (never twice in a day, never if they texted STOP), email the owner, and log it.\n\nThe second webhook records STOP/START. A plain Twilio number does not enforce opt-outs for you; a Messaging Service does.", [0, 40], 560, 190),
    node("Twilio call-status webhook", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "POST", "path": "twilio/call-status", "responseMode": "onReceived", "options": {}}),
    config_node([220, 300]),
    IF("Missed inbound call?", [440, 300], [
        cond("status", "={{ ['no-answer','busy','failed'].includes($json.body.DialCallStatus || $json.body.CallStatus) }}", "true", typ="boolean", single=True),
        cond("inbound", "={{ $json.body.Direction }}", "equals", "inbound")]),
    node("Shape + opt-out + once-a-day", "n8n-nodes-base.code", 2, [660, 200], {"jsCode": r"""
const b = $input.first().json.body;
const from = b.From, to = b.To;
const store = $getWorkflowStaticData('global');
store.optOut = store.optOut || [];
store.texted = store.texted || {};
const now = Date.now(), DAY = 24 * 60 * 60 * 1000;
const already  = store.texted[from] && now - store.texted[from] < DAY;
const optedOut = store.optOut.includes(from);
if (!already && !optedOut) store.texted[from] = now;
return [{ json: {
  from, to, callSid: b.CallSid, status: b.DialCallStatus || b.CallStatus,
  send: !already && !optedOut,
  reason: optedOut ? 'opted_out' : already ? 'already_texted_today' : null,
  at: new Date().toISOString(),
}}];
"""}),
    IF("Send rescue text?", [880, 200], [cond("send", "={{ $json.send }}", "true", typ="boolean", single=True)]),
    http("SMS the caller back (Twilio)", [1100, 100], "POST",
         "={{ " + C("twilioBase") + " }}/2010-04-01/Accounts/{{ " + C("twilioAccountSid") + " }}/Messages.json",
         form={"From": "={{ $json.to }}", "To": "={{ $json.from }}",
               "Body": "={{ " + C("businessName") + " }} here, sorry we missed you. Reply with what you need (service and vehicle or address) and we'll get you a quote or a time. Reply STOP to opt out."},
         cred=TWILIO_CRED, on_error="continueRegularOutput"),
    email("Email owner the missed call", [1320, 200],
          "=Missed call from {{ $('Shape + opt-out + once-a-day').item.json.from }} ({{ $('Shape + opt-out + once-a-day').item.json.status }})",
          "=Missed call at {{ $('Shape + opt-out + once-a-day').item.json.at }}\nFrom: {{ $('Shape + opt-out + once-a-day').item.json.from }}\nRescue text sent: {{ $('Shape + opt-out + once-a-day').item.json.send ? 'yes' : 'no (' + $('Shape + opt-out + once-a-day').item.json.reason + ')' }}\nCall SID: {{ $('Shape + opt-out + once-a-day').item.json.callSid }}",
          "ownerEmail"),
    http("Append to call log", [1540, 200], "POST", "={{ " + C("logBase") + " }}/missed-calls",
         body="={{ JSON.stringify($('Shape + opt-out + once-a-day').item.json) }}", on_error="continueRegularOutput", retry=False),
    node("Twilio inbound SMS webhook", "n8n-nodes-base.webhook", 2, [0, 640],
         {"httpMethod": "POST", "path": "twilio/inbound-sms", "responseMode": "onReceived", "options": {}}),
    node("Record STOP / START", "n8n-nodes-base.code", 2, [220, 640], {"jsCode": r"""
const b = $input.first().json.body;
const body = String(b.Body || '').trim().toLowerCase();
const store = $getWorkflowStaticData('global');
store.optOut = store.optOut || [];
let action = 'none';
if (/^(stop|stopall|unsubscribe|cancel|end|quit)$/.test(body)) { if (!store.optOut.includes(b.From)) store.optOut.push(b.From); action = 'opt_out'; }
if (/^(start|unstop|yes)$/.test(body)) { store.optOut = store.optOut.filter(n => n !== b.From); action = 'opt_in'; }
return [{ json: { from: b.From, body: b.Body, action, optOutList: store.optOut } }];
"""}),
]
c = {
    "Twilio call-status webhook": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Missed inbound call?")]]},
    "Missed inbound call?": {"main": [[L("Shape + opt-out + once-a-day")], []]},
    "Shape + opt-out + once-a-day": {"main": [[L("Send rescue text?")]]},
    "Send rescue text?": {"main": [[L("SMS the caller back (Twilio)")], [L("Email owner the missed call")]]},
    "SMS the caller back (Twilio)": {"main": [[L("Email owner the missed call")]]},
    "Email owner the missed call": {"main": [[L("Append to call log")]]},
    "Twilio inbound SMS webhook": {"main": [[L("Record STOP / START")]]},
}
dump("03-missed-call-rescue.json", wf("03", "03 Missed-call rescue: Twilio status to SMS, email, log", n, c))

# ───────────────────────── 04 scheduled follow-up ─────────────────────────
n = [
    sticky("## Scheduled follow-up\nRuns weekdays at 10:00 shop time. Pulls contacts the AI could not reach, decides per contact whether to try again, paces the calls, and tags each attempt.\n\nState lives in CRM tags (ai-attempt-N, ai-booked, ai-do-not-call...), so what the owner sees in the CRM and what this job believes can never drift apart.", [0, 40], 560, 190),
    node("Weekdays 10:00 shop time", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "0 10 * * 1-5"}]}}),
    node("Run now (manual)", "n8n-nodes-base.manualTrigger", 1, [0, 480], {}),
    config_node([220, 300]),
    http("Find contacts tagged ai-no-answer", [440, 300], "GET", "={{ " + C("ghlBase") + " }}/contacts/",
         query={"locationId": "={{ " + C("ghlLocationId") + " }}", "query": "ai-no-answer", "limit": "100"},
         cred=GHL_CRED, headers=GHL_HDR),
    node("Split contacts", "n8n-nodes-base.splitOut", 1, [660, 300], {"fieldToSplitOut": "contacts", "options": {}}),
    node("Decide: call again, or stop?", "n8n-nodes-base.code", 2, [880, 300], {"jsCode": r"""
const cfg = $('Config').first().json;
const MAX_ATTEMPTS = Number(cfg.followupMaxAttempts || 4);
const WINDOW_DAYS  = Number(cfg.followupWindowDays  || 6);
const CLOSED = ['ai-booked', 'ai-do-not-call', 'ai-bought-elsewhere', 'ai-not-interested'];
const out = [];
for (const item of $input.all()) {
  const c = item.json;
  const tags = (c.tags || []).map(t => String(t).toLowerCase());
  let attempt = 1;
  for (const t of tags) { const m = /^ai-attempt-(\d+)$/.exec(t); if (m) attempt = Math.max(attempt, Number(m[1])); }
  const ageDays = c.dateAdded ? (Date.now() - new Date(c.dateAdded)) / 86400000 : 0;
  let skip = null;
  if (tags.some(t => CLOSED.includes(t))) skip = 'closed';
  else if (attempt >= MAX_ATTEMPTS)        skip = 'max_attempts';
  else if (ageDays > WINDOW_DAYS)          skip = 'outside_window';
  else if (!c.phone)                       skip = 'no_phone';
  out.push({ json: { contactId: c.id, name: c.firstName || c.contactName || 'there', phone: c.phone,
                     attempt, nextAttempt: attempt + 1, skip } });
}
return out;
"""}),
    IF("Eligible?", [1100, 300], [cond("skip", "={{ $json.skip }}", "empty", single=True)]),
    node("Pace the calls", "n8n-nodes-base.wait", 1.1, [1320, 200],
         {"amount": "={{ " + C("paceSeconds") + " }}", "unit": "seconds"}),
    http("Follow-up call (Vapi)", [1540, 200], "POST", "={{ " + C("vapiBase") + " }}/call",
         body="={{ JSON.stringify({\n  assistantId: " + C("vapiAssistantIdFollowup") + ",\n  phoneNumberId: " + C("vapiPhoneNumberId") + ",\n  customer: { number: $json.phone, name: $json.name },\n  assistantOverrides: { variableValues: { name: $json.name, attempt: $json.nextAttempt } },\n  metadata: { contactId: $json.contactId }\n}) }}",
         cred=VAPI_CRED),
    http("Tag ai-attempt-N", [1760, 200], "POST",
         "={{ " + C("ghlBase") + " }}/contacts/{{ $('Eligible?').item.json.contactId }}/tags",
         body="={{ JSON.stringify({ tags: ['ai-attempt-' + $('Eligible?').item.json.nextAttempt] }) }}", cred=GHL_CRED, headers=GHL_HDR),
    node("Merge called + skipped", "n8n-nodes-base.merge", 3, [1980, 300], {"numberInputs": 2}),
    node("Summarize the pass", "n8n-nodes-base.code", 2, [2200, 300], {"jsCode": r"""
const called = $('Eligible?').all(0).map(i => i.json);
const skipped = $('Eligible?').all(1).map(i => i.json);
const text = [
  'Called:', ...(called.map(c => `  ${c.name} ${c.phone} (attempt ${c.nextAttempt})`)), called.length ? '' : '  none', '',
  'Skipped:', ...(skipped.map(c => `  ${c.name} (${c.skip})`)), skipped.length ? '' : '  none',
].join('\n');
return [{ json: { subject: `Follow-up pass: ${called.length} called, ${skipped.length} skipped`, text } }];
"""}, executeOnce=True),
    email("Daily summary email", [2420, 300], "={{ $json.subject }}", "={{ $json.text }}", "ownerEmail"),
]
c = {
    "Weekdays 10:00 shop time": {"main": [[L("Config")]]},
    "Run now (manual)": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Find contacts tagged ai-no-answer")]]},
    "Find contacts tagged ai-no-answer": {"main": [[L("Split contacts")]]},
    "Split contacts": {"main": [[L("Decide: call again, or stop?")]]},
    "Decide: call again, or stop?": {"main": [[L("Eligible?")]]},
    "Eligible?": {"main": [[L("Pace the calls")], [{"node": "Merge called + skipped", "type": "main", "index": 1}]]},
    "Pace the calls": {"main": [[L("Follow-up call (Vapi)")]]},
    "Follow-up call (Vapi)": {"main": [[L("Tag ai-attempt-N")]]},
    "Tag ai-attempt-N": {"main": [[{"node": "Merge called + skipped", "type": "main", "index": 0}]]},
    "Merge called + skipped": {"main": [[L("Summarize the pass")]]},
    "Summarize the pass": {"main": [[L("Daily summary email")]]},
}
dump("04-scheduled-followup.json", wf("04", "04 Scheduled follow-up: weekday cron with tag-based state", n, c,
                                      settings={"executionOrder": "v1", "timezone": "America/Los_Angeles"}))

# ───────────────────────── 05 error alerting ─────────────────────────
n = [
    sticky("## Error workflow\nSet as the Error Workflow on the other workflows (workflow Settings). n8n runs it whenever one of them fails, with the failing workflow, node, and error message as input.\n\nSame (workflow, node) failure alerts once an hour, not once per execution. A flapping API should not fill the inbox.", [0, 40], 560, 170),
    node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, [0, 300], {}),
    config_node([220, 300], keys=["alertFrom", "oncallEmail", "slackWebhookUrl"]),
    node("Build alert", "n8n-nodes-base.code", 2, [440, 300], {"jsCode": r"""
const e = $input.first().json;
const wf = e.workflow || {}, ex = e.execution || {};
const err = ex.error || {};
const last = ex.lastNodeExecuted || '—';
return [{ json: {
  subject: `[n8n] ${wf.name || 'workflow'} failed at "${last}"`,
  text: [
    `Workflow: ${wf.name} (${wf.id})`,
    `Execution: ${ex.id}  mode=${ex.mode}  retry=${ex.retryOf || 'no'}`,
    `Node: ${last}`,
    `Error: ${err.message || JSON.stringify(err).slice(0, 500)}`,
    ex.url ? `Open: ${ex.url}` : null,
  ].filter(Boolean).join('\n'),
  fingerprint: `${wf.id}:${last}`,
  slackWebhookUrl: $('Config').first().json.slackWebhookUrl || '',
}}];
"""}),
    node("Throttle: same failure once an hour", "n8n-nodes-base.code", 2, [660, 300], {"jsCode": r"""
const a = $input.first().json;
const store = $getWorkflowStaticData('global');
store.seen = store.seen || {};
const now = Date.now();
for (const k of Object.keys(store.seen)) if (now - store.seen[k] > 3600000) delete store.seen[k];
const suppressed = !!store.seen[a.fingerprint];
if (!suppressed) store.seen[a.fingerprint] = now;
return [{ json: { ...a, suppressed } }];
"""}),
    IF("Send?", [880, 300], [cond("s", "={{ $json.suppressed }}", "false", typ="boolean", single=True)]),
    email("Email on-call", [1100, 200], "={{ $json.subject }}", "={{ $json.text }}", "oncallEmail"),
    IF("Slack configured?", [1100, 440], [cond("slack", "={{ $json.slackWebhookUrl }}", "notEmpty", single=True)]),
    http("Post to Slack", [1320, 440], "POST", "={{ $json.slackWebhookUrl }}",
         body="={{ JSON.stringify({ text: $json.subject + '\\n' + $json.text }) }}", on_error="continueRegularOutput", retry=False),
]
c = {
    "Error Trigger": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Build alert")]]},
    "Build alert": {"main": [[L("Throttle: same failure once an hour")]]},
    "Throttle: same failure once an hour": {"main": [[L("Send?")]]},
    "Send?": {"main": [[L("Email on-call"), L("Slack configured?")], []]},
    "Slack configured?": {"main": [[L("Post to Slack")], []]},
}
dump("05-error-alerting.json", wf("05", "05 Error alerting (shared error workflow)", n, c))

# ───────────────────────── shared: the embedding function ─────────────────────────
# A hashed bag-of-words vector, 256 dimensions, unit length. No API needed, and the
# cosine similarity math is explicit. Swap for an Embeddings node for real semantics.
EMBED_JS = r"""
const DIM = 256;
const STOP = new Set('a an the and or of to in on for with is are be by at as it this that from into when what how do does which who does'.split(' '));
function stem(w) {           // crude suffix stripping so calls/called/calling all land on "call"
  return w.replace(/(ings?|ed|es|s)$/, '').replace(/(ly|er)$/, '') || w;
}
function tokens(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9\s-]/g, ' ').split(/\s+/)
    .filter(w => w.length > 2 && !STOP.has(w)).map(stem);
}
function fnv(str) {            // FNV-1a 32-bit hash -> which dimension a word lands in
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h;
}
function embed(text) {
  const v = new Array(DIM).fill(0);
  for (const w of tokens(text)) {
    const h = fnv(w);
    v[h % DIM] += (h & 0x80000000) ? -1 : 1;   // sign from one hash bit spreads words out
  }
  const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0)) || 1;   // ‖v‖
  return v.map(x => +(x / norm).toFixed(6));                        // unit length, so a·b == cos θ
}
"""

PG_CRED = ("postgres", "Postgres (workflow index)")

# queryReplacement is normally a comma-separated list; an expression that returns an
# array is passed through as the parameter list, which is the only safe form when a
# value can itself contain commas (descriptions do).
def pg_query(name, pos, sql, params_expr, on_error=None):
    extra = {"credentials": {"postgres": {"name": PG_CRED[1]}}}
    if on_error:
        extra["onError"] = on_error
    return node(name, "n8n-nodes-base.postgres", 2.6, pos,
                {"operation": "executeQuery", "query": sql, "options": {"queryReplacement": params_expr}}, **extra)

# ───────────────────────── 08 indexer ─────────────────────────
n = [
    sticky("## Index the workflows into Postgres\nAsks n8n's own REST API for every workflow, builds a one-paragraph description of each (name, trigger, nodes, sticky notes), turns it into a vector, and upserts it into `workflow_index` with pgvector.\n\nRuns nightly and on demand. Workflow 07 searches this table; 06 is the chat on top.", [0, 40], 600, 170),
    node("Nightly 02:00", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 300],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "0 2 * * *"}]}}),
    node("Run now (manual)", "n8n-nodes-base.manualTrigger", 1, [0, 480], {}),
    config_node([220, 300], keys=["n8nBase"]),
    http("GET /api/v1/workflows (n8n public API)", [440, 300], "GET", "={{ " + C("n8nBase") + " }}/api/v1/workflows",
         query={"limit": "100"}, cred=("httpHeaderAuth", "n8n API key (self)")),
    node("One item per workflow", "n8n-nodes-base.splitOut", 1, [660, 300], {"fieldToSplitOut": "data", "options": {}}),
    node("Describe + embed", "n8n-nodes-base.code", 2, [880, 300], {"jsCode": EMBED_JS + r"""
const out = [];
for (const item of $input.all()) {
  const w = item.json;
  const nodes = w.nodes || [];
  const trig = nodes.find(n => /trigger|webhook/i.test(n.type) && !/stickyNote/.test(n.type));
  let trigger = 'unknown';
  if (trig) {
    const t = trig.type.split('.').pop();
    if (t === 'webhook') trigger = `webhook ${trig.parameters?.httpMethod || 'POST'} /${trig.parameters?.path || ''}`;
    else if (t === 'scheduleTrigger') trigger = `schedule ${trig.parameters?.rule?.interval?.[0]?.expression || ''}`;
    else if (t === 'chatTrigger') trigger = 'chat';
    else if (t === 'errorTrigger') trigger = 'error workflow';
    else if (t === 'executeWorkflowTrigger') trigger = 'called by another workflow';
    else trigger = t;
  }
  const notes = nodes.filter(n => n.type === 'n8n-nodes-base.stickyNote').map(n => n.parameters?.content || '').join(' ');
  const nodeNames = nodes.filter(n => n.type !== 'n8n-nodes-base.stickyNote').map(n => n.name).join(', ');
  const description = `${w.name}. Trigger: ${trigger}. ${notes.replace(/[#*`]/g, '')} Nodes: ${nodeNames}.`.replace(/\s+/g, ' ').trim();
  out.push({ json: { id: w.id, name: w.name, description, trigger,
                     nodeCount: nodes.filter(n => n.type !== 'n8n-nodes-base.stickyNote').length,
                     active: !!w.active, vector: JSON.stringify(embed(description)) } });
}
return out;
"""}),
    pg_query("Upsert into workflow_index", [1100, 300],
             "INSERT INTO workflow_index (id, name, description, trigger, node_count, active, embedding, indexed_at)\nVALUES ($1, $2, $3, $4, $5, $6, $7::vector, now())\nON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, trigger = EXCLUDED.trigger,\n  node_count = EXCLUDED.node_count, active = EXCLUDED.active, embedding = EXCLUDED.embedding, indexed_at = now()\nRETURNING id, name;",
             "={{ [$json.id, $json.name, $json.description, $json.trigger, $json.nodeCount, $json.active, $json.vector] }}"),
    node("Summary", "n8n-nodes-base.code", 2, [1320, 300], {"jsCode": r"""
const rows = $input.all().map(i => i.json);
return [{ json: { indexed: rows.length, workflows: rows.map(r => r.name) } }];
"""}),
]
c = {
    "Nightly 02:00": {"main": [[L("Config")]]},
    "Run now (manual)": {"main": [[L("Config")]]},
    "Config": {"main": [[L("GET /api/v1/workflows (n8n public API)")]]},
    "GET /api/v1/workflows (n8n public API)": {"main": [[L("One item per workflow")]]},
    "One item per workflow": {"main": [[L("Describe + embed")]]},
    "Describe + embed": {"main": [[L("Upsert into workflow_index")]]},
    "Upsert into workflow_index": {"main": [[L("Summary")]]},
}
dump("08-index-workflows-to-postgres.json", wf("08", "08 Index workflows into Postgres (pgvector)", n, c))

# ───────────────────────── 07 lookup (sub-workflow) ─────────────────────────
n = [
    sticky("## Find the closest workflow (sub-workflow)\nCalled by workflow 06 with `{ question }`. Embeds the question the same way 08 embedded the descriptions, asks Postgres for the nearest vectors, and returns the best match with its cosine similarity (1 = identical meaning, 0 = unrelated).\n\n`embedding <=> $1` is pgvector's cosine distance; similarity = 1 - distance.", [0, 40], 600, 170),
    node("Called by another workflow", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [0, 300], {"inputSource": "passthrough"}),
    node("Embed the question", "n8n-nodes-base.code", 2, [220, 300], {"jsCode": EMBED_JS + r"""
const q = $input.first().json.question || $input.first().json.chatInput || '';
return [{ json: { question: q, vector: JSON.stringify(embed(q)) } }];
"""}),
    pg_query("Nearest 3 by cosine distance", [440, 300],
             "SELECT id, name, trigger, node_count, active, description,\n       1 - (embedding <=> $1::vector) AS similarity\nFROM workflow_index\nORDER BY embedding <=> $1::vector\nLIMIT 3;",
             "={{ [$json.vector] }}"),
    node("Shape the answer", "n8n-nodes-base.code", 2, [660, 300], {"jsCode": r"""
const rows = $input.all().map(i => i.json);
const q = $('Embed the question').first().json.question;
if (!rows.length) return [{ json: { question: q, found: false, answer: 'The workflow index is empty. Run workflow 08 first.' } }];
const best = rows[0];
const pct = (x) => (Number(x) * 100).toFixed(0) + '%';
const lines = [
  `Closest match: ${best.name}  (similarity ${Number(best.similarity).toFixed(3)}, ${pct(best.similarity)})`,
  `Trigger: ${best.trigger}. ${best.node_count} nodes. ${best.active ? 'Active.' : 'Inactive.'}`,
  ``,
  best.description.replace(/^.*?Trigger: [^.]*\. /, ''),
];
if (rows.length > 1) {
  lines.push(``, `Also close: ` + rows.slice(1).map(r => `${r.name} (${Number(r.similarity).toFixed(3)})`).join('; '));
}
return [{ json: { question: q, found: true, answer: lines.join('\n'),
                  matchedWorkflowId: best.id, matchedName: best.name, similarity: Number(best.similarity),
                  candidates: rows.map(r => ({ id: r.id, name: r.name, similarity: Number(r.similarity) })) } }];
"""}),
]
# With an empty index the SELECT returns no rows; keep the chain alive so the
# "index is empty, run 08" answer still reaches the chat.
[x for x in n if x["name"] == "Nearest 3 by cosine distance"][0]["alwaysOutputData"] = True
c = {
    "Called by another workflow": {"main": [[L("Embed the question")]]},
    "Embed the question": {"main": [[L("Nearest 3 by cosine distance")]]},
    "Nearest 3 by cosine distance": {"main": [[L("Shape the answer")]]},
}
dump("07-lookup-workflow-subworkflow.json", wf("07", "07 Lookup: nearest workflow by cosine similarity (sub-workflow)", n, c))

# ───────────────────────── 06 chatbot ─────────────────────────
n = [
    sticky("## Chatbot: ask which workflow does X\nThe Chat Trigger gives you a hosted chat page. Each message is handed to workflow 07 (Execute Workflow = one workflow calling another and waiting for the result). The answer is logged to Postgres, then sent back to the chat.\n\nThe Chat Trigger in 'last node' mode needs the final node to output `{ output: text }`; that is what the Reply node does.", [0, 40], 600, 170),
    node("When chat message received", "@n8n/n8n-nodes-langchain.chatTrigger", 1.1, [0, 300],
         {"public": True, "mode": "hostedChat", "initialMessages": "Ask me which workflow handles something, e.g. \"what happens when a call is missed?\" or \"how do follow-ups work?\"",
          "options": {"responseMode": "lastNode", "title": "Workflow helper", "subtitle": "Backed by n8n workflow 07 and Postgres/pgvector"}}),
    node("Ask workflow 07 (sub-workflow)", "n8n-nodes-base.executeWorkflow", 1.2, [220, 300],
         {"workflowId": {"__rl": True, "mode": "id", "value": IDS["07"]}, "options": {}}),
    pg_query("Log to chat_log", [440, 300],
             "INSERT INTO chat_log (session_id, question, answer, matched_workflow_id, similarity)\nVALUES ($1, $2, $3, $4, $5)\nRETURNING id, asked_at;",
             "={{ [$('When chat message received').item.json.sessionId, $('When chat message received').item.json.chatInput, $json.answer, $json.matchedWorkflowId || null, $json.similarity ?? null] }}",
             on_error="continueRegularOutput"),
    node("Reply", "n8n-nodes-base.code", 2, [660, 300], {"jsCode": r"""
const a = $('Ask workflow 07 (sub-workflow)').first().json;
const log = $input.first().json;
return [{ json: { output: a.answer + (log.id ? `\n\n(logged as chat_log #${log.id})` : '') } }];
"""}),
]
# The Reply node must run even if the INSERT returns nothing or fails, or the chat
# widget gets "No item to return": a node with zero input items never executes.
[x for x in n if x["name"] == "Log to chat_log"][0]["alwaysOutputData"] = True
c = {
    "When chat message received": {"main": [[L("Ask workflow 07 (sub-workflow)")]]},
    "Ask workflow 07 (sub-workflow)": {"main": [[L("Log to chat_log")]]},
    "Log to chat_log": {"main": [[L("Reply")]]},
}
dump("06-chatbot-workflow-helper.json", wf("06", "06 Chatbot: ask which workflow does what", n, c))

# ───────────────────────── 09 support ticket triage (structured output) ─────────────────────────
# The one-webhook demo: POST a support ticket, an LLM returns a fixed JSON shape
# (category, priority, sentiment, summary, suggested reply), the webhook answers
# with it. Structured output is forced by giving the model exactly one tool with a
# JSON schema and requiring it to call that tool.
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["billing", "login", "bug", "feature_request", "cancellation", "other"]},
        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
        "sentiment": {"type": "string", "enum": ["angry", "frustrated", "neutral", "happy"]},
        "summary": {"type": "string", "description": "One sentence, third person."},
        "key_issues": {"type": "array", "items": {"type": "string"}},
        "requires_human": {"type": "boolean", "description": "true if money, legal threat, or churn risk is involved"},
        "suggested_reply": {"type": "string", "description": "A short, calm reply to send the customer."},
    },
    "required": ["category", "priority", "sentiment", "summary", "key_issues", "requires_human", "suggested_reply"],
}
n = [
    sticky("## Support ticket triage (structured output)\nPOST a ticket to the production webhook:\n\n```\ncurl -X POST http://localhost:5678/webhook/ticket-triage \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"ticket\": \"I was charged twice this month and your app keeps logging me out. Fix this or I am cancelling.\"}'\n```\n\nThe model is forced to answer through one tool with a JSON schema, so the shape is guaranteed. Opening the URL in a browser is a GET and returns 404 on purpose: the node only accepts POST.", [0, 0], 620, 260),
    node("Webhook: POST /ticket-triage", "n8n-nodes-base.webhook", 2, [0, 400],
         {"httpMethod": "POST", "path": "ticket-triage", "responseMode": "responseNode", "options": {}}),
    config_node([220, 400], keys=["anthropicBase", "triageModel"]),
    IF("Has a ticket?", [440, 400], [cond("t", "={{ $json.body.ticket }}", "notEmpty", single=True)]),
    node("Respond 400", "n8n-nodes-base.respondToWebhook", 1.1, [660, 560],
         {"respondWith": "json", "responseBody": "={{ { ok: false, error: 'send JSON like {\"ticket\": \"...\"}' } }}", "options": {"responseCode": 400}}),
    node("Build the model request", "n8n-nodes-base.code", 2, [660, 300], {"jsCode": r"""
// Build the whole API request here rather than inside an expression: a JSON
// schema contains "}}" which n8n would read as the end of an expression.
const cfg = $('Config').first().json;
const ticket = $('Webhook: POST /ticket-triage').first().json.body.ticket;
const schema = """ + json.dumps(json.dumps(TRIAGE_SCHEMA)) + r""";
return [{ json: { request: {
  model: cfg.triageModel,
  max_tokens: 600,
  system: 'You triage customer support tickets for a small software company. Be accurate and brief.',
  messages: [{ role: 'user', content: ticket }],
  tools: [{ name: 'triage_ticket', description: 'Record the triage of one support ticket.', input_schema: JSON.parse(schema) }],
  tool_choice: { type: 'tool', name: 'triage_ticket' },
}}}];
"""}),
    http("Claude: triage (structured output)", [880, 300], "POST", "={{ " + C("anthropicBase") + " }}/v1/messages",
         body="={{ JSON.stringify($json.request) }}",
         cred=("httpHeaderAuth", "Anthropic API key"), headers={"anthropic-version": "2023-06-01"}),
    node("Parse triage JSON", "n8n-nodes-base.code", 2, [1100, 300], {"jsCode": r"""
// The model answered by "calling" our tool; its arguments are the structured triage.
const r = $input.first().json;
const call = (r.content || []).find(b => b.type === 'tool_use');
if (!call) throw new Error('model did not return a tool call: ' + JSON.stringify(r).slice(0, 300));
return [{ json: {
  ok: true,
  ticket: $('Webhook: POST /ticket-triage').first().json.body.ticket,
  triage: call.input,
  model: r.model,
  usage: { input_tokens: r.usage?.input_tokens, output_tokens: r.usage?.output_tokens },
}}];
"""}),
    node("Respond to Webhook", "n8n-nodes-base.respondToWebhook", 1.1, [1320, 300],
         {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
]
c = {
    "Webhook: POST /ticket-triage": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Has a ticket?")]]},
    "Has a ticket?": {"main": [[L("Build the model request")], [L("Respond 400")]]},
    "Build the model request": {"main": [[L("Claude: triage (structured output)")]]},
    "Claude: triage (structured output)": {"main": [[L("Parse triage JSON")]]},
    "Parse triage JSON": {"main": [[L("Respond to Webhook")]]},
}
dump("09-support-ticket-triage.json", wf("09", "09 Support ticket triage (structured output)", n, c))

# ───────────────────────── 10 ingest PDFs into Postgres ─────────────────────────
n = [
    sticky("## Index the PDFs\nReads every PDF in the docs folder, pulls the text out, splits it into chunks of about 1,200 characters, and upserts each chunk into `docs`. Postgres keeps a full-text index on the chunk text, so workflow 11 can search it with SQL and no AI.\n\nRun it again after dropping a new PDF in the folder. Re-runs update in place.", [0, 40], 600, 170),
    node("Run now (manual)", "n8n-nodes-base.manualTrigger", 1, [0, 300], {}),
    node("Nightly 02:30", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 480],
         {"rule": {"interval": [{"field": "cronExpression", "expression": "30 2 * * *"}]}}),
    config_node([220, 300], keys=["docsDir"]),
    node("Read every PDF in the folder", "n8n-nodes-base.readWriteFile", 1.1, [440, 300],
         {"fileSelector": "={{ $json.docsDir }}/*.pdf", "options": {}}),
    node("Name the file", "n8n-nodes-base.code", 2, [660, 300], {"jsCode": r"""
// Extract from File drops the binary, so remember the file name in json first.
return $input.all().map(i => ({ json: { fileName: i.binary.data.fileName }, binary: i.binary }));
"""}),
    node("Extract text from PDF", "n8n-nodes-base.extractFromFile", 1.1, [880, 300],
         {"operation": "pdf", "options": {}}),
    node("Split into chunks", "n8n-nodes-base.code", 2, [1100, 300], {"jsCode": r"""
// One item per chunk. ~1,200 characters, cut at a sentence or line break when possible.
const out = [];
const items = $input.all();
const names = $('Name the file').all().map(i => i.json.fileName);
for (let k = 0; k < items.length; k++) {
  const item = items[k];
  const name = names[k] || item.json.fileName || 'unknown.pdf';
  const text = String(item.json.text || '').replace(/\r/g, '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  const chunks = [];
  let i = 0;
  while (i < text.length) {
    let end = Math.min(i + 1200, text.length);
    if (end < text.length) {
      const cut = Math.max(text.lastIndexOf('\n\n', end), text.lastIndexOf('. ', end));
      if (cut > i + 400) end = cut + 1;
    }
    chunks.push(text.slice(i, end).trim());
    i = end;
  }
  chunks.forEach((c, n) => out.push({ json: { name, chunk_no: n + 1, n_chunks: chunks.length, content: c, pages: item.json.numpages } }));
}
return out;
"""}),
    pg_query("Upsert chunk into docs", [1320, 300],
             "INSERT INTO docs (name, chunk_no, n_chunks, content, indexed_at)\nVALUES ($1, $2, $3, $4, now())\nON CONFLICT (name, chunk_no) DO UPDATE SET n_chunks = EXCLUDED.n_chunks, content = EXCLUDED.content, indexed_at = now()\nRETURNING name, chunk_no;",
             "={{ [$json.name, $json.chunk_no, $json.n_chunks, $json.content] }}"),
    node("Summary", "n8n-nodes-base.code", 2, [1540, 300], {"jsCode": r"""
const rows = $input.all().map(i => i.json);
const byDoc = {};
for (const r of rows) byDoc[r.name] = (byDoc[r.name] || 0) + 1;
return [{ json: { chunks: rows.length, documents: byDoc } }];
"""}),
]
c = {
    "Run now (manual)": {"main": [[L("Config")]]},
    "Nightly 02:30": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Read every PDF in the folder")]]},
    "Read every PDF in the folder": {"main": [[L("Name the file")]]},
    "Name the file": {"main": [[L("Extract text from PDF")]]},
    "Extract text from PDF": {"main": [[L("Split into chunks")]]},
    "Split into chunks": {"main": [[L("Upsert chunk into docs")]]},
    "Upsert chunk into docs": {"main": [[L("Summary")]]},
}
dump("10-docs-ingest-pdfs.json", wf("10", "10 Docs: index PDFs into Postgres full-text search", n, c))

# ───────────────────────── 11 deterministic search API ─────────────────────────
KEYWORD_SQL = """WITH q AS (SELECT websearch_to_tsquery('english', $1) AS tsq)
SELECT d.name, d.chunk_no, d.n_chunks,
       ts_rank_cd(d.tsv, q.tsq) AS rank,
       ts_headline('english', d.content, q.tsq,
         'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MinWords=6, MaxWords=26, FragmentDelimiter= … ') AS snippet
FROM docs d, q
WHERE d.tsv @@ q.tsq
ORDER BY rank DESC, d.name, d.chunk_no
LIMIT 20;"""
EXACT_SQL = """SELECT name, chunk_no, n_chunks, NULL::real AS rank,
       substr(content, GREATEST(1, position(lower($1) in lower(content)) - 110), 260) AS snippet
FROM docs
WHERE content ILIKE '%' || $1 || '%'
ORDER BY name, chunk_no
LIMIT 20;"""
n = [
    sticky("## Deterministic search\nPOST `{ \"q\": \"sticky sessions\", \"mode\": \"keyword\" | \"exact\" }`.\n\nKeyword mode: Postgres full-text search. `websearch_to_tsquery` understands quotes and minus, `ts_rank_cd` orders, `ts_headline` builds the highlighted snippet.\nExact mode: `ILIKE '%phrase%'`, the words in that order, case-insensitive.\n\nNo model, no randomness: the same input always returns the same rows.", [0, 40], 600, 190),
    node("Webhook: POST /docs/search", "n8n-nodes-base.webhook", 2, [0, 340],
         {"httpMethod": "POST", "path": "docs/search", "responseMode": "responseNode", "options": {}}),
    node("Validate", "n8n-nodes-base.code", 2, [220, 340], {"jsCode": r"""
const b = $input.first().json.body || {};
const q = String(b.q || '').trim().slice(0, 200);
const mode = b.mode === 'exact' ? 'exact' : 'keyword';
if (!q) throw new Error('q is required');
return [{ json: { q, mode } }];
"""}),
    IF("Exact phrase?", [440, 340], [cond("m", "={{ $json.mode }}", "equals", "exact")]),
    pg_query("Exact: ILIKE", [660, 240], EXACT_SQL, "={{ [$json.q] }}"),
    pg_query("Keyword: full-text search", [660, 440], KEYWORD_SQL, "={{ [$json.q] }}"),
    node("Shape results", "n8n-nodes-base.code", 2, [880, 340], {"jsCode": r"""
const v = $('Validate').first().json;
const rows = $input.all().map(i => i.json).filter(r => r.name);
const docs = new Set(rows.map(r => r.name)).size;
return [{ json: { q: v.q, mode: v.mode, docs, results: rows,
  sql: v.mode === 'exact' ? "content ILIKE '%' || $1 || '%'" : "tsv @@ websearch_to_tsquery('english', $1) ORDER BY ts_rank_cd" } }];
"""}),
    node("Respond JSON", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 340],
         {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}}),
]
for x in n:
    if x["name"] in ("Exact: ILIKE", "Keyword: full-text search"):
        x["alwaysOutputData"] = True     # zero hits must still reach "Shape results"
c = {
    "Webhook: POST /docs/search": {"main": [[L("Validate")]]},
    "Validate": {"main": [[L("Exact phrase?")]]},
    "Exact phrase?": {"main": [[L("Exact: ILIKE")], [L("Keyword: full-text search")]]},
    "Exact: ILIKE": {"main": [[L("Shape results")]]},
    "Keyword: full-text search": {"main": [[L("Shape results")]]},
    "Shape results": {"main": [[L("Respond JSON")]]},
}
dump("11-docs-search-api.json", wf("11", "11 Docs: deterministic search API (Postgres full-text)", n, c))

# ───────────────────────── 12 serve a PDF ─────────────────────────
# n8n adds "Content-Security-Policy: sandbox ..." to every webhook response unless the
# workflow sets that header itself. The sandbox blocks the browser's PDF viewer and
# would also sandbox the HTML page, so 12 and 13 set their own CSP.
n = [
    sticky("## Serve a PDF\n`GET /docs/file?name=how-this-works.pdf`\n\nThe name must be a plain file name (no slashes) and must exist in the index. Then the file is read from the docs folder and returned as `application/pdf`, inline, so the browser shows the whole document.", [0, 40], 560, 150),
    node("Webhook: GET /docs/file", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "GET", "path": "docs/file", "responseMode": "responseNode", "options": {}}),
    config_node([220, 300], keys=["docsDir"]),
    node("Check the name", "n8n-nodes-base.code", 2, [440, 300], {"jsCode": r"""
const name = String($input.first().json.query?.name || '');
const ok = /^[A-Za-z0-9._ -]+\.pdf$/.test(name) && !name.includes('..');
return [{ json: { name, ok, path: $('Config').first().json.docsDir + '/' + name } }];
"""}),
    pg_query("Is it in the index?", [660, 300], "SELECT count(*)::int AS n FROM docs WHERE name = $1;", "={{ [$json.name] }}"),
    IF("Known file?", [880, 300], [
        cond("ok", "={{ $('Check the name').item.json.ok }}", "true", typ="boolean", single=True),
        cond("n", "={{ $json.n }}", "gt", 0, typ="number")]),
    node("Read the PDF", "n8n-nodes-base.readWriteFile", 1.1, [1100, 200],
         {"fileSelector": "={{ $('Check the name').item.json.path }}", "options": {}}),
    node("Respond with the PDF", "n8n-nodes-base.respondToWebhook", 1.1, [1320, 200],
         {"respondWith": "binary", "responseDataSource": "automatically",
          "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "application/pdf"}, {"name": "Content-Disposition", "value": "inline"}, {"name": "Content-Security-Policy", "value": "frame-ancestors 'self'"}]}}}),
    node("Respond 404", "n8n-nodes-base.respondToWebhook", 1.1, [1100, 440],
         {"respondWith": "json", "responseBody": "={{ { error: 'no such document in the index' } }}", "options": {"responseCode": 404}}),
]
c = {
    "Webhook: GET /docs/file": {"main": [[L("Config")]]},
    "Config": {"main": [[L("Check the name")]]},
    "Check the name": {"main": [[L("Is it in the index?")]]},
    "Is it in the index?": {"main": [[L("Known file?")]]},
    "Known file?": {"main": [[L("Read the PDF")], [L("Respond 404")]]},
    "Read the PDF": {"main": [[L("Respond with the PDF")]]},
}
dump("12-docs-serve-pdf.json", wf("12", "12 Docs: serve a PDF from the folder", n, c))

# ───────────────────────── 13 the HTML page ─────────────────────────
APP_HTML = (pathlib.Path(__file__).resolve().parent / "app.html").read_text()
chat_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "n8n-workflows/When chat message received"))
APP_HTML = APP_HTML.replace("CHAT_WEBHOOK_ID", chat_id)
n = [
    sticky("## The web page\n`GET /webhook/app` returns an HTML page. Its buttons call the other webhooks on this instance: /docs/search, /docs/file, /ticket-triage, and the chat trigger.\n\nThe HTML lives in the Respond node as a plain string (not an expression), so n8n serves it as-is with `Content-Type: text/html`.", [0, 40], 560, 160),
    node("Webhook: GET /app", "n8n-nodes-base.webhook", 2, [0, 300],
         {"httpMethod": "GET", "path": "app", "responseMode": "responseNode", "options": {}}),
    node("Respond with HTML", "n8n-nodes-base.respondToWebhook", 1.1, [220, 300],
         {"respondWith": "text", "responseBody": APP_HTML,
          "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}, {"name": "Content-Security-Policy", "value": "default-src 'self' 'unsafe-inline' data: blob: https://cdnjs.cloudflare.com; worker-src 'self' blob: https://cdnjs.cloudflare.com; frame-ancestors 'self'"}]}}}),
]
c = {"Webhook: GET /app": {"main": [[L("Respond with HTML")]]}}
dump("13-app-page.json", wf("13", "13 App: the HTML page (served by a webhook)", n, c))
