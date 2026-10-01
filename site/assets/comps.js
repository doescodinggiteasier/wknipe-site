/* Price comps: describe an API -> comparable Bazaar listings, their posted price distribution, and whether comparable
   sellers get genuine buyers. Data: the free API route /v1/comps/demo (summary, histogram, 5 best matches). The full
   comparable list is the paid x402 route /v1/comps (ORDER_014); no bulk listings file is downloaded here. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const WK = window.WK, fmt = WK.fmt, esc = WK.esc, L = WK.CAT_LABEL;
  const $ = (s) => document.querySelector(s);
  const MIN = 5;
  const API = $("#comps-form").dataset.api;
  const EX = ["token price lookup", "wallet balance", "scrape web page", "web search results", "news article", "image generation", "llm chat completion", "weather forecast", "company enrichment", "pdf to text"];
  const q = $("#comps-q"), cat = $("#comps-cat"), status = $("#comps-status");
  $("#comps-examples").innerHTML = EX.map((e) => `<button type="button" class="chip" data-ex="${esc(e)}">${esc(e)}</button>`).join("");
  $("#comps-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-ex]"); if (b) { q.value = b.dataset.ex; run(); } });

  let seq = 0;
  async function run() {
    const find = q.value.trim(), c = cat.value;
    const u = new URL(location); find ? u.searchParams.set("find", find) : u.searchParams.delete("find"); c ? u.searchParams.set("cat", c) : u.searchParams.delete("cat"); history.replaceState(null, "", u);
    if (!find && !c) { $("#comps-out").hidden = true; return; }
    const my = ++seq;
    status.textContent = "Searching…";
    const p = new URLSearchParams(); if (find) p.set("find", find); if (c) p.set("category", c);
    let j;
    try {
      const r = await fetch(`${API}/v1/comps/demo?${p}`);
      if (r.status === 402 || r.status === 429) { status.textContent = "Too many searches from here in the last minute. Try again shortly."; return; }
      j = await r.json();
    } catch (e) { status.textContent = "The search service did not answer. Try again shortly."; return; }
    if (my !== seq) return;
    const S = j.summary;
    $("#comps-out").hidden = !S || !S.comparables;
    if (!S || !S.comparables) { status.textContent = "No comparable listings found. Try fewer or more general words."; return; }
    status.textContent = `Bazaar snapshot ${j.listings_snapshot} · buyers week of ${fmt.week(j.buyers_week)}`;
    const card = (k, v, foot) => `<div class="stat-card"><div class="k"><span>${esc(k)}</span></div><div class="v">${v}</div>${foot ? `<div class="foot">${foot}</div>` : ""}</div>`;
    $("#comps-kpis").innerHTML = [
      card("Comparable listings", fmt.int(S.comparables), `${S.sellers} distinct sellers on Base`),
      card("Posted price, median", fmt.usdFull(S.posted_median_usd), `p10 ${fmt.usdFull(S.posted_p10_usd)} · p90 ${fmt.usdFull(S.posted_p90_usd)} · ${S.priced} priced`),
      card(`Comparables whose seller had ${MIN}+ genuine buyers`, `${S.comparables_with_5_buyer_seller} of ${S.comparables}`, `${S.sellers_with_5_buyers} of ${S.sellers} sellers, week of ${fmt.week(j.buyers_week)}`),
      card("Realised price at those sellers", fmt.usdFull(S.realised_median_usd), S.realised_sellers ? `median of ${S.realised_sellers} sellers' median clean payment` : "no comparable seller had enough buyers"),
    ].join("");
    const rp = S.realised_median_usd;
    $("#comps-title").textContent = S.sellers_with_5_buyers
      ? `${S.comparables_with_5_buyer_seller} of ${S.comparables} comparables sell through a seller with ${MIN}+ genuine buyers; they realise a median ${fmt.usdFull(rp)} per payment against a posted median of ${fmt.usdFull(S.posted_median_usd)}`
      : `None of the ${S.comparables} comparables' sellers had ${MIN}+ genuine buyers last week; posted median ${fmt.usdFull(S.posted_median_usd)}`;
    $("#comps-sub").innerHTML = `Posted price per call of the comparable listings (log scale). Gold line: median realised payment at comparable sellers with ${MIN}+ genuine buyers. Query: <b>${esc(find || "(category only)")}</b>${c ? ` · ${esc(L[c])}` : ""}.`;
    await WK.plotReady();
    const t = WK.theme($("#comps-dist")), body = $("#comps-dist .plot"), width = Math.max(280, body.clientWidth);
    body.replaceChildren(Plot.plot({ width, height: 220, marginLeft: 40, style: { fontFamily: "Geist, system-ui, sans-serif", fontSize: "12px", color: t.muted, background: "transparent" },
      x: { type: "log", label: "Posted USD per call (log scale)", labelAnchor: "center", labelArrow: false, tickFormat: fmt.usd, grid: true }, y: { label: null, grid: true, tickFormat: "d" },
      marks: [Plot.rectY(j.histogram, { x1: "lo_usd", x2: "hi_usd", y: "listings", fill: t.primary, inset: 1, tip: { fill: t.surface, stroke: t.line }, title: (b) => `${fmt.usdFull(b.lo_usd)}–${fmt.usdFull(b.hi_usd)}: ${b.listings} listings\n${b.with_5_buyer_seller} with a ${MIN}+ buyer seller` }),
        rp ? Plot.ruleX([rp], { stroke: t.clean, strokeWidth: 2.5 }) : null, rp ? Plot.text([rp], { x: (d) => d, frameAnchor: "top", dy: -2, text: () => "realised " + fmt.usdFull(rp), fill: t.ink, textAnchor: "start", dx: 5 }) : null, Plot.ruleY([0], { stroke: t.line })] }));
    $("#comps-table").innerHTML = `<h3 class="comps-top">The ${j.comparables.length} closest matches</h3><ul class="rows comps-rows">` + j.comparables.map((h) =>
      `<li><a href="${esc(h.seller_page ? h.seller_page.replace("https://wknipe.com", "") : h.url)}"><span class="t">${esc(h.name)}<span class="sub">${esc(h.what)} · ${esc((L[h.category] || h.category || "").split(" (")[0])}</span></span>` +
      `<span class="d2">${h.price_usd > 0 ? fmt.usdFull(h.price_usd) : "unpriced"} / call${h.seller_genuine_buyers_last_week ? ` · seller ${fmt.int(h.seller_genuine_buyers_last_week)} genuine buyers` : ""}</span><span class="x">→</span></a></li>`).join("") + "</ul>";
  }
  let tmr = 0; q.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(run, 400); }); cat.addEventListener("change", run);
  const u0 = new URLSearchParams(location.search);
  if (u0.get("find")) q.value = u0.get("find"); if (u0.get("cat")) cat.value = u0.get("cat");
  status.textContent = "Type a description or pick an example.";
  if (q.value || cat.value) run();
});
