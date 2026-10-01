// Bundle data/x402_index/*.csv|json and the method note's key sections into src/data.json for the Worker.
// Run before every deploy (npm run build:data). The Worker never reads the filesystem at runtime.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const DATA = join(ROOT, "data", "x402_index");

function csv(name, dir = DATA) {
  const [head, ...lines] = readFileSync(join(dir, name), "utf8").trim().split(/\r?\n/);
  const cols = head.split(",");
  return lines.map((line) => {
    const vals = []; let cur = "", q = false;
    for (const ch of line) {
      if (ch === '"') q = !q; else if (ch === "," && !q) { vals.push(cur); cur = ""; } else cur += ch;
    }
    vals.push(cur);
    return Object.fromEntries(cols.map((c, i) => [c, vals[i] !== "" && !isNaN(+vals[i]) && !/^0x/.test(vals[i]) ? +vals[i] : vals[i]]));
  });
}

const head = JSON.parse(readFileSync(join(DATA, "headline.json"), "utf8"));
const methodDoc = readFileSync(join(ROOT, "docs", "X402_INDEX_METHOD.md"), "utf8");
const method = {};
for (const part of methodDoc.split("\n## ").slice(1)) {
  const [title, ...body] = part.split("\n");
  if (/^[1236]\./.test(title)) method[title.trim()] = body.join("\n").trim();
}
const payees = csv("payees_weekly.csv");
const lastWeek = payees.reduce((m, r) => (r.week_start > m ? r.week_start : m), "");
const out = {
  built_at: new Date().toISOString(),
  latest: Object.fromEntries(Object.entries(head).filter(([k]) =>
    ["latest_week", "weeks_available", "raw_usd", "raw_payments", "d05_usd", "clean_usd", "clean_payments", "clean_payees",
     "clean_by_category_usd", "tripwire_content_plus_data_clean_usd", "tripwire_4week_growth", "tripwire_4week_base_week",
     "tripwire_loglinear_monthly_growth_last_5_weeks"].includes(k))),
  method: { source: "https://github.com/doescodinggiteasier/wknipe-site/blob/main/docs/X402_INDEX_METHOD.md", ...method },
  weekly: csv("weekly.csv"),
  prices: csv("prices_weekly.csv"),
  sellers: payees.filter((r) => r.week_start === lastWeek).sort((a, b) => b.usd - a.usd).slice(0, 200),
  // ORDER_014: per-seller full weekly history for the paid GET /v1/seller?address=
  payee_history: payees.reduce((m, r) => { const { payee, ...rest } = r; (m[String(payee).toLowerCase()] ??= []).push(rest); return m; }, {}),
};
// ORDER_013: free chart series, one per chart on wknipe.com (GET /v1/series?metric=NAME). Missing files are skipped.
const METRICS = {
  waterfall: ["x402_market", "waterfall.csv", "Raw -> clean: USD and payments each filter removes, per week"],
  buyer_threshold_sensitivity: ["x402_market", "buyer_threshold_sensitivity.csv", "Clean USD per week if sellers needed 1 / 2 (published) / 3 / 5 genuine buyers"],
  category_mix: ["x402_market", "category_mix.csv", "Demand-cleaned payments, USD, sellers and buyers per category per week"],
  concentration: ["x402_market", "concentration.csv", "Top-1 / top-10 seller share, HHI and effective sellers per category per week"],
  buyers_weekly: ["x402_market", "buyers_weekly.csv", "Active genuine buyers per week: new, returning, reactivated, median spend, multi-homing"],
  retention: ["x402_market", "retention.csv", "Share of each week's new buyers who buy again 1-4 weeks later"],
  buyer_spend_histogram: ["x402_market", "buyer_spend_histogram.csv", "Buyers by weekly clean spend (log bins)"],
  sellers_per_buyer: ["x402_market", "sellers_per_buyer.csv", "Buyers by number of distinct sellers paid in the week"],
  buyer_tiers: ["x402_market", "buyer_tiers.csv", "Buyer size tiers: buyers, USD and USD by category"],
  tickets: ["x402_market", "tickets.csv", "Clean payment size p10 / median / p90 per category per week"],
  ticket_histogram: ["x402_market", "ticket_histogram.csv", "Clean payments by size (log bins) per category per week"],
  facilitators: ["x402_market", "facilitators.csv", "Payments and USD per facilitator address, raw and clean, per week"],
  tripwire: ["x402_market", "tripwire.csv", "Content + data clean USD per week and the +20%/month reopen path"],
  movers: ["x402_market", "movers.csv", "Sellers with >= 5 buyers: entered, exited, continuing, USD change vs the previous week"],
  posted_by_category: ["x402_prices", "posted_by_category.csv", "Posted price p10 / median / p90 per listing category, latest Bazaar snapshot"],
  prices_weekly: ["x402_index", "prices_weekly.csv", "Chain-linked Jevons price index, posted and transacted"],
  weekly: ["x402_index", "weekly.csv", "Stage x category: payments, USD, sellers, buyers per week"],
  status_daily: ["x402_status", "status_daily.csv", "Endpoint monitor: share of checked listings answering a valid 402, per day"],
  access_weekly: ["ai_access", "access_weekly.csv", "Tranco top sites: share blocking each AI crawler and signal adoption, per run"],
};
out.metrics = {};
for (const [name, [dir, file, about]] of Object.entries(METRICS)) {
  try { out.metrics[name] = { about, source: `https://github.com/doescodinggiteasier/wknipe-site/blob/main/data/${dir}/${file}`, rows: csv(file, join(ROOT, "data", dir)) }; }
  catch { /* not built yet */ }
}
console.log("metrics:", Object.keys(out.metrics).join(", "));
writeFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "src", "data.json"), JSON.stringify(out));

