// ORDER_014: best execution for agents. Ranks Bazaar listings for a task by relevance, the latest endpoint check,
// the seller's genuine buyers and price. Same ranking as wknipe.com/x402/buy/ (formerly client-side in buy.js).
// The table (src/route.json, built by scripts/build-data.mjs) is bundled into the Worker and never served in bulk.
import MiniSearch from "minisearch";
import table from "./route.json";

const N = 40, MIN = 5, PER_SELLER = 3, REL_FLOOR = 0.35;
const FIELDS = ["what", "name", "desc", "host"];
const OPTS = { boost: { what: 3, name: 2, host: 1.2 }, prefix: true, fuzzy: 0.2 };
type State = "verified" | "differs" | "failed" | "unchecked";
type Row = { id: number; host: string; path: string; name: string; what: string; desc: string; price: number | null; net: string | null;
  method: string | null; seller: string | null; buyers: number; paid: number | null; page: boolean; state: State; latency_ms: number | null; category: string };

const T = table as any;
let rows: Row[] | null = null, ms: MiniSearch | null = null;
function index() {
  // Built once per isolate (~0.2 s CPU for ~19k listings); later requests reuse it.
  if (ms) return;
  rows = (T.rows as any[]).map((r, id) => {
    const s = r[8] != null ? T.sellers[r[8]] : null;
    return { id, host: r[0], path: r[1], name: r[2], what: r[3], desc: r[4], price: r[5], net: r[6], method: r[7],
      seller: s ? s[0] : null, buyers: s ? s[1] : 0, paid: s ? s[2] : null, page: !!(s && s[3]), state: r[9], latency_ms: r[10], category: r[11] };
  });
  ms = new MiniSearch({ fields: FIELDS, storeFields: [], searchOptions: OPTS });
  ms.addAll(rows);
}

export const routeMeta = () => ({ listings_snapshot: T.snapshot, buyers_week: T.week, checked_on: T.checked_on, data_built_at: T.built_at });
export const routeReady = () => (T.rows?.length ?? 0) > 0;

export function rank(need: string, opt: { maxPrice?: number | null; verifiedOnly?: boolean } = {}) {
  index();
  const per = new Map<string, number>(), hits: (Row & { rel: number; score: number })[] = [];
  const res = ms!.search(need);
  const top = res.length ? res[0].score : 1;
  for (const h of res) {
    const r = rows![h.id as number];
    if (opt.maxPrice != null && !(r.price && r.price > 0 && r.price <= opt.maxPrice)) continue;
    if (opt.verifiedOnly && r.state !== "verified") continue;
    const k = r.seller || r.host, n = per.get(k) || 0;
    if (n >= PER_SELLER) continue;
    per.set(k, n + 1);
    hits.push({ ...r, rel: h.score / top, score: 0 });
    if (hits.length >= N) break;
  }
  const priced = hits.filter((h) => h.price && h.price > 0).map((h) => Math.log10(h.price!));
  const lo = Math.min(...priced), span = Math.max(0.5, Math.max(...priced) - lo);
  for (const h of hits) {
    const p = h.price && h.price > 0 ? 1 - (Math.log10(h.price) - lo) / span : 0;
    h.score = h.rel + (h.state === "verified" ? 0.35 : h.state === "differs" ? 0.1 : h.state === "failed" ? -0.6 : 0)
      + (h.buyers >= MIN ? 0.25 : h.buyers > 0 ? 0.08 : 0) + 0.2 * p;
  }
  hits.sort((a, b) => b.score - a.score);
  const rel = hits.filter((h) => h.rel >= REL_FLOOR && h.state !== "failed");
  const byPrice = (a: Row, b: Row) => (a.price || Infinity) - (b.price || Infinity);
  const cheapest = rel.filter((h) => h.state === "verified" && h.price && h.price > 0).sort(byPrice)[0] ?? null;
  const value = rel.filter((h) => h.buyers >= MIN && h.state === "verified" && h.price && h.price > 0).sort(byPrice)[0] ?? null;
  const usedTop = rel.slice().sort((a, b) => b.buyers - a.buyers)[0];
  const most_used = usedTop && usedTop.buyers ? usedTop : null;
  const pr = hits.filter((h) => h.price && h.price > 0).map((h) => h.price!).sort((a, b) => a - b);
  const spread = pr.length ? { priced: pr.length, min_usd: pr[0], median_usd: pr[Math.floor((pr.length - 1) / 2)], max_usd: pr[pr.length - 1] } : null;
  return { hits, picks: { cheapest_verified: cheapest, best_value: value, most_used }, spread };
}

