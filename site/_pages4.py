"""Pre-render, ORDER_013 Phases 4-5: endpoint status, State of AI access, This week in x402, badges, OG images.
Called from _pages.build(d)."""
import csv, datetime as dt, glob, hashlib, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from _wk import *  # noqa: E402,F401
from _pages import D, rcsv, rjson, write, f, GLOSSARY  # noqa: E402


# ------------------------------------------------------------------ endpoint status
def status_page(d):
    S = d.status
    if not S:
        write('status.md', md(decide('I check every listed x402 endpoint, unpaid, to see whether it answers with a valid payment request. Here are the results.') + '<p>The first daily check has not run yet.</p>')); return
    daily = rcsv(D('x402_status', 'status_daily.csv'))
    last = {r['scope']: r for r in daily if r['date'] == S['latest_day']}
    a, p = last.get('all', {}), last.get('priority', {})
    sc = S.get('scope_latest') or {}
    names = {s['address']: s['label'] for s in d.sellers['sellers']}
    pages = {s['address'] for s in d.sellers['sellers']}
    buyers = {r['payee']: int(r['payers']) for r in d.payees if r['week_start'] == d.latest}
    up = rcsv(D('x402_status', 'seller_uptime.csv'))
    urows = []
    for r in up:
        q = r['pay_to']; v = f(r['valid_402_share'])
        urows.append({'seller': seller_cell(q, names.get(q), page=q in pages), 'seller_s': (names.get(q) or q).lower(), 'seller_t': names.get(q) or q, 'address': q,
                      'buyers': buyers.get(q, 0), 'endpoints': int(r['endpoints_7d']), 'checks': int(r['checks_7d']), 'valid': v,
                      'state': 'answers' if v >= 0.9 else 'partly' if v > 0 else 'fails',
                      'badge': f'<a href="/badges/status/{q}.svg"><img src="/badges/status/{q}.svg" alt="402 status badge" height="20" loading="lazy"></a>', 'badge_s': v, 'badge_t': ''})
    lat = rcsv(D('x402_status', 'status_latest.csv'))
    erows = [{'endpoint': f'{esc(r["host"])}<span class="sub">{esc(r["method"])} {esc(r["resource"][len("https://") + len(r["host"]):][:70])}</span>', 'endpoint_t': r['resource'], 'endpoint_s': r['resource'],
              'date': r['date'], 'result': ('<span class="pill ok">valid 402</span>' if r['valid_402'] == 'True' else f'<span class="pill bad">{esc("HTTP " + r["status"] if r["status"] not in ("0", "") else (r["error"] or "no response").split(":")[0])}</span>'),
              'result_s': 1 if r['valid_402'] == 'True' else 0, 'result_t': 'valid 402' if r['valid_402'] == 'True' else ('HTTP ' + r['status'] if r['status'] not in ('0', '') else r['error']),
              'price': {'True': 'match', 'False': 'differs', '': '–'}[r['price_match']], 'payto': {'True': 'match', 'False': 'differs', '': '–'}[r['payto_match']],
              'latency': f(r['latency_ms']), 'priority': 'seller has buyers' if r['priority'] == 'True' else 'weekly rotation',
              'version': r['x402_version']} for r in lat]
    json.dump(erows, open(os.path.join(HERE, 'x402', 'data', 'status_endpoints.json'), 'w'), separators=(',', ':'))
    fails = S.get('failure_reasons_7d') or []
    fail_rows = [{'reason': k, 'value': v / max(1, S['endpoints_7d']), 'n': S['endpoints_7d'], 'k': v} for k, v in fails]
    json.dump({'fails': fail_rows, 'daily': [r for r in daily if r['scope'] == 'all']}, open(os.path.join(HERE, 'x402', 'data', 'status_charts.json'), 'w'))
    for r in [r for r in daily if r['scope'] == 'all']:
        r['valid_402'] = f(r['valid_402'])
    cards = [stat_card('Listings answering a valid 402', pct(f(a.get('valid_402'))), foot=f'{num(int(a.get("checked", 0)))} checked on {S["latest_day"]}', tip='Status 402 with a parseable x402 `accepts` list (v2 PAYMENT-REQUIRED header or v1 JSON body), for an unpaid request with the listing\'s method.'),
             stat_card('…of sellers with genuine buyers', pct(f(p.get('valid_402'))), foot=f'{num(int(p.get("checked", 0)))} endpoints', tip='Endpoints whose Base payTo had at least one genuine buyer in the latest index week.'),
             stat_card('Posted price matches the listing', pct(f(a.get('price_match_of_valid'))), foot='of valid 402s with a Base USDC price', tip='The Base USDC exact amount in the live 402 equals the amount in the Bazaar listing.'),
             stat_card('payTo matches the listing', pct(f(a.get('payto_match_of_valid'))), foot='of valid 402s', tip='The live 402 asks to be paid to the same address the listing names.'),
             stat_card('Median latency', f'{num(f(a.get("median_latency_ms")))} ms', foot=f'p90 {num(f(a.get("p90_latency_ms")))} ms', tip='Time to response headers from GitHub-hosted runners (or my Mac for the first run).')]
    top_fail = fails[0] if fails else None
    selfcheck = f'''<form id="probe-form" class="card-wk" style="display:grid;gap:10px;margin:0 0 28px" onsubmit="return false">
<label for="probe-url" style="font-weight:600">Check an endpoint now <span class="meta">(unpaid, one request, same test as the daily monitor)</span></label>
<div style="display:flex;gap:8px;flex-wrap:wrap"><input id="probe-url" type="search" placeholder="https://api.example.com/paid-endpoint" style="flex:1 1 320px" autocomplete="off">
<select id="probe-method" class="wk-select" aria-label="HTTP method"><option>GET</option><option>POST</option></select><button class="wk-btn" id="probe-go" type="submit">Check</button></div>
<div id="probe-out" aria-live="polite"></div></form>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  const f = document.getElementById("probe-form"), out = document.getElementById("probe-out"), esc = WK.esc;
  async function listingFor(u) {{
    try {{ const L = await WK.json("/x402/data/listings.json"); const ci = Object.fromEntries(L.cols.map((c, i) => [c, i]));
      const path = (u.pathname || "/").slice(0, 80);
      const r = L.rows.find((r) => r[ci.host] === u.hostname && r[ci.path] === path);
      return r ? {{ price: r[ci.price_usd], what: r[ci.what], seller: r[ci.seller] != null ? L.sellers[r[ci.seller]] : null, snapshot: L.snapshot }} : {{ snapshot: L.snapshot }};
    }} catch (e) {{ return null; }}
  }}
  f.addEventListener("submit", async () => {{
    const url = document.getElementById("probe-url").value.trim(), method = document.getElementById("probe-method").value;
    if (!url) return; out.innerHTML = '<p class="meta">Checking…</p>';
    let u; try {{ u = new URL(url); }} catch {{ out.innerHTML = '<p class="meta">Enter a full URL starting with https://</p>'; return; }}
    const [r, L] = await Promise.all([fetch("{API}/v1/probe?method=" + method + "&url=" + encodeURIComponent(url)).then((x) => x.json()), listingFor(u)]);
    if (r.error && r.status === undefined) {{ out.innerHTML = `<p class="meta">${{esc(r.error)}}</p>`; return; }}
    const checks = [[r.status > 0, `Responds (HTTP ${{r.status || "–"}}, ${{r.latency_ms}} ms)`], [r.valid_402, "Answers 402 with a valid x402 accepts list" + (r.x402_version ? ` (v${{r.x402_version}})` : "")]];
    const base = (r.accepts || []).filter((a) => a.network === "eip155:8453" || a.network === "base");
    if (L && L.price != null) checks.push([base.some((a) => a.scheme === "exact" && String(a.amount) === String(Math.round(L.price * 1e6))), `Price matches the Bazaar listing (${{WK.fmt.usdFull(L.price)}} per call, snapshot ${{L.snapshot}})`]);
    else checks.push([null, L ? `Not found in the Bazaar snapshot ${{L.snapshot}} (listed endpoints appear on the Price comps page)` : "Bazaar listing not loaded"]);
    if (L && L.seller) checks.push([(r.accepts || []).some((a) => String(a.payTo).toLowerCase() === L.seller[0]), "payTo matches the listing"]);
    const icon = (ok) => ok === null ? '<span class="pill">n/a</span>' : ok ? '<span class="pill ok">pass</span>' : '<span class="pill bad">fail</span>';
    out.innerHTML = `<ul style="list-style:none;padding:0;margin:0;display:grid;gap:6px">${{checks.map(([ok, t]) => `<li>${{icon(ok)}} ${{esc(t)}}</li>`).join("")}}</ul>`
      + (r.problems && r.problems.length ? `<p class="meta" style="margin-top:8px">${{esc(r.problems.join(" · "))}}</p>` : "")
      + (r.accepts && r.accepts.length ? `<pre style="margin-top:8px"><code>${{esc(JSON.stringify(r.accepts, null, 1))}}</code></pre>` : "")
      + (L && L.seller && L.seller[3] ? `<p><a href="/x402/sellers/${{L.seller[0]}}">Seller page →</a> · badge: <code>https://wknipe.com/badges/status/${{L.seller[0]}}.svg</code></p>` : "")
      + `<p class="meta">${{r.cached ? "Cached result from the last 10 minutes. " : ""}}User agent: ${{esc(r.user_agent || "")}}</p>`;
  }});
}});
</script>'''
    out = [decide('Every day I send each listed x402 endpoint one unpaid request and record whether it answers with a valid 402, and whether the price and address match its listing. Here are the results, by seller and by endpoint, plus a box to check one yourself.'),
           freshness(S['latest_day'], 'checked daily', stale_days=3), selfcheck, kpis(cards),
           chart_frame('failures', f'{pct(1 - f(a.get("valid_402") or 0))} of checked listings do not answer a valid 402' + (f'; the most common failure is {esc(top_fail[0])}' if top_fail else ''),
                       f'Endpoints checked in the last 7 days whose latest check failed, by reason. Denominator: {num(S["endpoints_7d"])} endpoints checked.',
                       'bars', '/x402/data/status_charts.json', {'path': 'fails', 'label': 'reason', 'value': 'value', 'pct': True, 'labelName': 'Failure', 'valueName': 'Share of endpoints checked'},
                       csv='/x402/data/status_latest.csv', metric='status_daily', through=S['latest_day'], page='/x402/status/'),
           (chart_frame('trend', 'Share of checked listings answering a valid 402, per day', 'All endpoints checked that day (sellers with buyers daily + one seventh of the rest).', 'line', '/x402/data/status_charts.json',
                        {'path': 'daily', 'x': 'date', 'y': 'valid_402', 'pct': True, 'label': 'Valid 402'}, csv='/x402/data/status_daily.csv', metric='status_daily', page='/x402/status/')
            if len({r['date'] for r in daily}) >= 2 else ''),
           '<h2 id="sellers">By seller</h2><p>Sellers with endpoints checked in the last 7 days. Each gets an embeddable status badge (see <a href="/badges/">badges</a>), which is a nice thing to have when it is green.</p>',
           data_table('uptime-table', [{'k': 'seller', 'label': 'Seller', 't': 'html'}, {'k': 'buyers', 'label': 'Genuine buyers', 't': 'int', 'r': 1}, {'k': 'endpoints', 'label': 'Endpoints checked', 't': 'int', 'r': 1},
                                       {'k': 'valid', 'label': 'Valid 402', 't': 'pct', 'r': 1}, {'k': 'state', 'label': 'State'}, {'k': 'badge', 'label': 'Badge', 't': 'html'}],
                      urows, facets=[{'k': 'state', 'labels': {'answers': 'Answers (≥90%)', 'partly': 'Partly', 'fails': 'Fails'}, 'order': ['answers', 'partly', 'fails']}], sort='buyers', page_size=25,
                      placeholder='Search seller or address', csv_name='seller_uptime.csv', search=['seller_t', 'address']),
           '<h2 id="endpoints">Endpoints</h2>',
           data_table('endpoint-table', [{'k': 'endpoint', 'label': 'Endpoint', 't': 'html'}, {'k': 'result', 'label': 'Result', 't': 'html'}, {'k': 'price', 'label': 'Price vs listing'},
                                         {'k': 'payto', 'label': 'payTo vs listing'}, {'k': 'latency', 'label': 'Latency ms', 't': 'int', 'r': 1}, {'k': 'date', 'label': 'Checked'}],
                      src='/x402/data/status_endpoints.json', facets=[{'k': 'priority', 'labels': {'seller has buyers': 'Seller has buyers', 'weekly rotation': 'Weekly rotation'}, 'order': ['seller has buyers', 'weekly rotation']}, {'k': 'price', 'order': ['match', 'differs', '–']}],
                      sort=None, page_size=25, placeholder='Search host or URL', csv_name='endpoint_status.csv', search=['endpoint_t', 'result_t']),
           f'''<h2 id="method">How it checks</h2><ul>
<li><b>Unpaid, one request per endpoint.</b> I never send a payment; I just ask the price. User agent: <code>{esc(S["user_agent"])}</code>. The listing's HTTP method (POST gets an empty JSON body), 10 s timeout, 64 KB read, ≤3 redirects.</li>
<li><b>Scope.</b> Sellers whose Base payTo had a genuine buyer in the latest index week: up to {sc.get("caps", {}).get("per_seller_daily", 5)} of their endpoints every day, rotating. Every other listing: once a week (one seventh a day).</li>
<li><b>Caps.</b> ≤{sc.get("caps", {}).get("per_host_daily", 60)} requests per host per day, one at a time with ≥1 s between them; ≤{num(sc.get("caps", {}).get("per_day", 4000))} requests per day in total. Latest run: {num(sc.get("priority_checked_today"))} priority + {num(sc.get("rotating_checked_today"))} rotating requests, of {num(sc.get("endpoints_listed"))} listed endpoints.</li>
<li><b>Valid 402</b> = HTTP 402 with a parseable <code>accepts</code> list whose entries name a scheme, network, payTo and amount. A listing that answers 200 without payment, 404, 405 or times out counts as not answering. Some endpoints need specific query parameters before they will quote a price; they show as failures here, which the per-seller rate smooths out.</li></ul>
<p class="meta">Data: <a href="/x402/data/status_daily.csv">status_daily.csv</a> · <a href="/x402/data/status_latest.csv">status_latest.csv</a> · <a href="/api/">API</a>. Sellers who would rather not be checked can say so: wes@wknipe.com.</p>''']
    write('status.md', md('\n'.join(x for x in out if x)))


