// x402 Clean Index public API (ORDER_011 Module C). Cloudflare Worker + Hono + x402 v2 middleware.
// Free:  GET /v1/latest, GET /v1/method
// Paid:  GET /v1/series, GET /v1/sellers  ($0.001 per call, USDC on Base mainnet, via the public PayAI facilitator)
// ORDER_012 Build 1 (free, rate-limited, cached 24 h): GET /v1/check?domain=, GET /v1/check/examples
import { Hono } from "hono";
import { cors } from "hono/cors";
import { paymentMiddleware, x402ResourceServer } from "@x402/hono";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { HTTPFacilitatorClient } from "@x402/core/server";
import data from "./data.json";
import { EXAMPLES, normaliseDomain, runCheck } from "./check";

type Env = {
  PAY_TO: string; FACILITATOR_URL: string; PRICE: string;
  CHECK_CACHE: KVNamespace;                                   // domain -> last check, 24 h TTL
  CHECK_LIMIT?: { limit(o: { key: string }): Promise<{ success: boolean }> }; // 30 checks / min / client
};

const NETWORK = "eip155:8453"; // Base mainnet (CAIP-2)
const STAGES = ["raw", "d05", "clean"];
const CATEGORIES = ["content", "data", "search", "compute", "other", "large_ticket", "unclassed", "all"];

const app = new Hono<{ Bindings: Env }>();
app.use("*", cors({ origin: "*", exposeHeaders: ["PAYMENT-REQUIRED", "PAYMENT-RESPONSE"] }));

// The resource server and middleware are built once per isolate, on the first request, because Workers may not
// make network calls (the facilitator sync) at module load and the payTo comes from a runtime variable.
let paid: ReturnType<typeof paymentMiddleware> | null = null;
function paywall(env: Env) {
  if (paid) return paid;
  const server = new x402ResourceServer(new HTTPFacilitatorClient({ url: env.FACILITATOR_URL }))
    .register(NETWORK, new ExactEvmScheme());
  const accepts = [{ scheme: "exact", price: env.PRICE, network: NETWORK, payTo: env.PAY_TO, maxTimeoutSeconds: 60 }];
  paid = paymentMiddleware(
    {
      "GET /v1/series": { accepts, description: "x402 Clean Index weekly series (stage x category)", mimeType: "application/json" },
      "GET /v1/sellers": { accepts, description: "x402 Clean Index top cleaned sellers, latest week", mimeType: "application/json" },
    },
    server,
  );
  return paid;
}
// ORDER_013: /v1/series?metric=NAME is free (the chart series behind wknipe.com); /v1/series?stage=&category= stays paid.
app.use("/v1/series", (c, next) => (c.req.query("metric") ? next() : paywall(c.env)(c, next)));
app.use("/v1/sellers", (c, next) => paywall(c.env)(c, next));

app.get("/", (c) =>
  c.json({
    name: "x402 Clean Index API",
    docs: "https://wknipe.com/x402/",
    free: ["/v1/latest", "/v1/method", "/v1/metrics", "/v1/series?metric=waterfall", "/v1/check?domain=example.com", "/v1/check/examples", "/v1/badge/policy?domain=example.com", "/v1/probe?url=https://api.example.com/paid"],
    paid: { routes: ["/v1/series?stage=clean&category=all", "/v1/sellers?category=all&n=20"], price: c.env.PRICE, network: NETWORK, asset: "USDC" },
    data_built_at: data.built_at,
  }),
);
// ---- AI-policy checker ----
const CHECK_TTL = 86400;
const cacheKey = (d: string) => `check:v1:${d}`;

