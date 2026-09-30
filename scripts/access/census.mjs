// ORDER_013 Phase 4: State of AI access. Runs the AI-policy checker (apps/x402-index-api/src/check.ts, the same code as
// wknipe.com/check/) over the Tranco top-N domains, weekly.
//   node --experimental-strip-types scripts/access/census.mjs [--top 1000] [--concurrency 12]
// Politeness: the checker's identified UA (wknipe-policy-check/1.0 (+https://wknipe.com/check/)), 4-5 small GETs per
// domain (robots.txt, /.well-known/tdmrep.json, /llms.txt, /, and one RSL licence file if declared), 6 s timeouts,
// one domain at a time per host, no retries. Writes state/ai_access/run_<date>.json.gz (every result) and
// data/ai_access/{access_weekly.csv, access_latest.csv, access.json} via scripts/access/summarise.py.
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runCheck, normaliseDomain } from "../../apps/x402-index-api/src/check.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const STATE = process.env.X402_STATE ? join(ROOT, process.env.X402_STATE) : join(ROOT, "local");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const TOP = +arg("--top", 1000), CONC = +arg("--concurrency", 12);
const UA = "wknipe-access-census/1.0 (+https://wknipe.com/access/)";

async function tranco() {
  const meta = await (await fetch("https://tranco-list.eu/api/lists/date/latest", { headers: { "User-Agent": UA } })).json();
  const csv = await (await fetch(`https://tranco-list.eu/download/${meta.list_id}/${TOP}`, { headers: { "User-Agent": UA } })).text();
  const domains = csv.trim().split(/\r?\n/).map((l) => l.split(",")[1]).filter(Boolean);
  return { list_id: meta.list_id, created_on: meta.created_on, domains };
}

const t0 = Date.now();
const list = await tranco();
console.log(`Tranco list ${list.list_id} (${list.created_on}): ${list.domains.length} domains`);
const out = new Array(list.domains.length);
let next = 0, done = 0, requests = 0;
async function worker() {
  while (next < list.domains.length) {
    const i = next++, raw = list.domains[i], d = normaliseDomain(raw);
    if (!d) { out[i] = { rank: i + 1, domain: raw, error: "not a checkable public domain" }; continue; }
    try {
      const r = await runCheck(d);
      requests += 4 + (r.rsl?.fetched ? 1 : 0);
      out[i] = { rank: i + 1, ...r };
    } catch (e) { out[i] = { rank: i + 1, domain: d, error: String(e?.message ?? e).slice(0, 120) }; requests += 4; }
    if (++done % 100 === 0) console.log(`${done}/${list.domains.length} (${Math.round((Date.now() - t0) / 1000)} s)`);
  }
}
await Promise.all(Array.from({ length: CONC }, worker));
const date = new Date().toISOString().slice(0, 10);
const dir = join(STATE, "ai_access");
mkdirSync(dir, { recursive: true });
const run = { date, tranco_list_id: list.list_id, tranco_created_on: list.created_on, top: TOP, user_agent: UA, checker_ua: "wknipe-policy-check/1.0 (+https://wknipe.com/check/)", requests_approx: requests, seconds: Math.round((Date.now() - t0) / 1000), results: out };
writeFileSync(join(dir, `run_${date}.json.gz`), gzipSync(JSON.stringify(run)));
console.log(`done: ${out.length} domains, ~${requests} requests, ${run.seconds} s -> ${join(dir, `run_${date}.json.gz`)}`);
