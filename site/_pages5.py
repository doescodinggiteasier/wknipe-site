"""Pre-render, after ORDER_013: tools that turn the index into decisions.

- /x402/buy/    Best execution: for a task an agent needs done, the cheapest listing that verifiably answers 402 at its
                listed price, and which comparable sellers real buyers actually use. (The buy-side router idea: the price
                index as the router's decision input.) Client: assets/buy.js.
- /x402/brief/  State of x402 on one printable page, every number computed from the data files.
  (ORDER_014: Topics, /x402/gaps/, moved to the private repo, private/gaps/build_gaps.py: it is a what-to-build signal.)
- data:         a lighter ⌘K listings index (one entry per host instead of per host + task).
"""
import collections, json, os, statistics

from _pages import D, HERE, GLOSSARY, rcsv, rjson, f, write, esc, sensitivity_line
from _wk import *  # noqa: F401,F403

MIN = 5  # genuine buyers for a seller to count as "gets buyers", as on the sellers page


def _listings():
    L = rjson(D('x402_prices', 'listings.json'))
    if not L: return None, None
    return L, {c: i for i, c in enumerate(L['cols'])}


# ------------------------------------------------------------------ endpoint health for the router
def health(d):
    lat = rcsv(D('x402_status', 'status_latest.csv'))
    h = {}
    for r in lat:
        u = r['resource'].removeprefix('https://')
        b = lambda k: {'True': 1, 'False': 0}.get(r[k])
        h[u] = [b('valid_402'), b('price_match'), b('payto_match'), int(f(r['latency_ms']) or 0) or None]
    day = lat[0]['date'] if lat else None
    # ORDER_014: no longer written to /x402/data/health.json; the joined routing table lives only in the API Worker
    return day, len(h)


# ------------------------------------------------------------------ lighter search index (3.8 MB -> one entry per host)
def search_listings(d):
    L, ci = _listings()
    if not L: return
    by = collections.OrderedDict()
    for r in L['rows']:
        e = by.setdefault(r[ci['host']], {'whats': collections.Counter(), 'n': 0, 'prices': [], 'seller': r[ci['seller']]})
        e['n'] += 1
        if r[ci['what']]: e['whats'][r[ci['what']]] += 1
        if r[ci['price_usd']]: e['prices'].append(r[ci['price_usd']])
    out = []
    for host, e in by.items():
        top = [w for w, _ in e['whats'].most_common(3)]
        sel = L['sellers'][e['seller']] if e['seller'] is not None else None
        u = f'/x402/sellers/{sel[0]}' if sel and sel[3] else f'/x402/buy/?need={(top[0] if top else host).replace(" ", "+")}'
        pr = f' · from {usd(min(e["prices"]), True)}' if e['prices'] else ''
        out.append({'t': host, 's': f'{e["n"]} listing{"s" if e["n"] != 1 else ""} · {", ".join(top)}{pr}',
                    'x': ' '.join(w for w, _ in e['whats'].most_common(12))[:400], 'u': u})
    json.dump(out, open(os.path.join(HERE, 'assets', 'search-listings.json'), 'w'), separators=(',', ':'))


