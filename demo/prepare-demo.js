#!/usr/bin/env node
// Copies workflows/*.json into demo/out/build/ with the Config node pointed at
// the local mocks, and writes the credentials file the demo imports.
// The production JSON in workflows/ is never modified.
import fs from "node:fs";
import path from "node:path";

const SRC = "workflows";
const OUT = "demo/out/build";
fs.mkdirSync(path.join(OUT, "workflows"), { recursive: true });

const MOCK = "http://localhost:4010";
const overrides = {
  vapiBase: `${MOCK}/vapi`,
  ghlBase: `${MOCK}/ghl`,
  twilioBase: `${MOCK}/twilio`,
  logBase: `${MOCK}/log`,
  leadWebhookSecret: "demo-secret",
  vapiWebhookSecret: "demo-secret",
  twilioAccountSid: "ACdemo",
  ownerEmail: "owner@shop.test",
  oncallEmail: "maria@oncall.test",
  alertFrom: "n8n@demo.test",
  slackWebhookUrl: "",
  paceSeconds: 1,
  n8nBase: "http://localhost:5678",
};

for (const f of fs.readdirSync(SRC).filter((x) => x.endsWith(".json"))) {
  const w = JSON.parse(fs.readFileSync(path.join(SRC, f), "utf8"));
  const cfg = w.nodes.find((n) => n.name === "Config");
  let changed = 0;
  for (const a of (cfg ? cfg.parameters.assignments.assignments : [])) {
    if (a.name in overrides) { a.value = overrides[a.name]; changed++; }
  }
  fs.writeFileSync(path.join(OUT, "workflows", f), JSON.stringify(w, null, 2));
  console.log(`${f}: ${changed} config values pointed at the mocks`);
}

// Plain-text credential data. `n8n import:credentials` encrypts it with the
// instance's N8N_ENCRYPTION_KEY on the way in; nothing here is a real secret.
const credentials = [
  { id: "mpCredVapi000001", name: "Vapi API key", type: "httpHeaderAuth", data: { name: "Authorization", value: "Bearer demo-vapi-key" } },
  { id: "mpCredGhl0000002", name: "GoHighLevel API token", type: "httpHeaderAuth", data: { name: "Authorization", value: "Bearer demo-ghl-token" } },
  { id: "mpCredTwilio0003", name: "Twilio (basic auth)", type: "httpBasicAuth", data: { user: "ACdemo", password: "demo-auth-token" } },
  { id: "mpCredSmtp000004", name: "SMTP (Resend)", type: "smtp", data: { user: "", password: "", host: "localhost", port: 2525, secure: false, disableStartTls: true, hostName: "" } },
  // The throwaway Postgres demo.sh starts on port 5433 (trust auth, no password).
  { id: "mpCredPg00000005", name: "Postgres (workflow index)", type: "postgres", data: { host: "localhost", port: 5433, database: "n8ndemo", user: "n8n", password: "", ssl: "disable", allowUnauthorizedCerts: false } },
  // Placeholder. demo.sh creates a real n8n API key after n8n starts and writes it into this credential.
  { id: "mpCredN8nApi0006", name: "n8n API key (self)", type: "httpHeaderAuth", data: { name: "X-N8N-API-KEY", value: "set-by-demo.sh" } },
];
fs.writeFileSync(path.join(OUT, "credentials.json"), JSON.stringify(credentials, null, 2));
console.log(`credentials.json: ${credentials.length} demo credentials`);
