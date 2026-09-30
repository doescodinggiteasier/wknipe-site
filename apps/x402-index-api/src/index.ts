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
app.use("/v1/series", (c, next) => paywall(c.env)(c, next));
app.use("/v1/sellers", (c, next) => paywall(c.env)(c, next));

app.get("/", (c) =>
  c.json({
    name: "x402 Clean Index API",
    docs: "https://wknipe.com/x402/",
    free: ["/v1/latest", "/v1/method", "/v1/check?domain=example.com", "/v1/check/examples"],
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

app.get("/v1/latest", (c) => c.json({ ...data.latest, data_built_at: data.built_at }));
app.get("/v1/method", (c) => c.json(data.method));
app.get("/v1/series", (c) => {
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
