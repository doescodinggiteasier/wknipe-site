// ORDER_012 Build 1: AI-policy checker. GET /v1/check?domain=example.com
//
// What a site tells AI crawlers, read from the files it publishes for machines:
//   robots.txt (per named AI crawler: blocked / allowed / partly blocked, RFC 9309 matching), Content-Signal lines,
//   RSL `License:` links (+ the payment terms in that one declared license file), /.well-known/tdmrep.json, /llms.txt,
//   and one GET of / to see whether the site answers an identified crawler with HTTP 402 or a pay-per-crawl price.
// Politeness: an honest, identified user agent; only those files; 6 s timeout each; bodies capped; no spoofing.
// Privacy: nothing about the requester is stored or logged. Results are cached per domain for 24 h.

export const CHECK_UA = "wknipe-policy-check/1.0 (+https://wknipe.com/check/)";
const TIMEOUT_MS = 6000;
const MAX_BYTES = 512 * 1024;

// Named AI crawlers: product token, operator, what the operator says it is for.
export const AI_BOTS: { token: string; operator: string; purpose: "training" | "search" | "user" | "dataset" | "mixed" }[] = [
  { token: "GPTBot", operator: "OpenAI", purpose: "training" },
  { token: "OAI-SearchBot", operator: "OpenAI", purpose: "search" },
  { token: "ChatGPT-User", operator: "OpenAI", purpose: "user" },
  { token: "ClaudeBot", operator: "Anthropic", purpose: "training" },
  { token: "Claude-SearchBot", operator: "Anthropic", purpose: "search" },
  { token: "Claude-User", operator: "Anthropic", purpose: "user" },
  { token: "anthropic-ai", operator: "Anthropic (legacy token)", purpose: "training" },
  { token: "Google-Extended", operator: "Google", purpose: "training" },
  { token: "Google-CloudVertexBot", operator: "Google", purpose: "user" },
  { token: "Applebot-Extended", operator: "Apple", purpose: "training" },
  { token: "PerplexityBot", operator: "Perplexity", purpose: "search" },
  { token: "Perplexity-User", operator: "Perplexity", purpose: "user" },
  { token: "Meta-ExternalAgent", operator: "Meta", purpose: "training" },
  { token: "Meta-ExternalFetcher", operator: "Meta", purpose: "user" },
  { token: "CCBot", operator: "Common Crawl", purpose: "dataset" },
  { token: "Bytespider", operator: "ByteDance", purpose: "training" },
  { token: "Amazonbot", operator: "Amazon", purpose: "mixed" },
  { token: "cohere-ai", operator: "Cohere", purpose: "user" },
  { token: "cohere-training-data-crawler", operator: "Cohere", purpose: "training" },
  { token: "MistralAI-User", operator: "Mistral", purpose: "user" },
  { token: "DuckAssistBot", operator: "DuckDuckGo", purpose: "search" },
  { token: "AI2Bot", operator: "Allen Institute for AI", purpose: "training" },
  { token: "Diffbot", operator: "Diffbot", purpose: "dataset" },
  { token: "YouBot", operator: "You.com", purpose: "search" },
  { token: "Timpibot", operator: "Timpi", purpose: "dataset" },
];

// ---------- domain validation ----------
const BAD_SUFFIX = /\.(local|localhost|internal|intranet|lan|home|corp|test|invalid|example|arpa|onion)$/;

export function normaliseDomain(input: string | undefined | null): string | null {
  if (!input) return null;
  let s = input.trim().toLowerCase();
  if (!s || s.length > 300) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//.test(s)) s = "https://" + s;
  let u: URL;
  try { u = new URL(s); } catch { return null; }
  if (u.port || u.username || u.password) return null;
  const h = u.hostname.replace(/\.$/, "");
  if (h.length > 253 || !h.includes(".")) return null;
  if (/^[0-9.]+$/.test(h) || h.includes(":") || h.startsWith("[")) return null; // no IP literals
  if (BAD_SUFFIX.test(h) || h === "localhost") return null;
  if (!h.split(".").every((l) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(l))) return null;
  if (!/[a-z]/.test(h.split(".").pop()!)) return null;
  return h;
}

const base = (h: string) => h.replace(/^www\./, "");

// ---------- polite fetch ----------
type Got = { url: string; status: number; headers: Headers; body: string; error?: string; redirected_to?: string };

