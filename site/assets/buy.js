/* Best execution (/x402/buy/): for a task an agent needs done, rank x402 listings by relevance, verified 402 health
   (our daily unpaid check), genuine buyers of the seller, and price. Data: /x402/data/listings.json, /x402/data/health.json. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const WK = window.WK, fmt = WK.fmt, esc = WK.esc;
  const $ = (s) => document.querySelector(s);
  const N = 40, MIN = 5, PER_SELLER = 3, REL_FLOOR = 0.35;
  const EX = ["web search", "scrape web page to markdown", "token price", "weather forecast", "llm chat completion", "company enrichment", "sec filings", "twitter search", "image generation", "news headlines"];
  const q = $("#buy-q"), max = $("#buy-max"), ver = $("#buy-verified"), status = $("#buy-status");
  let rows = [], ms = null, meta = null, H = {}, hday = null;

  $("#buy-examples").innerHTML = EX.map((e) => `<button type="button" class="chip" data-ex="${esc(e)}">${esc(e)}</button>`).join("");
  $("#buy-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-ex]"); if (b) { q.value = b.dataset.ex; run(); } });

  const STATE = {
    verified: ["verified", "ok", "Valid 402 at the listed price and payTo"],
    differs: ["answers, price differs", "gold", "Valid 402, but the live price or payTo differs from the listing"],
    failed: ["failed check", "bad", "No valid 402 on the last check"],
    unchecked: ["not checked yet", "", "Not in today's sample of the daily monitor"],
  };
  const health = (r) => {
    const h = H[r.host + r.path];
    if (!h) return "unchecked";
    if (h[0] === 0) return "failed";
    return h[1] === 0 || h[2] === 0 ? "differs" : "verified";
  };

  async function load() {
    await WK.load("/assets/vendor/minisearch-7.min.js");
    const [L, hj] = await Promise.all([WK.json("/x402/data/listings.json"), WK.json("/x402/data/health.json").catch(() => ({ h: {} }))]);
    meta = L; H = hj.h || {}; hday = hj.date;
    const ci = Object.fromEntries(L.cols.map((c, i) => [c, i]));
    rows = L.rows.map((r, id) => {
      const s = r[ci.seller] != null ? L.sellers[r[ci.seller]] : null;
      const o = { id, host: r[ci.host], path: r[ci.path], name: r[ci.name], what: r[ci.what] || "", category: r[ci.category], desc: r[ci.desc], price: r[ci.price_usd], net: r[ci.price_network], method: r[ci.method],
        seller: s ? s[0] : null, buyers: s ? s[1] : 0, paid: s ? s[2] : null, page: s ? s[3] : false };
      o.state = health(o); o.lat = H[o.host + o.path] ? H[o.host + o.path][3] : null;
      return o;
    });
    ms = new MiniSearch({ fields: ["what", "name", "desc", "host"], storeFields: [], searchOptions: { boost: { what: 3, name: 2, host: 1.2 }, prefix: true, fuzzy: 0.2 } });
    await ms.addAllAsync(rows, { chunkSize: 1000 });
    const nv = rows.filter((r) => r.state === "verified").length;
    status.textContent = `${rows.length.toLocaleString("en-US")} listings · ${nv.toLocaleString("en-US")} verified on ${hday || "–"}`;
    const u = new URLSearchParams(location.search);
    if (u.get("need")) q.value = u.get("need"); if (u.get("max")) max.value = u.get("max"); if (u.get("verified") === "1") ver.checked = true;
    if (q.value) run();
  }

  function ranked() {
    const text = q.value.trim(), cap = max.value ? +max.value : null;
    if (!text) return [];
    const per = new Map(), hits = [];
    const res = ms.search(text);
    const top = res.length ? res[0].score : 1;
    for (const h of res) {
      const r = rows[h.id];
      if (cap != null && !(r.price > 0 && r.price <= cap)) continue;
      if (ver.checked && r.state !== "verified") continue;
      const k = r.seller || r.host, n = per.get(k) || 0;
      if (n >= PER_SELLER) continue; per.set(k, n + 1);
      hits.push({ ...r, rel: h.score / top });
      if (hits.length >= N) break;
    }
    const priced = hits.filter((h) => h.price > 0).map((h) => Math.log10(h.price));
    const lo = Math.min(...priced), span = Math.max(0.5, Math.max(...priced) - lo);
    for (const h of hits) {
      const p = h.price > 0 ? 1 - (Math.log10(h.price) - lo) / span : 0;
      h.score = h.rel + (h.state === "verified" ? 0.35 : h.state === "differs" ? 0.1 : h.state === "failed" ? -0.6 : 0) + (h.buyers >= MIN ? 0.25 : h.buyers > 0 ? 0.08 : 0) + 0.2 * p;
    }
    return hits.sort((a, b) => b.score - a.score);
  }

  const pill = (s) => `<span class="pill ${STATE[s][1]}" title="${esc(STATE[s][2])}">${esc(STATE[s][0])}</span>`;
  const endpoint = (h) => `https://${h.host}${h.path}`;
  const pickCard = (kind, title, h, why) => h
    ? `<div class="pick ${kind}"><div class="pk">${esc(title)}</div><div class="pn">${h.page ? `<a href="/x402/sellers/${h.seller}">${esc(h.name || h.host)}</a>` : esc(h.name || h.host)}</div>
       <div class="pp">${h.price > 0 ? fmt.usdFull(h.price) : "unpriced"}<small> / call</small></div><div class="pw">${esc(h.what)}</div>
       <div class="pm">${pill(h.state)} ${h.buyers ? `<span class="pill">${fmt.int(h.buyers)} genuine buyers</span>` : ""}</div><code class="pu">${esc(endpoint(h))}</code><div class="why">${why}</div></div>`
    : `<div class="pick ${kind} none"><div class="pk">${esc(title)}</div><div class="pw">No match qualifies. ${kind === "value" ? `No relevant seller with ${MIN}+ genuine buyers passed the check.` : "Try a broader task."}</div></div>`;

  function run() {
    if (!ms) return;
    const u = new URL(location); q.value.trim() ? u.searchParams.set("need", q.value.trim()) : u.searchParams.delete("need");
    max.value ? u.searchParams.set("max", max.value) : u.searchParams.delete("max"); ver.checked ? u.searchParams.set("verified", "1") : u.searchParams.delete("verified");
    history.replaceState(null, "", u);
    const hits = ranked();
    $("#buy-out").hidden = !hits.length;
    if (!hits.length) { if (q.value.trim()) status.textContent = "No listing matches. Try fewer or more general words, or lift the price cap."; return; }
    status.textContent = `${hits.length} relevant listings from ${new Set(hits.map((h) => h.seller || h.host)).size} sellers`;
    const rel = hits.filter((h) => h.rel >= REL_FLOOR && h.state !== "failed");
    const byPrice = (a, b) => (a.price || Infinity) - (b.price || Infinity);
    const cheap = rel.filter((h) => h.state === "verified" && h.price > 0).sort(byPrice)[0];
    const used = rel.slice().sort((a, b) => b.buyers - a.buyers)[0];
    const value = rel.filter((h) => h.buyers >= MIN && h.state === "verified" && h.price > 0).sort(byPrice)[0];
    $("#buy-picks").innerHTML = [
      pickCard("cheap", "Cheapest verified", cheap, cheap ? `Lowest listed price among relevant endpoints that passed my check on ${esc(hday)}.` : ""),
      pickCard("value", "Best value", value, value ? `Cheapest verified endpoint whose seller had ${MIN}+ genuine buyers last week.` : ""),
      pickCard("used", "Most used", used && used.buyers ? used : null, used && used.buyers ? `Its seller had the most genuine buyers last week (${fmt.int(used.buyers)}), across all its endpoints.` : ""),
    ].join("");
    const pr = hits.filter((h) => h.price > 0).map((h) => h.price).sort((a, b) => a - b);
    const med = pr.length ? pr[Math.floor((pr.length - 1) / 2)] : null;
    let spread = "";
    if (pr.length >= 3) {
      spread = `Prices for this task run from <b>${fmt.usdFull(pr[0])}</b> to <b>${fmt.usdFull(pr[pr.length - 1])}</b> per call (${fmt.int(pr[pr.length - 1] / pr[0])}× apart across ${pr.length} priced matches).`;
      if (cheap && med > cheap.price) spread += ` Paying the median listing (${fmt.usdFull(med)}) instead of the cheapest verified one costs <b>${fmt.usdFull((med - cheap.price) * 1000)} more per 1,000 calls</b>.`;
    }
    $("#buy-spread").innerHTML = spread;
    const cols = [{ k: "listing", label: "Endpoint", t: "html" }, { k: "price", label: "Price / call", t: "price", r: 1 }, { k: "check", label: "Last check", t: "html" }, { k: "buyers", label: "Seller's genuine buyers", t: "int", r: 1 }, { k: "lat", label: "Latency ms", t: "int", r: 1 }];
    const trs = hits.map((h, i) => ({ listing: `<span class="rank">${i + 1}</span>${h.page ? `<a href="/x402/sellers/${h.seller}">${esc(h.name || h.host)}</a>` : esc(h.name || h.host)}<span class="sub">${esc(h.what)} · ${esc(h.host)}${esc(h.path)}</span>`,
      listing_t: `${h.name} ${h.what} ${h.host}${h.path}`, listing_s: -i, check: pill(h.state), check_s: { verified: 3, differs: 2, unchecked: 1, failed: 0 }[h.state], check_t: STATE[h.state][0], state: h.state, price: h.price, buyers: h.buyers, lat: h.lat }));
    $("#buy-table").innerHTML = `<div class="wk-table" id="buy-rows"><script type="application/json">${JSON.stringify({ cols, rows: trs, sort: null, pageSize: 15, placeholder: "Filter these results", csvName: "x402_best_execution.csv",
      facets: [{ k: "state", labels: Object.fromEntries(Object.entries(STATE).map(([k, v]) => [k, v[0]])), order: ["verified", "differs", "unchecked", "failed"] }], search: ["listing_t"] }).replace(/</g, "\\u003c")}</script></div>`;
    WK.initTables($("#buy-table"));
    const top5 = hits.slice(0, 5).map((h) => ({ url: endpoint(h), method: h.method || null, what: h.what, price_usd: h.price, network: h.net, check: h.state, checked_on: h.state === "unchecked" ? null : hday, seller: h.seller, seller_genuine_buyers_last_week: h.buyers }));
    const js = JSON.stringify({ task: q.value.trim(), source: "https://wknipe.com/x402/buy/", listings_snapshot: meta.snapshot, results: top5 }, null, 2);
    $("#buy-json").textContent = js;
    $("#buy-copy").onclick = () => { navigator.clipboard.writeText(js); $("#buy-copy").textContent = "Copied"; setTimeout(() => ($("#buy-copy").textContent = "Copy JSON"), 1500); };
  }
  let tmr = 0; q.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(run, 250); });
  max.addEventListener("change", run); ver.addEventListener("change", run);
  load().catch((e) => (status.textContent = "Failed to load listings: " + e.message));
});