# ------------------------------------------------------------------ best execution (buy side)
def buy_page(d, hday, hn):
    P = d.prices
    price = '$0.001'
    ui = f'''{decide('A small demo: describe a task and it shows three x402 endpoints that do it: the cheapest one that passed my latest check, the cheapest whose seller has real buyers, and the one most buyers use.')}
{freshness(d.through, f"listings {P['snapshot']} · endpoint checks {hday or '–'} · buyers week of {week_label(P['week'])}")}
<form id="buy-form" class="card-wk" role="search" data-api="{API}" style="display:grid;gap:12px;margin-bottom:20px" onsubmit="return false">
<label for="buy-q" style="font-weight:600">What does your agent need done?</label>
<input id="buy-q" type="search" placeholder='e.g. "web search", "token price", "scrape a page to markdown"' autocomplete="off">
<div class="buy-opts"><label class="meta" for="buy-max">Max price per call</label>
<select id="buy-max" class="wk-select"><option value="">Any</option><option value="0.001">$0.001</option><option value="0.005">$0.005</option><option value="0.01">$0.01</option><option value="0.05">$0.05</option><option value="0.1">$0.10</option><option value="1">$1</option></select>
<label class="buy-chk"><input type="checkbox" id="buy-verified"> Only endpoints that passed today's check</label>
<span class="meta" id="buy-status">Searching {num(P['listings'])} listings.</span></div>
<div class="ctrl" id="buy-examples"></div></form>
<div id="buy-out" hidden>
<div class="picks" id="buy-picks"></div>
<p id="buy-spread" class="buy-spread"></p>
</div>
<h2 id="agents">For agents</h2>
<p>The full ranking (up to 40 endpoints per task, with price, check result, latency and the seller's genuine buyers) is a paid x402 endpoint, <b>{price} per call</b> in USDC on Base. The MCP server's <code>best_execution</code> tool calls it and needs a wallet. Without one, it returns these three picks.</p>
<pre><code>GET {API}/v1/route?need=web+search&amp;max_price=0.01&amp;verified=1&amp;n=20</code></pre>
<p class="meta">See the <a href="/api/#route">API page</a>. My own test payments are excluded from the index.</p>
<h2 id="how">How the ranking works</h2>
<ul class="meta-list">
<li><b>Relevance first.</b> The 40 best text matches for your task among {num(P['listings'])} Bazaar listings, at most 3 per seller.</li>
<li><b>Verified</b> = my unpaid daily check found a valid 402 whose price and payTo match the listing ({num(hn)} endpoints checked on {hday or '–'}; the rest are "not checked yet", not failed).</li>
<li><b>Used by buyers</b> = the listing's seller had {MIN}+ genuine (demand-cleaned) buyers in the week of {week_label(P['week'])}, across all its endpoints.</li>
<li><b>Score</b> = relevance, then +verified, +used by buyers, and a price term (cheaper is better, on a log scale). Failed checks sink to the bottom.</li>
<li>Nothing here is paid placement, and I never call a paid endpoint. Posted prices can change at any time; the live 402 is the price you actually pay.</li>
</ul>
<p class="meta">Related: <a href="/x402/prices/comps">Price comps</a> shows what comparable listings charge.</p>
<script defer src="/assets/buy.js?v={int(dt.datetime.now().timestamp())}"></script>'''
    write('buy.md', md(ui))