export const out = (h: any) => h && {
  url: `https://${h.host}${h.path}`, method: h.method ?? null, name: h.name || h.host, what: h.what, price_usd: h.price ?? null, network: h.net ?? null,
  check: h.state, latency_ms: h.latency_ms ?? null, seller: h.seller, seller_genuine_buyers_last_week: h.buyers,
  seller_page: h.page ? `https://wknipe.com/x402/sellers/${h.seller}` : null,
};

// ORDER_014 (follow-up): Price comps. Comparable listings for a described API, at most 3 per seller, their posted price
// distribution, and whether their sellers have 5+ genuine buyers. Same matching as the old client-side comps.js.
const COMPS_N = 60;
const pctl = (xs: number[], p: number) => { if (!xs.length) return null; const s = xs.slice().sort((a, b) => a - b), k = (s.length - 1) * p, f = Math.floor(k), c = Math.min(f + 1, s.length - 1); return s[f] + (s[c] - s[f]) * (k - f); };

export function comps(find: string, category: string | null) {
  index();
  let hits: Row[] = [];
  if (find) {
    const per = new Map<string, number>();
    for (const h of ms!.search(find, { filter: (r: any) => !category || rows![r.id].category === category } as any)) {
      const r = rows![h.id as number], k = r.seller || r.host, n = per.get(k) || 0;
      if (n >= PER_SELLER) continue;
      per.set(k, n + 1); hits.push(r);
      if (hits.length >= COMPS_N) break;
    }
  } else if (category) hits = rows!.filter((r) => r.category === category);
  const priced = hits.filter((h) => h.price && h.price > 0).map((h) => h.price!);
  const sellers = new Map<string, Row>(); hits.forEach((h) => h.seller && sellers.set(h.seller, h));
  const sellersB = [...sellers.values()].filter((h) => h.buyers >= MIN);
  const paid = sellersB.map((h) => h.paid).filter((x): x is number => x != null);
  // log10 bins of width 0.25 for the histogram: [bin_lo_usd, listings, listings whose seller has 5+ buyers]
  const bins = new Map<number, [number, number]>();
  for (const h of hits) if (h.price && h.price > 0) { const b = Math.floor(Math.log10(h.price) * 4) / 4, x = bins.get(b) ?? [0, 0]; x[0]++; if (h.buyers >= MIN) x[1]++; bins.set(b, x); }
  return {
    hits,
    summary: { comparables: hits.length, sellers: sellers.size, priced: priced.length,
      posted_p10_usd: pctl(priced, 0.1), posted_median_usd: pctl(priced, 0.5), posted_p90_usd: pctl(priced, 0.9),
      comparables_with_5_buyer_seller: hits.filter((h) => h.buyers >= MIN).length, sellers_with_5_buyers: sellersB.length,
      realised_median_usd: pctl(paid, 0.5), realised_sellers: paid.length },
    histogram: [...bins.entries()].sort((a, b) => a[0] - b[0]).map(([b, [n, n5]]) => ({ lo_usd: +(10 ** b).toPrecision(4), hi_usd: +(10 ** (b + 0.25)).toPrecision(4), listings: n, with_5_buyer_seller: n5 })),
  };
}

export const compOut = (h: any) => h && { name: h.name || h.host, what: h.what, category: h.category, url: `https://${h.host}${h.path}`, price_usd: h.price ?? null, network: h.net ?? null,
  seller: h.seller, seller_genuine_buyers_last_week: h.buyers, seller_paid_median_usd: h.paid ?? null,
  seller_page: h.page ? `https://wknipe.com/x402/sellers/${h.seller}` : null };
