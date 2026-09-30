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
};
// ORDER_013: free chart series, one per chart on wknipe.com (GET /v1/series?metric=NAME). Missing files are skipped.
const METRICS = {
  waterfall: ["x402_market", "waterfall.csv", "Raw -> clean: USD and payments each filter removes, per week"],
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
  posted_vs_paid: ["x402_prices", "posted_vs_paid.csv", "Median posted price vs median clean payment per category"],
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
console.log(`src/data.json: ${out.weekly.length} weekly rows, ${out.prices.length} price rows, ${out.sellers.length} sellers, latest ${out.latest.latest_week}`);
