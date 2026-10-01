// ORDER_014: best execution for agents. Ranks Bazaar listings for a task by relevance, the latest endpoint check,
// the seller's genuine buyers and price. Same ranking as wknipe.com/x402/buy/ (formerly client-side in buy.js).
// The table (src/route.json, built by scripts/build-data.mjs) is bundled into the Worker and never served in bulk.
import table from "./route.json";

const N = 40, MIN = 5, PER_SELLER = 3, REL_FLOOR = 0.35;
type State = "verified" | "differs" | "failed" | "unchecked";
type Row = { id: number; host: string; path: string; name: string; what: string; desc: string; price: number | null; net: string | null;
  method: string | null; seller: string | null; buyers: number; paid: number | null; page: boolean; state: State; latency_ms: number | null; category: string };

const T = table as any;
let rows: Row[] | null = null;
function index() {
  if (rows) return;
  rows = (T.rows as any[]).map((r, id) => {
    const s = r[8] != null ? T.sellers[r[8]] : null;
    return { id, host: r[0], path: r[1], name: r[2], what: r[3], desc: r[4], price: r[5], net: r[6], method: r[7],
      seller: s ? s[0] : null, buyers: s ? s[1] : 0, paid: s ? s[2] : null, page: !!(s && s[3]), state: r[9], latency_ms: r[10], category: r[11] };
  });
}

// Search over the inverted index built by scripts/build-data.mjs (same tokenizer, BM25+ weights and field boosts as
// MiniSearch; exact terms weigh 1, prefix matches 0.375, fuzzy matches 0.45 scaled by distance, as MiniSearch does).
const TOK: string[] = T.idx?.tokens ?? [], POST: number[][] = T.idx?.post ?? [];
const lower = (q: string) => { let lo = 0, hi = TOK.length; while (lo < hi) { const m = (lo + hi) >> 1; if (TOK[m] < q) lo = m + 1; else hi = m; } return lo; };
function lev(a: string, b: string, max: number) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i]; let best = i;
    for (let j = 1; j <= b.length; j++) { cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); best = Math.min(best, cur[j]); }
    if (best > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}
function search(query: string, keep?: (r: Row) => boolean) {
  const terms = query.toLowerCase().split(/[\n\r\p{Z}\p{P}]+/u).filter(Boolean).slice(0, 8);
  const score = new Map<number, number>(), quality = new Map<number, number>();
  let hit = new Set<number>();
  const add = (k: number, weight: number) => { const p = POST[k]; let id = 0; for (let i = 0; i < p.length; i += 2) { id += p[i]; hit.add(id); score.set(id, (score.get(id) || 0) + weight * p[i + 1] / 100); } };
  for (const t of terms) {
    hit = new Set<number>();
    const seen = new Set<number>();
    const lo = lower(t);
    for (let k = lo; k < TOK.length && TOK[k].startsWith(t); k++) { seen.add(k); add(k, TOK[k] === t ? 1 : 0.375 * t.length / (t.length + 0.3 * (TOK[k].length - t.length))); }
    const max = Math.round(0.2 * t.length);
    if (max > 0) {  // fuzzy: tokens sharing the first letter, within the edit distance
      for (let k = lower(t[0]); k < TOK.length && TOK[k][0] === t[0]; k++) {
        if (seen.has(k)) continue;
        const d = lev(t, TOK[k], max);
        if (d <= max) add(k, 0.45 * t.length / (t.length + d));
      }
    }
    hit.forEach((id) => quality.set(id, (quality.get(id) || 0) + 1));
  }
  // as MiniSearch: a document's score is multiplied by the number of query terms it matched
  const out = [...score].map(([id, s]) => ({ id, score: s * (quality.get(id) || 1) })).filter((h) => !keep || keep(rows![h.id]));
  return out.sort((a, b) => b.score - a.score);
}

export const routeMeta = () => ({ listings_snapshot: T.snapshot, buyers_week: T.week, checked_on: T.checked_on, data_built_at: T.built_at });
export const routeReady = () => (T.rows?.length ?? 0) > 0;

export function rank(need: string, opt: { maxPrice?: number | null; verifiedOnly?: boolean } = {}) {
  index();
  const per = new Map<string, number>(), hits: (Row & { rel: number; score: number })[] = [];
  const res = search(need);
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
    for (const h of search(find, (r) => !category || r.category === category)) {
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