# ------------------------------------------------------------------ AI access
def access_page(d):
    A = d.access
    if not A:
        write('access.md', md('<p>The first census has not run yet.</p>')); return
    L = A['latest']; sig = {s['signal']: s for s in A['signals']}
    b0 = A['bots'][0]
    anyb = sig['Blocks at least one AI crawler by name']; allt = sig['Blocks all 7 major training crawlers']; llms = sig['Publishes /llms.txt']
    p402 = sig['Answers my crawler with HTTP 402']; price = sig['States a machine-readable price']
    lat = rcsv(D('ai_access', 'access_latest.csv'))
    names402 = [r['domain'] for r in lat if r['http_402'] == 'True']
    json.dump({'bots': [{**b, 'label': b['bot']} for b in A['bots']], 'signals': A['signals']}, open(os.path.join(HERE, 'x402', 'data', 'access_charts.json'), 'w'))
    cards = [stat_card('Block ≥1 AI crawler by name', pct(anyb['share']), foot=f'{anyb["k"]} of {anyb["n"]} sites with a robots.txt', tip='A robots.txt group naming the crawler disallows the whole site.'),
             stat_card('Block all 7 training crawlers', pct(allt['share']), foot=f'{allt["k"]} of {allt["n"]}', tip='GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, Meta-ExternalAgent, CCBot and Bytespider all fully disallowed (by name or by *).'),
             stat_card('Publish /llms.txt', pct(llms['share']), foot=f'{llms["k"]} of {llms["n"]} sites', tip='A non-HTML /llms.txt file answering 200.'),
             stat_card('Answer an AI crawler with 402', f'{p402["k"]}', foot=', '.join(names402) or 'none', tip='My identified crawler got HTTP 402 Payment Required on the homepage.'),
             stat_card('State a machine-readable price', f'{price["k"]}', foot=f'of {price["n"]} sites', tip='A 402, a crawler-price header, an x402 accepts list, or a priced RSL licence.')]
    rows = [{'domain': f'<a href="/check/?domain={esc(r["domain"])}">{esc(r["domain"])}</a>', 'domain_t': r['domain'], 'domain_s': r['domain'], 'rank': int(r['rank']),
             'robots': r['robots'], 'named': int(r['ai_bots_blocked_by_name']), 'blocked': int(r['ai_bots_blocked']) if r['robots'] == 'found' else None,
             'signals': ' '.join(k for k in ('content_signal', 'rsl', 'tdmrep', 'llms_txt', 'http_402') if r[k] == 'True').replace('_', '-') or '–',
             'bots_t': r['blocked_bots']} for r in lat]
    out = [decide('Once a week I read the robots.txt and related files of the top 1,000 websites and record what each one tells AI crawlers, and whether any of them ask to be paid. Here is what they say.'),
           freshness(L['date'], 'updates weekly'), kpis(cards),
           chart_frame('bots', f'{b0["bot"]} is the most blocked AI crawler: {pct(b0["named_block"])} of top sites with a robots.txt block it by name',
                       f'Share of the Tranco top {num(L["checked"])} domains with a robots.txt ({num(L["robots_found"])}) whose rules name the crawler and disallow the whole site. {num(L["robots_unreachable"])} list entries are CDN, API or infrastructure hostnames with no reachable robots.txt; they are excluded.',
                       'bars', '/x402/data/access_charts.json', {'path': 'bots', 'label': 'bot', 'value': 'named_block', 'pct': True, 'labelName': 'Crawler', 'valueName': 'Blocked by name', 'top': 25, 'dp': 0},
                       csv='/x402/data/access_latest.csv', metric='access_weekly', through=L['date'], page='/access/'),
           chart_frame('signals', f'Pricing is almost absent: {price["k"]} of {price["n"]} top sites state a machine-readable price; {pct(llms["share"])} publish llms.txt',
                       'Adoption of machine-readable access signals among top sites that serve a website. Block rows use sites with a robots.txt as the denominator.',
                       'bars', '/x402/data/access_charts.json', {'path': 'signals', 'label': 'signal', 'value': 'share', 'pct': True, 'labelName': 'Signal', 'valueName': 'Share', 'dp': 1},
                       csv='/x402/data/access_weekly.csv', metric='access_weekly', through=L['date'], page='/access/'),
           '<h2 id="compare">Top sites vs the whole crawl</h2>',
           f'<p>My earlier Common Crawl census (CC-MAIN-2026-39, a 5% sample of robots.txt files, 2.67M hosts) measured the same rules across the whole web. <b>Method break:</b> that population is every crawled host, this one is the top 1,000 registrable domains; compare levels with care, and read the weekly series from {L["date"]} on as the consistent one.</p>',
           data_table('compare-table', [{'k': 'bot', 'label': 'Crawler'}, {'k': 'operator', 'label': 'Operator'}, {'k': 'purpose', 'label': 'Purpose'}, {'k': 'named_block', 'label': f'Top {num(L["checked"])}: blocked by name', 't': 'pct1', 'r': 1},
                                       {'k': 'cc_sample', 'label': 'Whole crawl (CC 5% sample)', 't': 'pct1', 'r': 1}], A['bots'], sort='named_block', page_size=30, csv_name='ai_crawler_blocks.csv',
                      facets=[{'k': 'purpose', 'labels': {'training': 'Training', 'search': 'Search', 'user': 'User-initiated', 'dataset': 'Dataset', 'mixed': 'Mixed'}, 'order': ['training', 'search', 'user', 'dataset', 'mixed']}]),
           '<h2 id="domains">Every domain</h2>',
           data_table('domains-table', [{'k': 'rank', 'label': 'Tranco rank', 't': 'int', 'r': 1}, {'k': 'domain', 'label': 'Domain', 't': 'html'}, {'k': 'robots', 'label': 'robots.txt'},
                                        {'k': 'named', 'label': 'AI crawlers blocked by name', 't': 'int', 'r': 1}, {'k': 'signals', 'label': 'Signals'}],
                      rows, facets=[{'k': 'robots', 'labels': {'found': 'Has robots.txt', 'none': 'No robots.txt', 'unreachable': 'Unreachable'}, 'order': ['found', 'none', 'unreachable']}], sort='rank', dir='asc', page_size=25,
                      placeholder='Search domain or crawler', csv_name='ai_access_domains.csv', search=['domain_t', 'bots_t', 'signals']),
           f'<p class="meta">Method: the <a href="/check/">AI-policy checker</a>\'s code (RFC 9309 matching, 25 named crawlers) run over the <a href="https://tranco-list.eu/list/{esc(L["tranco_list_id"])}">Tranco list {esc(L["tranco_list_id"])}</a> ({esc(L["tranco_created_on"][:10])}), weekly. '
           f'About {num(L["requests_approx"])} requests this run: robots.txt, /.well-known/tdmrep.json, /llms.txt and / per domain (plus one declared RSL licence), 6 s timeouts, identified user agent, no retries. Data: <a href="/x402/data/access_weekly.csv">access_weekly.csv</a> · <a href="/x402/data/access_latest.csv">access_latest.csv</a>.</p>']
    write('access.md', md('\n'.join(out)))