async function politeFetch(url: string, root: string, opts: { method?: string; accept?: string; maxBytes?: number } = {}): Promise<Got> {
  let current = url;
  for (let hop = 0; hop < 4; hop++) {
    let r: Response;
    try {
      r = await fetch(current, {
        method: opts.method ?? "GET", redirect: "manual",
        headers: { "User-Agent": CHECK_UA, Accept: opts.accept ?? "*/*" },
        signal: AbortSignal.timeout(TIMEOUT_MS),
        cf: { cacheTtl: 0 },
      } as RequestInit);
    } catch (e: any) {
      return { url: current, status: 0, headers: new Headers(), body: "", error: e?.name === "TimeoutError" ? "timeout" : "unreachable" };
    }
    if (r.status >= 300 && r.status < 400 && r.headers.get("location")) {
      let next: URL;
      try { next = new URL(r.headers.get("location")!, current); } catch { return { url: current, status: r.status, headers: r.headers, body: "", error: "bad redirect" }; }
      // Follow only within the same site (www / subdomains of the domain asked about), http->https allowed.
      const nh = next.hostname;
      if (!["http:", "https:"].includes(next.protocol) || !(base(nh) === base(root) || nh.endsWith("." + base(root)))) {
        return { url: current, status: r.status, headers: r.headers, body: "", redirected_to: next.toString(), error: "redirects off-site (not followed)" };
      }
      await r.body?.cancel();
      current = next.toString();
      continue;
    }
    let body = "";
    if ((opts.method ?? "GET") === "GET" && r.body) {
      const reader = r.body.getReader();
      const chunks: Uint8Array[] = [];
      let n = 0;
      const cap = opts.maxBytes ?? MAX_BYTES;
      while (n < cap) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value); n += value.length;
      }
      await reader.cancel().catch(() => {});
      const all = new Uint8Array(Math.min(n, cap));
      let off = 0;
      for (const c of chunks) { const take = Math.min(c.length, all.length - off); all.set(c.subarray(0, take), off); off += take; if (off >= all.length) break; }
      body = new TextDecoder("utf-8", { fatal: false }).decode(all);
    }
    return { url: current, status: r.status, headers: r.headers, body };
  }
  return { url: current, status: 0, headers: new Headers(), body: "", error: "too many redirects" };
}

const looksHtml = (g: Got) => /text\/html/i.test(g.headers.get("content-type") ?? "") || /^\s*<(!doctype|html|head|body)/i.test(g.body);

// ---------- robots.txt (RFC 9309) ----------
type Rule = { allow: boolean; path: string };
type Group = { agents: string[]; rules: Rule[]; signals: string[] };

export function parseRobots(text: string) {
  const groups: Group[] = [];
  const licenses: string[] = [];
  const signals: { agents: string[]; value: string }[] = [];
  const sitemaps: string[] = [];
  let g: Group | null = null;
  let inRules = false;
  for (const raw of text.split(/\r\n|\r|\n/)) {
    const line = raw.replace(/#.*$/, "").trim();
    const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/);
    if (!m) continue;
    const k = m[1].toLowerCase(), v = m[2].trim();
    if (k === "user-agent") {
      if (!g || inRules) { g = { agents: [], rules: [], signals: [] }; groups.push(g); inRules = false; }
      g.agents.push(v.toLowerCase());
    } else if (k === "allow" || k === "disallow") {
      if (!g) continue;
      inRules = true;
      g.rules.push({ allow: k === "allow", path: v });
    } else if (k === "content-signal") {
      signals.push({ agents: g ? [...g.agents] : ["*"], value: v });
      if (g) g.signals.push(v);
    } else if (k === "license") {
      licenses.push(v);
    } else if (k === "sitemap") {
      sitemaps.push(v);
    }
  }
  return { groups, licenses, signals, sitemaps };
}

function patternMatches(pattern: string, path: string): boolean {
  if (pattern === "") return false;
  const anchored = pattern.endsWith("$");
  const body = anchored ? pattern.slice(0, -1) : pattern;
  const re = "^" + body.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + (anchored ? "$" : "");
  return new RegExp(re).test(path);
}

// Is `path` allowed for `token` under these groups? Longest matching rule wins; ties go to allow (RFC 9309 §2.2.2).
export function evaluate(groups: Group[], token: string, path = "/") {
  const t = token.toLowerCase();
  let matched = groups.filter((g) => g.agents.includes(t));
  const via = matched.length ? "named" : "*";
  if (!matched.length) matched = groups.filter((g) => g.agents.includes("*"));
  const rules = matched.flatMap((g) => g.rules);
  let best: Rule | null = null;
  for (const r of rules) {
    if (!patternMatches(r.path, path)) continue;
    if (!best || r.path.length > best.path.length || (r.path.length === best.path.length && r.allow && !best.allow)) best = r;
  }
  const allowed = !best || best.allow;
  const someDisallowed = rules.some((r) => !r.allow && r.path !== "");
  return {
    status: !allowed ? "blocked" : someDisallowed ? "partial" : "allowed",
    via: matched.length ? via : "none",
    rule: best ? `${best.allow ? "Allow" : "Disallow"}: ${best.path}` : null,
  };
}

