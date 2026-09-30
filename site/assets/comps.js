/* Price comps (ORDER_013): describe an API -> comparable Bazaar listings, their posted price distribution, and whether
   comparable sellers get genuine buyers. Data: /x402/data/listings.json (built by scripts/x402_prices/build.py). */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const WK = window.WK, fmt = WK.fmt, esc = WK.esc, L = WK.CAT_LABEL;
  const $ = (s) => document.querySelector(s);
  const N = 60, MIN = 5, PER_SELLER = 3;
  const EX = ["token price lookup", "wallet balance", "scrape web page", "web search results", "news article", "image generation", "llm chat completion", "weather forecast", "company enrichment", "pdf to text"];
  let rows = [], ms = null, meta = null;

  const q = $("#comps-q"), cat = $("#comps-cat"), status = $("#comps-status");
  $("#comps-examples").innerHTML = EX.map((e) => `<button type="button" class="chip" data-ex="${esc(e)}">${esc(e)}</button>`).join("");
  $("#comps-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-ex]"); if (b) { q.value = b.dataset.ex; run(); } });

  const pctl = (xs, p) => { if (!xs.length) return null; const s = xs.slice().sort((a, b) => a - b), k = (s.length - 1) * p, f = Math.floor(k), c = Math.min(f + 1, s.length - 1); return s[f] + (s[c] - s[f]) * (k - f); };
  const median = (xs) => pctl(xs, 0.5);

  async function load() {
    await WK.load("/assets/vendor/minisearch-7.min.js");
    meta = await WK.json("/x402/data/listings.json");
    const ci = Object.fromEntries(meta.cols.map((c, i) => [c, i]));
    rows = meta.rows.map((r, id) => {
      const s = r[ci.seller] != null ? meta.sellers[r[ci.seller]] : null;
      return { id, host: r[ci.host], path: r[ci.path], name: r[ci.name], what: r[ci.what] || "", category: r[ci.category], desc: r[ci.desc], price: r[ci.price_usd], net: r[ci.price_network],
        seller: s ? s[0] : null, buyers: s ? s[1] : 0, paid: s ? s[2] : null, page: s ? s[3] : false };
    });
    ms = new MiniSearch({ fields: ["what", "name", "desc", "host"], storeFields: [], searchOptions: { boost: { what: 3, name: 2, host: 1.2 }, prefix: true, fuzzy: 0.2 } });
    await ms.addAllAsync(rows, { chunkSize: 1000 });
    status.textContent = `${rows.length.toLocaleString("en-US")} listings from the Bazaar snapshot ${meta.snapshot}`;
    const u = new URLSearchParams(location.search);
    if (u.get("find")) q.value = u.get("find"); if (u.get("cat")) cat.value = u.get("cat");
    if (q.value || cat.value) run();
  }

  function comparables() {
    const text = q.value.trim(), c = cat.value;
    let hits;
    if (text) {
      // at most PER_SELLER comparables per seller (or host when unlisted on Base), so one big lister can't set the distribution
      const per = new Map(); hits = [];
      for (const h of ms.search(text, { filter: (r) => !c || rows[r.id].category === c })) {
        const r = rows[h.id], k = r.seller || r.host, n = per.get(k) || 0;
        if (n >= PER_SELLER) continue; per.set(k, n + 1); hits.push({ ...r, score: h.score });
        if (hits.length >= N) break;
      }
    }
    else if (c) hits = rows.filter((r) => r.category === c);
    else hits = [];
    return hits;
  }

  async function run() {
    if (!ms) return;
    const u = new URL(location); u.searchParams.set("find", q.value.trim()); cat.value ? u.searchParams.set("cat", cat.value) : u.searchParams.delete("cat"); history.replaceState(null, "", u);
    const hits = comparables();
    $("#comps-out").hidden = !hits.length;
    if (!hits.length) { status.textContent = q.value || cat.value ? "No comparable listings found. Try fewer or more general words." : status.textContent; return; }
    const priced = hits.filter((h) => h.price > 0).map((h) => h.price);
    const sellers = new Map(); hits.forEach((h) => h.seller && sellers.set(h.seller, h));
    const withB = hits.filter((h) => h.buyers >= MIN), sellersB = [...sellers.values()].filter((h) => h.buyers >= MIN);
    const paid = sellersB.map((h) => h.paid).filter((x) => x != null);
    const p10 = pctl(priced, 0.1), p50 = median(priced), p90 = pctl(priced, 0.9), rp = median(paid);
    const card = (k, v, foot) => `<div class="stat-card"><div class="k"><span>${esc(k)}</span></div><div class="v">${v}</div>${foot ? `<div class="foot">${foot}</div>` : ""}</div>`;
    $("#comps-kpis").innerHTML = [
      card("Comparable listings", hits.length.toLocaleString("en-US"), `${sellers.size} distinct sellers on Base`),
      card("Posted price, median", fmt.usdFull(p50), `p10 ${fmt.usdFull(p10)} · p90 ${fmt.usdFull(p90)} · ${priced.length} priced`),
      card(`Comparables whose seller had ${MIN}+ genuine buyers`, `${withB.length} of ${hits.length}`, `${sellersB.length} of ${sellers.size} sellers, week of ${fmt.week(meta.week)}`),
      card("Realised price at those sellers", fmt.usdFull(rp), paid.length ? `median of ${paid.length} sellers' median clean payment` : "no comparable seller had enough buyers"),
    ].join("");
    $("#comps-title").textContent = sellersB.length
      ? `${withB.length} of ${hits.length} comparables sell through a seller with ${MIN}+ genuine buyers; they realise a median ${fmt.usdFull(rp)} per payment against a posted median of ${fmt.usdFull(p50)}`
      : `None of the ${hits.length} comparables' sellers had ${MIN}+ genuine buyers last week; posted median ${fmt.usdFull(p50)}`;
    $("#comps-sub").innerHTML = `Posted price per call of the comparable listings (log scale). Gold line: median realised payment at comparable sellers with ${MIN}+ genuine buyers. Query: <b>${esc(q.value || "(category only)")}</b>${cat.value ? ` · ${esc(L[cat.value])}` : ""}.`;
    await WK.plotReady();
    const t = WK.theme($("#comps-dist")), body = $("#comps-dist .plot"), width = Math.max(280, body.clientWidth);
    const bins = d3.bin().thresholds(d3.range(-4, 4.01, 0.25)).value((h) => Math.log10(h.price))(hits.filter((h) => h.price > 0));
    body.replaceChildren(Plot.plot({ width, height: 220, marginLeft: 40, style: { fontFamily: "Inter, system-ui, sans-serif", fontSize: "12px", color: t.muted, background: "transparent" },
      x: { type: "log", label: "Posted USD per call (log scale)", labelAnchor: "center", labelArrow: false, tickFormat: fmt.usd, grid: true }, y: { label: null, grid: true, tickFormat: "d" },
      marks: [Plot.rectY(bins.filter((b) => b.length), { x1: (b) => 10 ** b.x0, x2: (b) => 10 ** b.x1, y: (b) => b.length, fill: t.primary, inset: 1, tip: { fill: t.surface, stroke: t.line }, title: (b) => `${fmt.usdFull(10 ** b.x0)}–${fmt.usdFull(10 ** b.x1)}: ${b.length} listings\n${b.filter((h) => h.buyers >= MIN).length} with a ${MIN}+ buyer seller` }),
        rp ? Plot.ruleX([rp], { stroke: t.clean, strokeWidth: 2.5 }) : null, rp ? Plot.text([rp], { x: (d) => d, frameAnchor: "top", dy: -2, text: () => "realised " + fmt.usdFull(rp), fill: t.ink, textAnchor: "start", dx: 5 }) : null, Plot.ruleY([0], { stroke: t.line })] }));
    const cols = [{ k: "listing", label: "Listing", t: "html" }, { k: "cat", label: "Category", t: "html" }, { k: "price", label: "Posted", t: "price", r: 1 }, { k: "buyers", label: "Seller's buyers", t: "int", r: 1 }, { k: "paid", label: "Seller's paid median", t: "price", r: 1 }];
    const trs = hits.map((h) => ({ listing: `${h.page ? `<a href="/x402/sellers/${h.seller}">${esc(h.name || h.host)}</a>` : esc(h.name || h.host)}<span class="sub">${esc(h.what)} · ${esc(h.host)}${esc(h.path)}</span>`, listing_t: `${h.name} ${h.host}${h.path}`, listing_s: h.name || h.host,
      cat: `<i class="cat-dot" style="background:var(--c-${h.category})"></i>${esc((L[h.category] || h.category).split(" (")[0])}`, cat_s: h.category, cat_t: h.category, category: h.category, price: h.price, buyers: h.buyers, paid: h.paid }));
    $("#comps-table").innerHTML = `<div class="wk-table" id="comps-rows"><script type="application/json">${JSON.stringify({ cols, rows: trs, sort: null, pageSize: 20, placeholder: "Filter comparables", csvName: "price_comps.csv", facets: [{ k: "category", dot: 1, order: WK.CATS }], search: ["listing_t", "category"] }).replace(/</g, "\\u003c")}</script></div>`;
    WK.initTables($("#comps-table"));
    $("#comps-csv").onclick = () => WK.download("price_comps.csv", WK.toCSV([{ k: "name", label: "name" }, { k: "host", label: "host" }, { k: "path", label: "path" }, { k: "what", label: "what" }, { k: "category", label: "category" }, { k: "price", label: "posted_usd" }, { k: "net", label: "network" }, { k: "seller", label: "seller" }, { k: "buyers", label: "seller_buyers_last_week" }, { k: "paid", label: "seller_paid_median_usd" }], hits));
  }
  let tmr = 0; q.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(run, 250); }); cat.addEventListener("change", run);
  load().catch((e) => (status.textContent = "Failed to load listings: " + e.message));
});