# ------------------------------------------------------------------ This week in x402 (auto, numbers only)
def weekly_posts(d):
    wd = os.path.join(HERE, 'weekly')
    os.makedirs(wd, exist_ok=True)
    for p in glob.glob(os.path.join(wd, '20??-??-??.qmd')): os.remove(p)
    M = d.market; W = d.weeks
    names = {s['address']: s['label'] for s in d.sellers['sellers']}
    for i, w in enumerate(W):
        prev = W[i - 1] if i else None
        g = lambda st, c='all', k='usd': growth(d.w(prev, st, c, k), d.w(w, st, c, k)) if prev else None
        raw, clean = d.w(w, 'raw', 'all'), d.w(w, 'clean', 'all')
        bw = next(r for r in M['buyers_weekly'] if r['week_start'] == w)
        cats = sorted(((c, d.w(w, 'clean', c)) for c in CATS), key=lambda x: -(x[1] or 0))
        cd = d.head['content_plus_data_clean_usd_by_week'].get(w)
        conc = next((r for r in M['concentration'] if r['week_start'] == w and r['category'] == 'all'), None)
        tk = next((r for r in M['tickets'] if r['week_start'] == w and r['category'] == 'all'), None)
        wf = {r['step']: r for r in M['waterfall'] if r['week_start'] == w}
        big = max((r for r in wf.values() if r['step'] != 'clean'), key=lambda r: r['usd'])
        movers = ''
        if i == len(W) - 1 and M['movers']:
            up = [m for m in M['movers'] if m['usd_change'] > 0][:3]; dn = sorted((m for m in M['movers'] if m['usd_change'] < 0), key=lambda m: m['usd_change'])[:3]
            nm = lambda m: names.get(m['payee']) or f"{m['payee'][:6]}…{m['payee'][-4:]}"
            movers = ('\n## Movers (sellers with 5+ genuine buyers)\n\n' + '\n'.join(f"- ▲ [{nm(m)}](/x402/sellers/{m['payee']}): {usd(m['usd_prev'])} → {usd(m['usd_now'])}" for m in up) + '\n'
                      + '\n'.join(f"- ▼ [{nm(m)}](/x402/sellers/{m['payee']}): {usd(m['usd_prev'])} → {usd(m['usd_now'])}" for m in dn) + '\n')
        lede_p = os.path.join(wd, 'ledes', f'{w}.md')
        lede = open(lede_p).read().strip() if os.path.exists(lede_p) else f'<!-- TODO(Wes): optional one-paragraph lede in your voice; save it as site/weekly/ledes/{w}.md and it appears here. -->'
        end = dt.date.fromisoformat(w) + dt.timedelta(days=6)
        chg = lambda x: f' ({signed_pct(x)} WoW)' if x is not None else ''
        body = f'''---
title: "This week in x402: {week_label(w)}–{end.strftime('%-d %b %Y')}"
date: "{(end + dt.timedelta(days=1)).isoformat()}"
description: "{usd(clean)} demand-cleaned of {usd(raw)} settled; {num(int(bw['active_buyers']))} genuine buyers; content + data {usd(cd)}."
categories: [x402, weekly]
---

{lede}

**{usd(clean)}** of **{usd(raw)}** settled over x402 on Base survived cleaning ({pct(clean / raw)}){chg(g('clean'))}. The biggest removal was {big['label'].lower()}: {usd(big['usd'])}.

| | This week | Change |
|---|--:|--:|
| Settled through facilitators | {usd(raw)} | {signed_pct(g('raw'))} |
| Demand-cleaned | {usd(clean)} | {signed_pct(g('clean'))} |
| Genuine buyers | {num(int(bw['active_buyers']))} | {signed_pct(growth(int(next(r for r in M['buyers_weekly'] if r['week_start'] == prev)['active_buyers']), int(bw['active_buyers'])) if prev else None)} |
| Active sellers (2+ buyers) | {num(d.w(w, 'clean', 'all', 'payees'))} | {signed_pct(g('clean', 'all', 'payees'))} |
| Content + data | {usd(cd)} | {signed_pct(growth(d.head['content_plus_data_clean_usd_by_week'].get(prev), cd) if prev else None)} |
| Top-10 seller share | {pct(conc['top10_share']) if conc else '–'} | |
| Median clean payment | {usd(tk['median_usd'], True) if tk else '–'} | |

**By category (demand-cleaned USD):** {' · '.join(f'{CAT_LABEL[c].split(" (")[0]} {usd(v)}' for c, v in cats if v)}.
{movers}
Numbers only, generated from the [x402 index](/x402/) data for the week of {week_label(w, True)}. Method: [X402_INDEX_METHOD.md]({METHOD}). Data CC BY 4.0.
'''
        open(os.path.join(wd, f'{w}.qmd'), 'w').write(body)