# ------------------------------------------------------------------ one-page brief
def brief_page(d):
    M, H, lw = d.market, d.head, d.latest
    wf = [r for r in M['waterfall'] if r['week_start'] == lw]
    raw = sum(r['usd'] for r in wf); clean = next(r['usd'] for r in wf if r['step'] == 'clean')
    cuts = sorted((r for r in wf if r['step'] != 'clean' and r['usd'] > 0), key=lambda r: -r['usd'])
    bw = next(r for r in M['buyers_weekly'] if r['week_start'] == lw)
    con = next(r for r in M['concentration'] if r['week_start'] == lw and r['category'] == 'all')
    tiers = [t for t in M['buyer_tiers'] if t['week_start'] == lw]
    big = [t for t in tiers if t['tier'] in ('$100–$1k', '$1k and up')]
    big_b = sum(t['buyers'] for t in big); big_usd = sum(t['usd'] for t in big); tier_usd = sum(t['usd'] for t in tiers)
    spb = [r for r in M['sellers_per_buyer'] if r['week_start'] == lw]
    one = next((r['buyers'] for r in spb if str(r['sellers']) == '1'), None); spb_tot = sum(r['buyers'] for r in spb)
    fac = collections.defaultdict(float)
    for r in M['facilitators']:
        if r['week_start'] == lw: fac[r['name'] or r['facilitator'][:10]] += r['clean_usd']
    ftop = max(fac.items(), key=lambda x: x[1]) if fac else None
    cats = H.get('clean_by_category_usd', {}); ctop = max(cats.items(), key=lambda x: x[1]) if cats else None
    cd = H.get('tripwire_content_plus_data_clean_usd'); g4 = H.get('tripwire_4week_growth')
    pbc = {r['category']: r for r in d.prices.get('posted_by_category', [])}.get('all', {})
    st = next((r for r in (d.status or {}).get('latest', []) if r['scope'] == 'all'), None)
    A = d.access; sig = {s['signal']: s for s in A['signals']} if A else {}
    anyb = sig.get('Blocks at least one AI crawler by name'); price = sig.get('States a machine-readable price')
    W = d.weeks; cs = d.series('clean', 'all')
    first, last = cs[0], cs[-1]
    rows = [
        ('Volume', f'{usd(raw)} settled through x402 facilitators on Base in the week of {week_label(lw, True)}; <b>{usd(clean)} ({pct(clean / raw)}) is demand-cleaned</b>. '
                   f'The biggest cut: {esc(cuts[0]["label"].lower())} ({usd(cuts[0]["usd"])}). Clean volume was {usd(first)} in the week of {week_label(W[0])} ({signed_pct(growth(first, last))} over {len(W) - 1} weeks). '
                   f'Annualised, the latest week is {usd(clean * 52)} a year of demand-cleaned spend (latest week × 52; an upper bound on genuine demand, not a forecast).'),
        ('Buyers', f'<b>{num(bw["active_buyers"])} genuine buyer wallets</b>, {num(bw["new_buyers"])} of them new. Median spend {usd(bw["median_spend_usd"], True)} a week. '
                   + (f'{pct(one / spb_tot)} pay a single seller. ' if one and spb_tot else '')
                   + (f'The {num(big_b)} wallets spending $100+ bring {pct(big_usd / tier_usd)} of clean dollars.' if big_b and tier_usd else '')),
        ('Sellers', f'<b>{num(con["sellers"])} sellers</b> with 2+ genuine buyers. The top 10 hold {pct(con["top10_share"])} of clean dollars (HHI {num(con["hhi"])}, the equivalent of {con["effective_sellers"]:.1f} equal-sized sellers).'),
        ('What sells', (f'{esc(CAT_LABEL.get(ctop[0], ctop[0]))} is the largest category at {usd(ctop[1])} ({pct(ctop[1] / clean)}). ' if ctop else '')
                   + (f'Content + data (articles, reports, prices and records) is {usd(cd)} ({pct(cd / clean, 1)}), {signed_pct(g4)} over four weeks.' if cd is not None else '')),
        ('Prices', f'Half of priced listings ask {usd(pbc.get("median_usd"), True)} or less per call; the top tenth ask {usd(pbc.get("p90_usd"), True)} or more.' if pbc else ''),
        ('Infrastructure', (f'{esc(ftop[0].title())} settles {pct(ftop[1] / clean)} of clean dollars. ' if ftop else '')
                   + (f'{pct(f(st["valid_402"]))} of {num(st["checked"])} listed endpoints checked on {st["date"]} answer a valid 402; {pct(f(st["price_match_of_valid"]))} of those at their listed price.' if st else '')),
        ('Publishers', f'{pct(anyb["share"])} of top-1,000 sites with a robots.txt block at least one AI crawler by name; {price["k"]} of {price["n"]} state a machine-readable price.' if anyb and price else ''),
    ]
    body = ''.join(f'<div class="brief-row"><div class="bk">{k}</div><div class="bv">{v}</div></div>' for k, v in rows if v)
    cite = f'Knipe, W. ({lw[:4]}). State of x402, week of {week_label(lw, True)}. wknipe.com/x402/brief/. Data: x402 Clean Index, CC BY 4.0.'
    out = f'''<p class="brief-eyebrow">x402 Clean Index · one page · week of {week_label(lw, True)}</p>
<p class="lede brief-lede">Of every dollar that moved through x402 on Base last week, {pct(clean / raw)} survives removing manufactured, single-buyer and test payments: {usd(clean)} a week, or {usd(clean * 52)} a year at this rate.</p>
<div class="brief">{body}</div>
<div class="brief-foot"><p><b>Method.</b> Every USDC settlement sent by 128 known x402 facilitators on Base, minus my own payments, closed loops, funding-linked pairs, fan-out manufacture and single-buyer sellers. The filters are conservative, so clean volume is a ceiling on genuine demand, not a floor. {esc(sensitivity_line(d))} <a href="{METHOD}">Method note</a> · <a href="/x402/">Market dashboard</a> · <a href="/api/">API</a></p>
<p><b>Cite.</b> {esc(cite)} <button type="button" class="chip" data-copy="{esc(cite)}">Copy</button></p>
<p class="brief-actions"><button type="button" class="wk-btn" onclick="window.print()">Print or save as PDF</button> <a class="wk-btn ghost" href="/weekly/">Weekly report + RSS</a></p></div>
<script>document.addEventListener("click",(e)=>{{const b=e.target.closest("[data-copy]");if(b){{navigator.clipboard.writeText(b.dataset.copy);b.textContent="Copied";}}}});</script>'''
    write('brief.md', md(out))


def build(d):
    hday, hn = health(d)
    search_listings(d)
    buy_page(d, hday, hn)
    brief_page(d)
