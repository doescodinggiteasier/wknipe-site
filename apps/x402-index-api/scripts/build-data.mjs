// Bundle data/x402_index/*.csv|json and the method note's key sections into src/data.json for the Worker.
// Run before every deploy (npm run build:data). The Worker never reads the filesystem at runtime.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const DATA = join(ROOT, "data", "x402_index");

function csv(name) {
  const [head, ...lines] = readFileSync(join(DATA, name), "utf8").trim().split("\n");
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
writeFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "src", "data.json"), JSON.stringify(out));
console.log(`src/data.json: ${out.weekly.length} weekly rows, ${out.prices.length} price rows, ${out.sellers.length} sellers, latest ${out.latest.latest_week}`);