# ------------------------------------------------------------------ badges
def badge_svg(label, value, color):
    """Flat two-part badge (shields.io style), text measured roughly (6.5 px per char at 11px)."""
    lw = int(len(label) * 6.3 + 12); vw = int(len(value) * 6.6 + 12); w = lw + vw
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" aria-label="{esc(label)}: {esc(value)}"><title>{esc(label)}: {esc(value)}</title>'
            f'<clipPath id="r"><rect width="{w}" height="20" rx="3"/></clipPath><g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#3A3C44"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/></g>'
            f'<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11"><text x="{lw / 2}" y="14">{esc(label)}</text><text x="{lw + vw / 2}" y="14">{esc(value)}</text></g></svg>')


def badges(d):
    bd = os.path.join(HERE, 'badges')
    for sub in ('seller', 'status'):
        p = os.path.join(bd, sub)
        if os.path.isdir(p): shutil.rmtree(p)
        os.makedirs(p)
    lw = d.sellers['latest_week']
    for s in d.sellers['sellers']:
        L = s['latest']
        val = f"{usd(L['usd'])}/wk · {L['buyers']} buyers" if L else 'no clean volume this week'
        open(os.path.join(bd, 'seller', s['address'] + '.svg'), 'w').write(badge_svg('x402 clean volume', val, '#7A5E00' if L and L['buyers'] >= 5 else '#5F616A'))
    for r in rcsv(D('x402_status', 'seller_uptime.csv')):
        v = f(r['valid_402_share'])
        open(os.path.join(bd, 'status', r['pay_to'] + '.svg'), 'w').write(badge_svg('x402 status', f'402 OK {pct(v)} · 7d', '#1E6B45' if v >= 0.9 else '#7A5E00' if v > 0 else '#A3261E'))
    ex = next((s for s in d.sellers['sellers'] if s['qualifies_latest'] and s['label']), d.sellers['sellers'][0])
    q = ex['address']
    out = f'''{decide("Small SVG badges that show a seller's genuine volume, an endpoint's uptime, or a website's AI policy. They update themselves from the same public data as the rest of the site.")}
<p>Badges are plain SVG files, no scripts, no tracking. Seller and status badges are rebuilt from the public data every week and every day; the AI-policy badge is computed live by the API (cached 24 h).</p>
<div class="card-wk" style="display:grid;gap:12px;margin:16px 0 28px">
<label for="badge-q" style="font-weight:600">Seller address (0x…) or website domain</label>
<input id="badge-q" type="search" value="{q}" autocomplete="off">
<div id="badge-out"></div></div>
<h2>Seller: demand-cleaned volume</h2><p><img src="/badges/seller/{q}.svg" alt="x402 clean volume badge" height="20"> — demand-cleaned USD and genuine buyers last week, from the <a href="/x402/sellers/">seller leaderboard</a>.</p>
<pre><code>&lt;a href="https://wknipe.com/x402/sellers/{q}"&gt;&lt;img src="https://wknipe.com/badges/seller/{q}.svg" alt="x402 clean volume"&gt;&lt;/a&gt;</code></pre>
<h2>Endpoint: 402 status</h2><p>Share of the seller's endpoints that answered a valid 402 over the last 7 days of <a href="/x402/status/">daily checks</a>.</p>
<pre><code>&lt;img src="https://wknipe.com/badges/status/0xYOUR_PAYTO.svg" alt="x402 status"&gt;</code></pre>
<h2>Publisher: AI policy</h2><p>What your robots.txt tells AI crawlers and whether you state a price, from the <a href="/check/">AI-policy checker</a>. <img src="{API}/v1/badge/policy?domain=theguardian.com" alt="AI policy badge example" height="20"></p>
<pre><code>&lt;a href="https://wknipe.com/check/?domain=example.com"&gt;&lt;img src="{API}/v1/badge/policy?domain=example.com" alt="AI policy"&gt;&lt;/a&gt;</code></pre>
<script>
(function(){{const i=document.getElementById("badge-q"),o=document.getElementById("badge-out");
function r(){{const v=i.value.trim().toLowerCase();let src,href,alt;
if(/^0x[0-9a-f]{{40}}$/.test(v)){{src=`https://wknipe.com/badges/seller/${{v}}.svg`;href=`https://wknipe.com/x402/sellers/${{v}}`;alt="x402 clean volume";
 o.innerHTML=`<p><img src="/badges/seller/${{v}}.svg" alt="" height="20" onerror="this.replaceWith('No seller page for this address yet (needs 5+ genuine buyers in some week).')"> <img src="/badges/status/${{v}}.svg" alt="" height="20" onerror="this.remove()"></p>`;}}
else if(/^[a-z0-9.-]+\\.[a-z]{{2,}}$/.test(v)){{src=`{API}/v1/badge/policy?domain=${{v}}`;href=`https://wknipe.com/check/?domain=${{v}}`;alt="AI policy";o.innerHTML=`<p><img src="${{src}}" alt="" height="20"></p>`;}}
else {{o.innerHTML='<p class="meta">Enter a 0x address or a domain.</p>';return;}}
const snip=`<a href="${{href}}"><img src="${{src}}" alt="${{alt}}"></a>`;const md=`[![${{alt}}](${{src}})](${{href}})`;
o.insertAdjacentHTML("beforeend",`<pre><code>${{snip.replace(/</g,"&lt;")}}</code></pre><pre><code>${{md}}</code></pre>`);}}
i.addEventListener("input",r);r();}})();
</script>'''
    write('badges.md', md(out))