// ---------- Content-Signal ----------
function parseSignal(v: string) {
  const out: Record<string, string> = {};
  for (const part of v.split(",")) {
    const [k, val] = part.split("=").map((x) => x?.trim().toLowerCase());
    if (k && val) out[k] = val;
  }
  return out;
}

// ---------- RSL (Really Simple Licensing 1.0) ----------
function parseRsl(xml: string) {
  const payments: { type: string; amount?: string; currency?: string }[] = [];
  const re = /<payment\b([^>]*)>([\s\S]*?)<\/payment>|<payment\b([^>]*)\/>/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(xml)) && payments.length < 20) {
    const attrs = m[1] ?? m[3] ?? "";
    const type = attrs.match(/type\s*=\s*["']([^"']+)["']/i)?.[1] ?? "unspecified";
    const inner = m[2] ?? "";
    const am = inner.match(/<amount\b([^>]*)>\s*([^<\s]+)\s*<\/amount>/i);
    payments.push({ type, amount: am?.[2], currency: am?.[1].match(/currency\s*=\s*["']([^"']+)["']/i)?.[1] });
  }
  const permits = [...xml.matchAll(/<permits\b[^>]*>([^<]*)<\/permits>/gi)].map((x) => x[1].trim()).filter(Boolean).slice(0, 10);
  const prohibits = [...xml.matchAll(/<prohibits\b[^>]*>([^<]*)<\/prohibits>/gi)].map((x) => x[1].trim()).filter(Boolean).slice(0, 10);
  return { is_rsl: /<rsl\b/i.test(xml), payments, permits, prohibits };
}

// ---------- 402 / pay-per-crawl ----------
function decodeB64Json(s: string | null) {
  if (!s) return null;
  try { return JSON.parse(atob(s)); } catch { return null; }
}

function paymentSignals(g: Got) {
  const h = g.headers;
  const x402 = decodeB64Json(h.get("payment-required")) ?? (g.status === 402 ? (() => { try { return JSON.parse(g.body); } catch { return null; } })() : null);
  const accepts = Array.isArray(x402?.accepts) ? x402.accepts.slice(0, 5).map((a: any) => ({
    scheme: a.scheme, network: a.network, amount: a.amount ?? a.maxAmountRequired, asset: a.asset, payTo: a.payTo,
  })) : null;
  return {
    status: g.status,
    http_402: g.status === 402,
    crawler_price: h.get("crawler-price"),           // Cloudflare pay per crawl
    crawler_charged: h.get("crawler-charged"),
    x402_accepts: accepts,                            // x402 (v2 PAYMENT-REQUIRED header, or v1 JSON body)
  };
}

