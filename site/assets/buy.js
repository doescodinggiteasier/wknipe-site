/* Best execution (/x402/buy/): a demo. For a task, three picks from the free API route /v1/route/demo (cheapest
   verified, best value, most used). The full ranking is the paid x402 route /v1/route (ORDER_014); no bulk data
   is downloaded here. */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";
  const WK = window.WK, fmt = WK.fmt, esc = WK.esc;
  const $ = (s) => document.querySelector(s);
  const MIN = 5;
  const API = $("#buy-form").dataset.api;
  const EX = ["web search", "scrape web page to markdown", "token price", "weather forecast", "llm chat completion", "company enrichment", "sec filings", "twitter search", "image generation", "news headlines"];
  const q = $("#buy-q"), max = $("#buy-max"), ver = $("#buy-verified"), status = $("#buy-status");

  $("#buy-examples").innerHTML = EX.map((e) => `<button type="button" class="chip" data-ex="${esc(e)}">${esc(e)}</button>`).join("");
  $("#buy-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-ex]"); if (b) { q.value = b.dataset.ex; run(); } });

  const STATE = {
    verified: ["verified", "ok", "Valid 402 at the listed price and payTo"],
    differs: ["answers, price differs", "gold", "Valid 402, but the live price or payTo differs from the listing"],
    failed: ["failed check", "bad", "No valid 402 on the last check"],
    unchecked: ["not checked yet", "", "Not in today's sample of the daily monitor"],
  };
  const pill = (s) => `<span class="pill ${STATE[s][1]}" title="${esc(STATE[s][2])}">${esc(STATE[s][0])}</span>`;
  const pickCard = (kind, title, h, why) => h
    ? `<div class="pick ${kind}"><div class="pk">${esc(title)}</div><div class="pn">${h.seller_page ? `<a href="${esc(h.seller_page.replace("https://wknipe.com", ""))}">${esc(h.name)}</a>` : esc(h.name)}</div>
       <div class="pp">${h.price_usd > 0 ? fmt.usdFull(h.price_usd) : "unpriced"}<small> / call</small></div><div class="pw">${esc(h.what)}</div>
       <div class="pm">${pill(h.check)} ${h.seller_genuine_buyers_last_week ? `<span class="pill">${fmt.int(h.seller_genuine_buyers_last_week)} genuine buyers</span>` : ""}</div><code class="pu">${esc(h.url)}</code><div class="why">${why}</div></div>`
    : `<div class="pick ${kind} none"><div class="pk">${esc(title)}</div><div class="pw">No match qualifies. ${kind === "value" ? `No relevant seller with ${MIN}+ genuine buyers passed the check.` : "Try a broader task."}</div></div>`;

  let seq = 0;
  async function run() {
    const need = q.value.trim();
    const u = new URL(location); need ? u.searchParams.set("need", need) : u.searchParams.delete("need");
    max.value ? u.searchParams.set("max", max.value) : u.searchParams.delete("max"); ver.checked ? u.searchParams.set("verified", "1") : u.searchParams.delete("verified");
    history.replaceState(null, "", u);
    if (!need) { $("#buy-out").hidden = true; return; }
    const my = ++seq;
    status.textContent = "Searching…";
    const p = new URLSearchParams({ need }); if (max.value) p.set("max_price", max.value); if (ver.checked) p.set("verified", "1");
    let j;
    try {
      const r = await fetch(`${API}/v1/route/demo?${p}`);
      if (r.status === 402 || r.status === 429) { status.textContent = "Too many searches from here in the last minute. Try again shortly."; return; }
      j = await r.json();
    } catch (e) { status.textContent = "The search service did not answer. Try again shortly."; return; }
    if (my !== seq) return;
    $("#buy-out").hidden = !j.matches;
    if (!j.matches) { status.textContent = "No listing matches. Try fewer or more general words, or lift the price cap."; return; }
    status.textContent = `${j.matches} relevant listings · checks ${j.checked_on || "–"}`;
    const k = j.picks;
    $("#buy-picks").innerHTML = [
      pickCard("cheap", "Cheapest verified", k.cheapest_verified, k.cheapest_verified ? `Lowest listed price among relevant endpoints that passed my check on ${esc(j.checked_on)}.` : ""),
      pickCard("value", "Best value", k.best_value, k.best_value ? `Cheapest verified endpoint whose seller had ${MIN}+ genuine buyers last week.` : ""),
      pickCard("used", "Most used", k.most_used, k.most_used ? `Its seller had the most genuine buyers last week (${fmt.int(k.most_used.seller_genuine_buyers_last_week)}), across all its endpoints.` : ""),
    ].join("");
    const s = j.spread, c = k.cheapest_verified;
    let spread = "";
    if (s && s.priced >= 3) {
      spread = `Prices for this task run from <b>${fmt.usdFull(s.min_usd)}</b> to <b>${fmt.usdFull(s.max_usd)}</b> per call (${fmt.int(s.max_usd / s.min_usd)}× apart across ${s.priced} priced matches).`;
      if (c && s.median_usd > c.price_usd) spread += ` Paying the median listing (${fmt.usdFull(s.median_usd)}) instead of the cheapest verified one costs <b>${fmt.usdFull((s.median_usd - c.price_usd) * 1000)} more per 1,000 calls</b>.`;
    }
    $("#buy-spread").innerHTML = spread;
  }
  let tmr = 0; q.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(run, 400); });
  max.addEventListener("change", run); ver.addEventListener("change", run);
  const u0 = new URLSearchParams(location.search);
  if (u0.get("need")) q.value = u0.get("need"); if (u0.get("max")) max.value = u0.get("max"); if (u0.get("verified") === "1") ver.checked = true;
  status.textContent = "Type a task or pick an example.";
  if (q.value) run();
});
