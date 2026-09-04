#!/usr/bin/env node
// Stand-ins for the three outside services the workflows talk to, so the whole
// thing runs on a laptop with no accounts. Each one answers the way the real
// API does for the fields the workflows use, and prints every request it gets.
//
//   http://localhost:4010/vapi     -> api.vapi.ai
//   http://localhost:4010/ghl      -> services.leadconnectorhq.com (GoHighLevel)
//   http://localhost:4010/twilio   -> api.twilio.com
//   http://localhost:4010/log      -> a call-log endpoint
//
// GET /_requests returns everything received, so demo.sh can print a summary.

import http from "node:http";

const PORT = Number(process.env.MOCK_PORT || 4010);
const received = [];

// Contacts the follow-up cron will find: Dana and Sam still to chase, Luis already
// booked, Priya at the attempt cap. (The demo books Dana before the cron runs.)
const contacts = [
  { id: "c_101", firstName: "Dana", phone: "+15555550101", tags: ["ai-no-answer", "ai-attempt-1"], dateAdded: new Date(Date.now() - 1 * 864e5).toISOString() },
  { id: "c_102", firstName: "Luis", phone: "+15555550102", tags: ["ai-no-answer", "ai-booked"], dateAdded: new Date(Date.now() - 2 * 864e5).toISOString() },
  { id: "c_103", firstName: "Priya", phone: "+15555550103", tags: ["ai-no-answer", "ai-attempt-4"], dateAdded: new Date(Date.now() - 3 * 864e5).toISOString() },
  { id: "c_104", firstName: "Sam", phone: "+15555550104", tags: ["ai-no-answer", "ai-attempt-2"], dateAdded: new Date(Date.now() - 2 * 864e5).toISOString() },
];

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
  });
}

function send(res, code, obj) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const raw = await readBody(req);
  let body = raw;
  try { body = JSON.parse(raw); } catch { /* form-encoded or empty */ }
  const auth = req.headers.authorization || "";
  const entry = { at: new Date().toISOString(), method: req.method, path: url.pathname, query: Object.fromEntries(url.searchParams), auth: auth ? auth.slice(0, 12) + "…" : "(none)", body };

  if (url.pathname === "/_requests") return send(res, 200, received);
  if (url.pathname === "/_reset") { received.length = 0; return send(res, 200, { ok: true }); }

  received.push(entry);
  console.log(`${entry.method} ${entry.path}  auth=${entry.auth}  ${typeof body === "string" ? body.slice(0, 80) : JSON.stringify(body).slice(0, 120)}`);

  // Every real API rejects a missing token. So do we.
  if (!auth && url.pathname.startsWith("/vapi") || !auth && url.pathname.startsWith("/ghl") || !auth && url.pathname.startsWith("/twilio")) {
    return send(res, 401, { error: "missing credentials" });
  }

  // ---- Vapi ----
  if (req.method === "POST" && url.pathname === "/vapi/call") {
    const number = body?.customer?.number || "";
    if (number.endsWith("0000")) return send(res, 500, { error: "simulated Vapi outage" }); // used to demo the error workflow
    return send(res, 201, { id: "call_" + Math.random().toString(36).slice(2, 10), status: "queued", customer: body.customer });
  }

  // ---- GoHighLevel ----
  if (req.method === "GET" && url.pathname === "/ghl/contacts/") {
    const q = url.searchParams.get("query") || "";
    return send(res, 200, { contacts: contacts.filter((c) => !q || c.tags.includes(q)), meta: { total: contacts.length } });
  }
  let m = url.pathname.match(/^\/ghl\/contacts\/([^/]+)\/tags$/);
  if (req.method === "POST" && m) {
    const c = contacts.find((x) => x.id === m[1]);
    if (c) for (const t of body.tags || []) if (!c.tags.includes(t)) c.tags.push(t);
    return send(res, 200, { tags: c ? c.tags : body.tags });
  }
  m = url.pathname.match(/^\/ghl\/contacts\/([^/]+)\/notes$/);
  if (req.method === "POST" && m) return send(res, 200, { note: { id: "note_" + Date.now(), contactId: m[1], body: body.body } });

  // ---- Twilio ----
  m = url.pathname.match(/^\/twilio\/2010-04-01\/Accounts\/([^/]+)\/Messages\.json$/);
  if (req.method === "POST" && m) {
    const form = Object.fromEntries(new URLSearchParams(raw));
    return send(res, 201, { sid: "SM" + Math.random().toString(36).slice(2, 12), from: form.From, to: form.To, body: form.Body, status: "queued" });
  }

  // ---- generic log endpoint ----
  if (req.method === "POST" && url.pathname.startsWith("/log/")) return send(res, 200, { logged: true });

  send(res, 404, { error: "no mock for " + req.method + " " + url.pathname });
});

server.listen(PORT, () => console.log(`mock APIs listening on http://localhost:${PORT}  (vapi, ghl, twilio, log)`));