async function clientKey(c: any) {
  // Rate-limit key: a hash of the client IP, held only by the limiter for its 60 s window. Never stored or logged.
  const ip = c.req.header("cf-connecting-ip") ?? "unknown";
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("wknipe-check:" + ip));
  return [...new Uint8Array(h).slice(0, 12)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function limited(c: any) {
  if (!c.env.CHECK_LIMIT) return false;
  const { success } = await c.env.CHECK_LIMIT.limit({ key: await clientKey(c) });
  return !success;
}

async function checkCached(env: Env, domain: string, compute: boolean) {
  const hit = await env.CHECK_CACHE.get(cacheKey(domain), "json");
  if (hit) return { ...(hit as object), cached: true };
  if (!compute) return null;
  const res = await runCheck(domain);
  await env.CHECK_CACHE.put(cacheKey(domain), JSON.stringify(res), { expirationTtl: CHECK_TTL });
  return { ...res, cached: false };
}

app.get("/v1/check", async (c) => {
  const domain = normaliseDomain(c.req.query("domain"));
  if (!domain) return c.json({ error: "give a public domain name, e.g. ?domain=example.com" }, 400);
  if (await limited(c)) return c.json({ error: "rate limit: 30 checks a minute; try again shortly" }, 429);
  const res = await checkCached(c.env, domain, true);
  return c.json(res, 200, { "Cache-Control": "public, max-age=3600" });
});

app.get("/v1/check/examples", async (c) => {
  if (await limited(c)) return c.json({ error: "rate limit: 30 checks a minute; try again shortly" }, 429);
  let budget = 3; // compute at most 3 uncached examples per call (subrequest limits); the weekly job warms them all
  const out = [];
  for (const d of EXAMPLES) {
    let r = await checkCached(c.env, d, false);
    if (!r && budget > 0) { budget--; r = await checkCached(c.env, d, true); }
    out.push(r ?? { domain: d, pending: true });
  }
  return c.json({ examples: out }, 200, { "Cache-Control": "public, max-age=600" });
});

// ORDER_013 Phase 5: embeddable AI-policy badge for publishers (SVG). Uses the same 24 h check cache.
function badgeSvg(label: string, value: string, color: string) {
  const esc = (x: string) => x.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]!));
  const lw = Math.round(label.length * 6.3 + 12), vw = Math.round(value.length * 6.6 + 12), w = lw + vw;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="20" role="img" aria-label="${esc(label)}: ${esc(value)}"><title>${esc(label)}: ${esc(value)}</title><clipPath id="r"><rect width="${w}" height="20" rx="3"/></clipPath><g clip-path="url(#r)"><rect width="${lw}" height="20" fill="#4B2E83"/><rect x="${lw}" width="${vw}" height="20" fill="${color}"/></g><g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11"><text x="${lw / 2}" y="14">${esc(label)}</text><text x="${lw + vw / 2}" y="14">${esc(value)}</text></g></svg>`;
}
app.get("/v1/badge/policy", async (c) => {
  const domain = normaliseDomain(c.req.query("domain"));
  const svg = (v: string, col: string, ttl = 86400) => c.body(badgeSvg("AI policy", v, col), 200, { "Content-Type": "image/svg+xml; charset=utf-8", "Cache-Control": `public, max-age=${ttl}` });
  if (!domain) return svg("give ?domain=", "#5E5873", 60);
  let res: any = await checkCached(c.env, domain, false);
  if (!res) {
    if (await limited(c)) return svg("try again shortly", "#5E5873", 60);
    res = await checkCached(c.env, domain, true);
  }
  const s = res.summary ?? {};
  if (res.robots?.state === "unreachable") return svg("robots.txt unreachable", "#5E5873", 3600);
  const priced = s.machine_readable_price ? " · priced" : " · no price";
  return svg(`blocks ${s.blocked}/${s.ai_bots_checked} AI bots${priced}`, s.machine_readable_price ? "#1E6B45" : s.blocked > 0 ? "#7A5E00" : "#5E5873");
});