// ORDER_014: routing table for the paid GET /v1/route (and the 3-result demo on wknipe.com/x402/buy/). Bazaar listings
// joined with the latest endpoint check and each seller's genuine buyers. It lives only inside the Worker: the site no
// longer ships it as a bulk file. Missing inputs leave an empty table (the route then answers 503).
const route = { built_at: out.built_at, snapshot: null, week: null, checked_on: null, sellers: [], rows: [] };
try {
  const L = JSON.parse(readFileSync(join(ROOT, "data", "x402_prices", "listings.json"), "utf8"));
  const ci = Object.fromEntries(L.cols.map((c, i) => [c, i]));
  const H = {};
  try {
    for (const r of csv("status_latest.csv", join(ROOT, "data", "x402_status"))) {
      const st = r.valid_402 !== "True" ? "failed" : r.price_match === "False" || r.payto_match === "False" ? "differs" : "verified";
      H[String(r.resource).replace(/^https:\/\//, "")] = [st, +r.latency_ms || null];
      route.checked_on = r.date;
    }
  } catch { /* no monitor data yet */ }
  Object.assign(route, { snapshot: L.snapshot, week: L.week, sellers: L.sellers.map((s) => [s[0], s[1], s[2], s[3] ? 1 : 0]) });
  route.rows = L.rows.map((r) => {
    const h = H[r[ci.host] + r[ci.path]];
    return [r[ci.host], r[ci.path], r[ci.name] || "", r[ci.what] || "", (r[ci.desc] || "").slice(0, 240), r[ci.price_usd], r[ci.price_network], r[ci.method], r[ci.seller], h ? h[0] : "unchecked", h ? h[1] : null, r[ci.category]];
  });
  route.idx = searchIndex(route.rows);
  for (const r of route.rows) r[4] = "";  // descriptions are indexed above but never returned, so they are not shipped
} catch (e) { console.log("route table: skipped (" + e.message + ")"); }
writeFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "src", "route.json"), JSON.stringify(route));
console.log(`src/route.json: ${route.rows.length} listings, ${route.sellers.length} sellers, checks ${route.checked_on}`);
console.log(`src/data.json: ${out.weekly.length} weekly rows, ${out.prices.length} price rows, ${out.sellers.length} sellers, latest ${out.latest.latest_week}`);

// ORDER_014 fix: the Worker's free plan allows ~10 ms CPU per request, and building a MiniSearch index at runtime took
// ~230 ms (Cloudflare error 1102 on cold isolates). So the inverted index is built here, once: for every token, the
// documents containing it and a precomputed BM25+ weight summed over fields with MiniSearch's boosts and parameters.
// Runtime search (src/route.ts) is then a binary search over sorted tokens plus a few array reads.
function searchIndex(rows) {
  const FIELDS = [[3, 3], [2, 2], [4, 1], [0, 1.2]]; // [column in route.rows, boost]: what, name, desc, host
  const K = 1.2, B = 0.7, D = 0.5, N = rows.length;
  const tok = (x) => String(x || "").toLowerCase().split(/[\n\r\p{Z}\p{P}]+/u).filter(Boolean);
  const df = FIELDS.map(() => new Map()), lens = FIELDS.map(() => []), tfs = [];
  rows.forEach((r, id) => {
    tfs[id] = FIELDS.map(([col], f) => {
      const ts = tok(r[col]), tf = new Map();
      ts.forEach((t) => tf.set(t, (tf.get(t) || 0) + 1));
      tf.forEach((_, t) => df[f].set(t, (df[f].get(t) || 0) + 1));
      lens[f][id] = ts.length;
      return tf;
    });
  });
  const avg = lens.map((l) => l.reduce((a, b) => a + b, 0) / N || 1);
  const post = new Map();
  rows.forEach((_, id) => FIELDS.forEach(([, boost], f) => tfs[id][f].forEach((tf, t) => {
    const n = df[f].get(t), idf = Math.log(1 + (N - n + 0.5) / (n + 0.5));
    const w = boost * idf * (D + (tf * (K + 1)) / (tf + K * (1 - B + (B * lens[f][id]) / avg[f])));
    let p = post.get(t); if (!p) post.set(t, (p = new Map()));
    p.set(id, (p.get(id) || 0) + w);
  })));
  const tokens = [...post.keys()].sort();
  // postings as [id delta, weight x 100, ...]: ids ascend, so deltas are small and compress well
  return { tokens, post: tokens.map((t) => { let last = 0; return [...post.get(t)].flatMap(([id, w]) => { const d = id - last; last = id; return [d, Math.max(1, Math.round(w * 100))]; }); }) };
}