# ------------------------------------------------------------------ OG images (headline number per page)
def og_images(d):
    """1200x630 PNG per main page with its headline number, rendered by headless Chrome from an SVG. Skipped quietly
    when no Chrome is available (the committed PNGs stay)."""
    chrome = next((c for c in (os.environ.get('CHROME', ''), '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', shutil.which('google-chrome') or '', shutil.which('chromium') or '', shutil.which('chrome') or '') if c and os.path.exists(c)), None)
    og = os.path.join(HERE, 'og'); os.makedirs(og, exist_ok=True)
    M = d.market; lw = d.latest
    clean = d.w(lw, 'clean', 'all'); raw = d.w(lw, 'raw', 'all'); bw = M['buyers_weekly'][-1]
    P = d.prices; S = d.status; A = d.access
    pa = next((r for r in P.get('posted_by_category', []) if r['category'] == 'all'), {}) if P else {}
    cards = {
        'home': ('Agent payments, measured', usd(clean) + ' / week', f'demand-cleaned x402 spend of {usd(raw)} settled · {num(int(bw["active_buyers"]))} genuine buyers'),
        'market': ('x402 market', pct(clean / raw) + ' survives', f'of {usd(raw)} settled in the week of {week_label(lw)} after removing manufactured and single-buyer volume'),
        'sellers': ('x402 sellers', f'{sum(1 for s in d.sellers["sellers"] if s["qualifies_latest"])} sellers', 'with 5+ genuine buyers last week, ranked by demand-cleaned USD'),
        'buyers': ('x402 buyers', num(int(bw['active_buyers'])), f'genuine buyers in the week of {week_label(lw)} · {pct(int(bw["new_buyers"]) / int(bw["active_buyers"]))} new'),
        'prices': ('x402 prices', f'{usd(pa.get("median_usd"), True)} median ask' if pa.get('median_usd') else 'Posted prices', f'per call, across {num(pa.get("priced") or 0)} priced Bazaar listings'),
        'buy': ('Best execution', 'Cheapest verified', 'x402 endpoint for any task an agent needs done · ranked by price, 402 health and real buyers'),
        'brief': ('State of x402', usd(clean * 52) + ' / yr', 'demand-cleaned x402 spend, latest week × 52 · one printable page'),
        'comps': ('Price comps', f'{num(P.get("listings"))} listings', 'comparable x402 listings, their prices, and whether their sellers have buyers'),
    }
    if S:
        a = next((r for r in rcsv(D('x402_status', 'status_daily.csv')) if r['date'] == S['latest_day'] and r['scope'] == 'all'), None)
        if a: cards['status'] = ('x402 endpoint status', pct(f(a['valid_402'])), 'of checked listings answer a valid 402 · checked daily')
    if A:
        s = {x['signal']: x for x in A['signals']}
        cards['access'] = ('State of AI access', pct(s['Blocks at least one AI crawler by name']['share']), f'of top sites block an AI crawler by name · {s["States a machine-readable price"]["k"]} state a price')
    tmp = os.path.join(og, '_tmp'); os.makedirs(tmp, exist_ok=True)
    font = 'file://' + os.path.join(HERE, 'fonts', 'geist-latin-var.woff2')
    made = 0
    for k, (eyebrow, big, sub) in cards.items():
        html_s = f'''<!doctype html><html><head><meta charset="utf-8"><style>@font-face{{font-family:Plex;src:url("{font}") format("woff2");font-weight:100 700}}
html,body{{margin:0;width:1200px;height:630px;background:#F7F7F8;font-family:Plex,sans-serif;color:#141416}}
.w{{position:absolute;top:0;left:0;width:1200px;height:630px;padding:72px 80px;box-sizing:border-box;display:flex;flex-direction:column}}
.e{{font:600 26px Plex;color:#5F616A;letter-spacing:.1em;text-transform:uppercase}}.b{{font:600 124px/1.05 Plex;letter-spacing:-.04em;margin:40px 0 18px;color:#141416}}
.r{{width:120px;height:3px;background:#D4B860;margin-bottom:28px}}.s{{font:500 34px/1.35 Plex;color:#5F616A;max-width:1000px}}
.f{{margin-top:auto;display:flex;justify-content:space-between;font:600 28px Plex}}.f span:last-child{{color:#5F616A;font-weight:500}}</style></head>
<body><div class="w"><div class="e">{esc(eyebrow)}</div><div class="b">{esc(big)}</div><div class="r"></div><div class="s">{esc(sub)}</div><div class="f"><span>wknipe.com</span><span>Data through {esc(d.through)}</span></div></div></body></html>'''
        hp = os.path.join(tmp, f'{k}.html'); open(hp, 'w').write(html_s)
        if chrome:
            try:
                subprocess.run([chrome, '--headless=new', '--disable-gpu', *(['--no-sandbox'] if os.geteuid() == 0 else []), '--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1200,630',
                                f'--screenshot={os.path.join(og, k + ".png")}', 'file://' + hp], capture_output=True, timeout=60)
                made += 1
            except Exception as e:
                print('og image failed', k, e)
    shutil.rmtree(tmp, ignore_errors=True)
    return made