function htmlMeta(html: string) {
  const head = html.slice(0, 200_000);
  const meta = (name: string) => head.match(new RegExp(`<meta[^>]+name=["']${name}["'][^>]*content=["']([^"']*)["']`, "i"))?.[1]
    ?? head.match(new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*name=["']${name}["']`, "i"))?.[1] ?? null;
  const rslLink = head.match(/<link[^>]+type=["']application\/rsl\+xml["'][^>]*>/i)?.[0]?.match(/href=["']([^"']+)["']/i)?.[1] ?? null;
  return { robots: meta("robots"), tdm_reservation: meta("tdm-reservation"), tdm_policy: meta("tdm-policy"), rsl_link: rslLink };
}

// ---------- the check ----------
export async function runCheck(domain: string) {
  const root = `https://${domain}`;
  const [robots, tdm, llms, home] = await Promise.all([
    politeFetch(`${root}/robots.txt`, domain, { accept: "text/plain" }),
    politeFetch(`${root}/.well-known/tdmrep.json`, domain, { accept: "application/json", maxBytes: 128 * 1024 }),
    politeFetch(`${root}/llms.txt`, domain, { accept: "text/plain, text/markdown", maxBytes: 64 * 1024 }),
    politeFetch(`${root}/`, domain, { accept: "text/html" }),
  ]);

  // robots.txt
  const robotsOk = robots.status >= 200 && robots.status < 300 && !looksHtml(robots);
  const parsed = robotsOk ? parseRobots(robots.body) : { groups: [], licenses: [], signals: [], sitemaps: [] };
  let robotsState: string;
  if (robotsOk) robotsState = "found";
  else if (robots.status >= 500 || robots.status === 0) robotsState = "unreachable"; // RFC 9309: crawlers assume full disallow
  else robotsState = "none"; // 4xx or an HTML page: crawlers may crawl everything
  const bots = AI_BOTS.map((b) => {
    if (robotsState === "unreachable") return { ...b, status: "blocked", via: "unreachable", rule: null };
    if (robotsState === "none") return { ...b, status: "allowed", via: "none", rule: null };
    return { ...b, ...evaluate(parsed.groups, b.token) };
  });
  const star = robotsState === "found" ? evaluate(parsed.groups, "*") : null;

  // RSL: licence links in robots.txt or the homepage <link>; fetch the first one (the only extra file we read).
  const meta = home.status === 200 && looksHtml(home) ? htmlMeta(home.body) : { robots: null, tdm_reservation: null, tdm_policy: null, rsl_link: null };
  const rslLinks = [...parsed.licenses];
  if (meta.rsl_link) { try { rslLinks.push(new URL(meta.rsl_link, root).toString()); } catch {} }
  let rsl: any = { found: rslLinks.length > 0, links: rslLinks.slice(0, 5) };
  if (rslLinks.length) {
    let u: URL | null = null;
    try { u = new URL(rslLinks[0], root); } catch {}
    if (u && (u.protocol === "https:" || u.protocol === "http:") && normaliseDomain(u.hostname)) {
      const lic = await politeFetch(u.toString(), u.hostname, { accept: "application/rsl+xml, application/xml, text/xml", maxBytes: 256 * 1024 });
      rsl.fetched = { url: lic.url, status: lic.status, error: lic.error, ...(lic.status === 200 ? parseRsl(lic.body) : {}) };
    }
  }

  // TDMRep
  let tdmrep: any = { found: false, status: tdm.status };
  if (tdm.status === 200 && !looksHtml(tdm)) {
    try {
      const j = JSON.parse(tdm.body);
      const arr = Array.isArray(j) ? j : [j];
      tdmrep = { found: true, status: 200, rules: arr.slice(0, 10).map((r: any) => ({ location: r.location, reservation: r["tdm-reservation"], policy: r["tdm-policy"] })) };
    } catch { tdmrep = { found: false, status: 200, error: "not valid JSON" }; }
  }

  // llms.txt
  const llmsOk = llms.status === 200 && !looksHtml(llms) && llms.body.trim().length > 0;
  const llmsTxt = { found: llmsOk, status: llms.status, bytes: llmsOk ? llms.body.length : 0, title: llmsOk ? (llms.body.match(/^#\s+(.+)$/m)?.[1]?.slice(0, 120) ?? null) : null };

  // Content-Signal
  const contentSignal = { found: parsed.signals.length > 0, lines: parsed.signals.slice(0, 10).map((s) => ({ ...s, parsed: parseSignal(s.value) })) };

  const pay = paymentSignals(home);
  const blocked = bots.filter((b) => b.status === "blocked").length;
  const partial = bots.filter((b) => b.status === "partial").length;
  const priced = pay.http_402 || !!pay.crawler_price || !!pay.x402_accepts || (rsl.fetched?.payments ?? []).some((p: any) => p.amount);

  return {
    domain, checked_at: new Date().toISOString(), user_agent: CHECK_UA,
    summary: {
      ai_bots_checked: bots.length, blocked, partial, allowed: bots.length - blocked - partial,
      default_for_other_bots: star?.status ?? (robotsState === "unreachable" ? "blocked" : "allowed"),
      content_signal: contentSignal.found, rsl: rsl.found, tdmrep: tdmrep.found, llms_txt: llmsTxt.found,
      machine_readable_price: priced,
    },
    robots: { state: robotsState, status: robots.status, url: robots.url, error: robots.error, bytes: robots.body.length, groups: parsed.groups.length, sitemaps: parsed.sitemaps.length, bots },
    content_signal: contentSignal,
    rsl,
    tdmrep,
    llms_txt: llmsTxt,
    homepage: { ...pay, url: home.url, error: home.error, redirected_to: home.redirected_to, x_robots_tag: home.headers.get("x-robots-tag"), meta },
  };
}

export const EXAMPLES = ["nytimes.com", "theguardian.com", "bbc.co.uk", "reuters.com", "wsj.com", "washingtonpost.com",
  "economist.com", "ft.com", "medium.com", "wikipedia.org"];
