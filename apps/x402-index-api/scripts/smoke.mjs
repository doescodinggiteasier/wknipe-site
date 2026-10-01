// Smoke test against a running Worker (default wrangler dev on :8787): free routes 200, paid routes 402 with
// correct payment requirements (Base mainnet, USDC, exact, $0.001 = 1000 atomic, payTo = ours).
const BASE = process.env.API ?? "http://localhost:8787";
const USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
const PAY_TO = "0x6ac87b6a48e329e2557c7f6054ed1518be76fbf9";
let fail = 0;
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"} ${msg}`); if (!ok) fail++; };
for (const p of ["/v1/latest", "/v1/method", "/v1/metrics", "/v1/series?metric=waterfall", "/v1/series?metric=posted_by_category", "/v1/route/demo?need=web+search"]) {
  const r = await fetch(BASE + p);
  check(r.status === 200, `${p} -> ${r.status}`);
}
{ // ORDER_014: the demo gives the three picks only, never a full ranking
  const j = await (await fetch(BASE + "/v1/route/demo?need=web+search")).json();
  check(j.picks && !j.results && Object.keys(j.picks).length === 3, `/v1/route/demo returns 3 picks and no results list (matches ${j.matches})`);
}
for (const p of ["/v1/series?stage=clean&category=all", "/v1/sellers?n=5", "/v1/route?need=web+search", "/v1/seller?address=0x68396bd35874695ad86cd29410bd80a550991a2b"]) {
  const r = await fetch(BASE + p, { headers: { Accept: "application/json" } });
  const h = r.headers.get("payment-required");
  const terms = h ? JSON.parse(Buffer.from(h, "base64").toString("utf8")) : null;
  const a = terms?.accepts?.[0] ?? {};
  check(r.status === 402, `${p} -> ${r.status}`);
  check(a.network === "eip155:8453" && (a.asset ?? "").toLowerCase() === USDC && a.scheme === "exact"
        && a.amount === "1000" && (a.payTo ?? "").toLowerCase() === PAY_TO,
        `${p} requirements: ${JSON.stringify({ network: a.network, asset: a.asset, scheme: a.scheme, amount: a.amount, payTo: a.payTo })}`);
}
process.exit(fail ? 1 : 0);