// ORDER_013 next step: on-demand x402 endpoint self-check (the daily monitor's test, for one URL a visitor pastes).
// Unpaid, one request, no redirects followed, 10 s, 64 KB, public hostnames only, 30 checks/min/client, and each URL is
// cached for 10 minutes so the tool can't be used to hammer an endpoint.
const PROBE_UA = "wknipe-x402-status/1.0 (+https://wknipe.com/x402/status/; on-demand check requested by a visitor)";
function parseAccepts(status: number, headers: Headers, body: string) {
  const pr = headers.get("payment-required");
  if (pr) { try { const j = JSON.parse(atob(pr)); return { version: j.x402Version ?? 2, accepts: Array.isArray(j.accepts) ? j.accepts : [], resource: j.resource ?? null }; } catch {} }
  try { const j = JSON.parse(body); if (j && Array.isArray(j.accepts)) return { version: j.x402Version ?? 1, accepts: j.accepts, resource: null }; } catch {}
  return { version: null, accepts: [] as any[], resource: null };
}
app.get("/v1/probe", async (c) => {
  const raw = (c.req.query("url") ?? "").trim();
  const method = (c.req.query("method") ?? "GET").toUpperCase();
  let u: URL;
  try { u = new URL(raw); } catch { return c.json({ error: "give a full URL, e.g. ?url=https://api.example.com/paid" }, 400); }
  if (!["https:", "http:"].includes(u.protocol) || !normaliseDomain(u.hostname) || u.port || u.username) return c.json({ error: "public http(s) URLs on standard ports only" }, 400);
  if (!["GET", "POST"].includes(method)) return c.json({ error: "method must be GET or POST" }, 400);
  const key = `probe:v1:${method}:${u.toString()}`.slice(0, 480);
  const hit = await c.env.CHECK_CACHE.get(key, "json");
  if (hit) return c.json({ ...(hit as object), cached: true });
  if (await limited(c)) return c.json({ error: "rate limit: 30 checks a minute; try again shortly" }, 429);
  const t0 = Date.now();
  let out: any = { url: u.toString(), method, checked_at: new Date().toISOString(), user_agent: PROBE_UA };
  try {
    const r = await fetch(u.toString(), { method, redirect: "manual", body: method === "POST" ? "{}" : undefined,
      headers: { "User-Agent": PROBE_UA, Accept: "application/json", ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
      signal: AbortSignal.timeout(10000) } as RequestInit);
    out.latency_ms = Date.now() - t0; out.status = r.status;
    let body = "";
    if (r.body) { const buf = await new Response(r.body).arrayBuffer(); body = new TextDecoder().decode(buf.slice(0, 65536)); }
    if (r.status >= 300 && r.status < 400) out.redirect = r.headers.get("location");
    const p = r.status === 402 ? parseAccepts(r.status, r.headers, body) : { version: null, accepts: [] as any[], resource: null };
    const good = p.accepts.filter((a: any) => a && a.scheme && a.network && a.payTo && (a.amount || a.maxAmountRequired));
    out.x402_version = p.version; out.valid_402 = r.status === 402 && good.length > 0;
    out.accepts = good.slice(0, 10).map((a: any) => ({ scheme: a.scheme, network: a.network, asset: a.asset, amount: a.amount ?? a.maxAmountRequired, payTo: a.payTo, description: typeof a.description === "string" ? a.description.slice(0, 200) : undefined }));
    out.problems = [
      ...(r.status !== 402 ? [`answered HTTP ${r.status}, not 402 Payment Required`] : []),
      ...(r.status === 402 && !p.accepts.length ? ["402 without a parseable accepts list (no PAYMENT-REQUIRED header or JSON body with accepts)"] : []),
      ...(p.accepts.length && good.length < p.accepts.length ? [`${p.accepts.length - good.length} accepts entries miss scheme, network, payTo or amount`] : []),
    ];
  } catch (e: any) {
    out.latency_ms = Date.now() - t0; out.status = 0; out.valid_402 = false; out.error = e?.name === "TimeoutError" ? "timeout after 10 s" : "unreachable"; out.problems = [out.error];
  }
  await c.env.CHECK_CACHE.put(key, JSON.stringify(out), { expirationTtl: 600 });
  return c.json({ ...out, cached: false }, 200, { "Cache-Control": "no-store" });
});

app.get("/v1/latest", (c) => c.json({ ...data.latest, data_built_at: data.built_at }));
app.get("/v1/method", (c) => c.json(data.method));
app.get("/v1/metrics", (c) =>
  c.json({ docs: "https://wknipe.com/api/", metrics: Object.fromEntries(Object.entries((data as any).metrics ?? {}).map(([k, v]: [string, any]) => [k, { about: v.about, rows: v.rows.length, source: v.source, url: `https://api.wknipe.com/v1/series?metric=${k}` }])) }, 200, { "Cache-Control": "public, max-age=3600" }),
);
app.get("/v1/series", (c) => {
  const metric = c.req.query("metric");
  if (metric) {
    const m = (data as any).metrics?.[metric];
    if (!m) return c.json({ error: "unknown metric", metrics: Object.keys((data as any).metrics ?? {}) }, 404);
    let rows = m.rows as any[];
    const week = c.req.query("week"), category = c.req.query("category");
    if (week) rows = rows.filter((r) => r.week_start === week || r.cohort_week === week);
    if (category) rows = rows.filter((r) => r.category === category);
    return c.json({ metric, about: m.about, source: m.source, licence: "CC BY 4.0, cite wknipe.com", data_built_at: data.built_at, rows }, 200, { "Cache-Control": "public, max-age=3600" });
  }
  const stage = c.req.query("stage") ?? "clean";
  const category = c.req.query("category") ?? "all";
  if (!STAGES.includes(stage) || !CATEGORIES.includes(category)) return c.json({ error: "bad stage or category", STAGES, CATEGORIES }, 400);
  return c.json({
    stage, category,
    weekly: data.weekly.filter((r: any) => r.stage === stage && r.category === category),
    prices: data.prices.filter((r: any) => r.category === category),
  });
});
app.get("/v1/sellers", (c) => {
  const category = c.req.query("category") ?? "all";
  const n = Math.max(1, Math.min(200, Number(c.req.query("n") ?? 20) || 20));
  if (!CATEGORIES.includes(category)) return c.json({ error: "bad category", CATEGORIES }, 400);
  return c.json(data.sellers.filter((r: any) => category === "all" || r.category === category).slice(0, n));
});

export default app;