def price_feed(d):
    """RSS of posted-price changes from the daily Bazaar diff (newest 200)."""
    import email.utils
    rows = rcsv(D('bazaar_daily', 'price_changes.csv'))[-200:][::-1]
    items = ''.join(f"""<item><title>{esc(r['host'])}: {esc(r['what'] or r['resource'][:60])} {usd(f(r['old_usd']), True)} → {usd(f(r['new_usd']), True)}</title>
<link>https://wknipe.com/x402/prices/#price-changes</link><guid isPermaLink="false">{esc(r['date'] + '|' + r['resource'] + '|' + r['new_usd'])}</guid>
<pubDate>{email.utils.format_datetime(dt.datetime.fromisoformat(r['date'] + 'T12:00:00+00:00'))}</pubDate>
<description>{esc(r['resource'])} changed its posted price from {usd(f(r['old_usd']), True)} to {usd(f(r['new_usd']), True)} per call ({signed_pct(f(r['change']))}) between {esc(r['since'])} and {esc(r['date'])}. Category: {esc(r['category'])}.</description></item>""" for r in rows)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>x402 posted-price changes (wknipe.com)</title><link>https://wknipe.com/x402/prices/</link>
<description>Daily diff of the Coinbase CDP Bazaar: x402 listings that changed their posted USDC price per call.</description>{items}</channel></rss>"""
    os.makedirs(os.path.join(HERE, 'x402', 'prices'), exist_ok=True)
    open(os.path.join(HERE, 'x402', 'prices', 'changes.xml'), 'w').write(xml)


def build(d):
    price_feed(d)
    status_page(d); access_page(d); weekly_posts(d); badges(d)
    print('og images:', og_images(d))
