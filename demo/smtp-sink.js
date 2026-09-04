#!/usr/bin/env node
// A throwaway SMTP server. The workflows' "Send Email" nodes point their SMTP
// credential here during the demo, so every alert and owner email lands in
// demo/out/mail/ as a .eml file and prints a one-line summary.
import { SMTPServer } from "smtp-server";
import fs from "node:fs";
import path from "node:path";

const PORT = Number(process.env.SMTP_PORT || 2525);
const OUT = path.resolve(process.env.MAIL_DIR || "demo/out/mail");
fs.mkdirSync(OUT, { recursive: true });
let n = 0;

const server = new SMTPServer({
  authOptional: true,
  disabledCommands: ["STARTTLS"],
  onData(stream, session, cb) {
    let raw = "";
    stream.on("data", (c) => (raw += c));
    stream.on("end", () => {
      n += 1;
      const subject = (raw.match(/^Subject: (.*)$/mi) || [])[1] || "(no subject)";
      const to = (raw.match(/^To: (.*)$/mi) || [])[1] || "";
      const file = path.join(OUT, `${String(n).padStart(2, "0")}.eml`);
      fs.writeFileSync(file, raw);
      console.log(`mail #${n}  to=${to}  subject=${subject}`);
      cb();
    });
  },
});

server.listen(PORT, () => console.log(`SMTP sink listening on localhost:${PORT}, saving to ${OUT}`));
