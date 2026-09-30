// ORDER_013: 20-query hand check of Price comps retrieval (keyword + category, same MiniSearch settings as comps.js).
// Prints the top 10 per query for a human to judge; the judged counts are recorded in data/x402_prices/recall_check.json.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const MiniSearch = require("../../site/assets/vendor/minisearch-7.min.js");
const L = JSON.parse(readFileSync(new URL("../../data/x402_prices/listings.json", import.meta.url)));
const ci = Object.fromEntries(L.cols.map((c, i) => [c, i]));
const rows = L.rows.map((r, id) => ({ id, host: r[ci.host], name: r[ci.name], what: r[ci.what] || "", desc: r[ci.desc], category: r[ci.category] }));
const ms = new MiniSearch({ fields: ["what", "name", "desc", "host"], storeFields: [], searchOptions: { boost: { what: 3, name: 2, host: 1.2 }, prefix: true, fuzzy: 0.2 } });
ms.addAll(rows);
const Q = ["token price lookup", "wallet balance", "scrape web page", "web search results", "news article", "image generation", "llm chat completion", "weather forecast",
  "company enrichment", "pdf to text", "text to speech", "translate text", "stock quote", "dex swap quote", "email verification", "sports scores", "academic paper search",
  "youtube transcript", "screenshot of website", "domain whois lookup"];
for (const q of Q) {
  const hits = ms.search(q).slice(0, 10);
  console.log(`\n## ${q} (${ms.search(q).length} matches)`);
  hits.forEach((h, i) => console.log(`${i + 1}. [${rows[h.id].category}] ${rows[h.id].what} — ${rows[h.id].host}`));
}
