"""Pre-render, after ORDER_013: tools that turn the index into decisions.

- /x402/buy/    Best execution: for a task an agent needs done, the cheapest listing that verifiably answers 402 at its
                listed price, and which comparable sellers real buyers actually use. (The buy-side router idea: the price
                index as the router's decision input.) Client: assets/buy.js.
- /x402/gaps/   Topics: per listing topic, how many sellers compete and what share of them get 5+ genuine buyers.
- /x402/brief/  State of x402 on one printable page, every number computed from the data files.
- data:         /x402/data/health.json (latest endpoint check per listing URL), /x402/data/gaps.json;
                a lighter ⌘K listings index (one entry per host instead of per host + task).
"""
import collections, json, os, statistics

from _pages import D, HERE, GLOSSARY, rcsv, rjson, f, write, esc
from _wk import *  # noqa: F401,F403
import _topics

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
    json.dump({'date': day, 'cols': ['valid_402', 'price_match', 'payto_match', 'latency_ms'], 'h': h},
              open(os.path.join(HERE, 'x402', 'data', 'health.json'), 'w'), separators=(',', ':'))
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


# ------------------------------------------------------------------ gap map
def gaps(d):
    L, ci = _listings()
    if not L: return None
    S = L['sellers']
    usd_by = {r['payee']: f(r['usd']) or 0 for r in d.payees if r['week_start'] == L['week']}
    listings, prices, per_seller, examples = collections.Counter(), collections.defaultdict(list), collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for r in L['rows']:
        t = _topics.topic(r[ci['what']], r[ci['name']])
        listings[t] += 1
        if r[ci['price_usd']]: prices[t].append(r[ci['price_usd']])
        if r[ci['what']]: examples[t][r[ci['what']]] += 1
        if r[ci['seller']] is not None: per_seller[r[ci['seller']]][t] += 1
    # each seller counts once, in the topic most of its listings are in, so seller counts add up to the total
    main = collections.defaultdict(list)
    for s, c in per_seller.items(): main[c.most_common(1)[0][0]].append(s)
    rows = []
    for t, n in listings.items():
        ss = main.get(t, [])
        got = [s for s in ss if S[s][1] >= MIN]
        paid = [S[s][2] for s in got if S[s][2]]
        rows.append({'topic': t, 'label': _topics.LABEL[t], 'listings': n, 'sellers': len(ss), 'sellers_5': len(got),
                     'hit_rate': len(got) / len(ss) if len(ss) >= 10 else None,
                     'buyer_seller_pairs': sum(S[s][1] for s in ss),
                     'clean_usd': round(sum(usd_by.get(S[s][0], 0) for s in ss), 2),
                     'posted_median_usd': statistics.median(prices[t]) if prices[t] else None,
                     'paid_median_usd': statistics.median(paid) if paid else None,
                     'examples': [w for w, _ in examples[t].most_common(4)]})
    rows.sort(key=lambda r: -(r['hit_rate'] if r['hit_rate'] is not None else -1))
    tot_s = sum(r['sellers'] for r in rows); tot_5 = sum(r['sellers_5'] for r in rows)
    out = {'snapshot': L['snapshot'], 'week': L['week'], 'min_buyers': MIN, 'sellers': tot_s, 'sellers_5': tot_5, 'base_rate': tot_5 / tot_s if tot_s else None, 'topics': rows}
    json.dump(out, open(os.path.join(HERE, 'x402', 'data', 'gaps.json'), 'w'), separators=(',', ':'))
    with open(os.path.join(HERE, 'x402', 'data', 'gaps.csv'), 'w') as fh:
        cols = ['topic', 'label', 'listings', 'sellers', 'sellers_5', 'hit_rate', 'buyer_seller_pairs', 'clean_usd', 'posted_median_usd', 'paid_median_usd']
        fh.write(','.join(cols) + '\n')
        for r in rows: fh.write(','.join('' if r[c] is None else f'"{r[c]}"' if c == 'label' else str(r[c]) for c in cols) + '\n')
    return out


def gaps_page(d, G):
    if not G:
        write('gaps.md', md('<p>Listing data not built yet.</p>')); return
    T = [r for r in G['topics'] if r['hit_rate'] is not None and r['topic'] != 'other']
    best = T[0]; worst = min(T, key=lambda r: r['hit_rate'])
    crowd = max(T, key=lambda r: r['sellers'])
    base = G['base_rate']
    under = [r for r in T if r['hit_rate'] >= 2 * base and r['sellers'] <= statistics.median(x['sellers'] for x in T)]
    cards = [stat_card('Sellers listed on Base', num(G['sellers']), foot=f'Bazaar snapshot {G["snapshot"]}', tip='Distinct Base payTo addresses with at least one listing in the Coinbase CDP Bazaar.'),
             stat_card(f'…with {MIN}+ genuine buyers', pct(base), foot=f'{num(G["sellers_5"])} sellers, week of {week_label(G["week"])}', tip='The base rate: share of listed sellers whose payTo had at least 5 genuine buyers in the latest index week.'),
             stat_card('Highest share with buyers', esc(best['label'].split(' &')[0].split(',')[0]), foot=f'{pct(best["hit_rate"])} of {best["sellers"]} sellers', tip='Highest share of sellers with 5+ genuine buyers, among topics with at least 10 sellers.'),
             stat_card('Most crowded topic', esc(crowd['label'].split(' &')[0].split(',')[0]), foot=f'{num(crowd["sellers"])} sellers, {pct(crowd["hit_rate"])} get buyers', tip='Most sellers whose main topic this is.')]
    uline = ', '.join(f'{esc(r["label"].lower())} ({pct(r["hit_rate"])} of {r["sellers"]})' for r in under[:4])
    title = f'{esc(best["label"])} has the highest share with buyers: {pct(best["hit_rate"])} of its sellers get {MIN}+ genuine buyers, against {pct(base)} across all listed sellers'
    cols = [{'k': 'label', 'label': 'Topic'}, {'k': 'sellers', 'label': 'Sellers', 't': 'int', 'r': 1}, {'k': 'hit_rate', 'label': f'Get {MIN}+ buyers', 't': 'pct', 'r': 1},
            {'k': 'buyer_seller_pairs', 'label': 'Genuine buyers (sum)', 't': 'int', 'r': 1}, {'k': 'clean_usd', 'label': 'Clean $ / week', 't': 'usd', 'r': 1},
            {'k': 'posted_median_usd', 'label': 'Median ask', 't': 'price', 'r': 1}, {'k': 'paid_median_usd', 'label': 'Median paid', 't': 'price', 'r': 1},
            {'k': 'listings', 'label': 'Listings', 't': 'int', 'r': 1}, {'k': 'ex', 'label': 'Typical listings', 't': 'html'}]
    trows = [{**r, 'ex': '<span class="sub">' + esc(' · '.join(r['examples'][:3])) + '</span>', 'ex_t': ' · '.join(r['examples']), 'ex_s': r['label'],
              'hit_rate': r['hit_rate']} for r in G['topics']]
    out = [decide('Every x402 listing, grouped by what it does, with how many sellers offer it and what share of them have five or more genuine buyers.'),
           freshness(d.through, f'listings snapshot {G["snapshot"]} · buyers week of {week_label(G["week"])}'), kpis(cards),
           chart_frame('gap-map', title,
                       f'Each dot is a listing topic. Across: sellers whose main topic it is (competition, log scale). Up: share of them with {MIN}+ genuine buyers in the week of {week_label(G["week"])} (demand that reaches sellers). '
                       f'Dot size: genuine buyers summed over those sellers. Dashed line: the {pct(base)} base rate. Topics with fewer than 10 sellers are left off the chart.',
                       'gapmap', '/x402/data/gaps.json', csv='/x402/data/gaps.csv', through=d.through, page='/x402/gaps/',
                       note='Upper left: few sellers, most of them with genuine buyers. Lower right: many sellers, few of them with buyers.'),
           (f'<p>Above the base rate with fewer sellers than the median topic: {uline}. ' if under else '<p>')
           + f'Lowest conversion: {esc(worst["label"].lower())}, where {pct(worst["hit_rate"])} of {worst["sellers"]} sellers get {MIN}+ buyers.</p>',
           '<h2 id="topics">Every topic</h2>',
           data_table('gaps-table', cols, trows, sort='hit_rate', page_size=40, csv_name='x402_topics.csv', search=['label', 'ex_t']),
           f'<p class="meta">How it works. Topics come from a fixed keyword taxonomy over each listing\'s normalised "what it does" text (<a href="https://github.com/doescodinggiteasier/wknipe-site/blob/main/site/_topics.py">_topics.py</a>; first matching rule wins). '
           f'Each seller is counted once, in the topic most of its listings fall in, so seller counts add up to {num(G["sellers"])}. Buyers are genuine (demand-cleaned) buyer wallets of the seller across all its endpoints, so a seller\'s buyers are credited to its main topic. '
           f'"Genuine buyers (sum)" adds buyers across sellers and double-counts a wallet that pays two sellers. Listings on other networks than Base have no seller match and count only in "Listings". '
           f'<a href="/x402/prices/comps">Price comps</a> goes one level deeper for a specific API.</p>']
    write('gaps.md', md('\n'.join(out)))


# ------------------------------------------------------------------ best execution (buy side)
def buy_page(d, hday, hn):
    P = d.prices
    EX = ['web search', 'scrape web page to markdown', 'token price', 'weather forecast', 'llm chat completion', 'company enrichment', 'sec filings', 'twitter search', 'image generation', 'news headlines']
    ui = f'''{decide('A small search tool: describe a task and it ranks the x402 endpoints that do it by price, by whether they passed my latest check, and by whether real buyers use them.')}
{freshness(d.through, f"listings {P['snapshot']} · endpoint checks {hday or '–'} · buyers week of {week_label(P['week'])}")}
<form id="buy-form" class="card-wk" role="search" style="display:grid;gap:12px;margin-bottom:20px" onsubmit="return false">
<label for="buy-q" style="font-weight:600">What does your agent need done?</label>
<input id="buy-q" type="search" placeholder='e.g. "web search", "token price", "scrape a page to markdown"' autocomplete="off">
<div class="buy-opts"><label class="meta" for="buy-max">Max price per call</label>
<select id="buy-max" class="wk-select"><option value="">Any</option><option value="0.001">$0.001</option><option value="0.005">$0.005</option><option value="0.01">$0.01</option><option value="0.05">$0.05</option><option value="0.1">$0.10</option><option value="1">$1</option></select>
<label class="buy-chk"><input type="checkbox" id="buy-verified"> Only endpoints that passed today's check</label>
<span class="meta" id="buy-status">Loading {num(P['listings'])} listings…</span></div>
<div class="ctrl" id="buy-examples"></div></form>
<div id="buy-out" hidden>
<div class="picks" id="buy-picks"></div>
<p id="buy-spread" class="buy-spread"></p>
<div id="buy-table"></div>
<details class="card-wk buy-json"><summary>Agent-ready JSON (top 5 by this ranking)</summary><pre><code id="buy-json"></code></pre><button type="button" class="wk-btn ghost" id="buy-copy">Copy JSON</button></details>
</div>
<h2 id="how">How the ranking works</h2>
<ul class="meta-list">
<li><b>Relevance first.</b> The 40 best text matches for your task among {num(P['listings'])} Bazaar listings, at most 3 per seller.</li>
<li><b>Verified</b> = my unpaid daily check found a valid 402 whose price and payTo match the listing ({num(hn)} endpoints checked on {hday or '–'}; the rest are "not checked yet", not failed).</li>
<li><b>Used by buyers</b> = the listing's seller had {MIN}+ genuine (demand-cleaned) buyers in the week of {week_label(P['week'])}, across all its endpoints.</li>
<li><b>Score</b> = relevance, then +verified, +used by buyers, and a price term (cheaper is better, on a log scale). Failed checks sink to the bottom.</li>
<li>Nothing here is paid placement, and I never call a paid endpoint. Posted prices can change at any time; the live 402 is the price you actually pay.</li>
</ul>
<p class="meta">Related: <a href="/x402/prices/comps">Price comps</a> shows what comparable listings charge; <a href="/x402/gaps/">Topics</a> groups every listing by what it does.</p>
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
    pv = {r['category']: r for r in d.prices.get('posted_vs_paid', [])}.get('all', {})
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
        ('Prices', f'The median listing asks {usd(pv.get("posted_median_usd"), True)} per call; the median clean payment is {usd(pv.get("paid_median_usd"), True)}: buyers pay about {pv.get("ratio", 0):.1f}× the asking median.' if pv else ''),
        ('Infrastructure', (f'{esc(ftop[0].title())} settles {pct(ftop[1] / clean)} of clean dollars. ' if ftop else '')
                   + (f'{pct(f(st["valid_402"]))} of {num(st["checked"])} listed endpoints checked on {st["date"]} answer a valid 402; {pct(f(st["price_match_of_valid"]))} of those at their listed price.' if st else '')),
        ('Publishers', f'{pct(anyb["share"])} of top-1,000 sites with a robots.txt block at least one AI crawler by name; {price["k"]} of {price["n"]} state a machine-readable price.' if anyb and price else ''),
    ]
    body = ''.join(f'<div class="brief-row"><div class="bk">{k}</div><div class="bv">{v}</div></div>' for k, v in rows if v)
    cite = f'Knipe, W. ({lw[:4]}). State of x402, week of {week_label(lw, True)}. wknipe.com/x402/brief/. Data: x402 Clean Index, CC BY 4.0.'
    out = f'''<p class="brief-eyebrow">x402 Clean Index · one page · week of {week_label(lw, True)}</p>
<p class="lede brief-lede">Of every dollar that moved through x402 on Base last week, {pct(clean / raw)} survives removing manufactured, single-buyer and test payments: {usd(clean)} a week, or {usd(clean * 52)} a year at this rate.</p>
<div class="brief">{body}</div>
<div class="brief-foot"><p><b>Method.</b> Every USDC settlement sent by 128 known x402 facilitators on Base, minus my own payments, closed loops, funding-linked pairs, fan-out manufacture and single-buyer sellers. The filters are conservative, so clean volume is a ceiling on genuine demand, not a floor. <a href="{METHOD}">Method note</a> · <a href="/x402/">Market dashboard</a> · <a href="/api/">API</a></p>
<p><b>Cite.</b> {esc(cite)} <button type="button" class="chip" data-copy="{esc(cite)}">Copy</button></p>
<p class="brief-actions"><button type="button" class="wk-btn" onclick="window.print()">Print or save as PDF</button> <a class="wk-btn ghost" href="/weekly/">Weekly report + RSS</a></p></div>
<script>document.addEventListener("click",(e)=>{{const b=e.target.closest("[data-copy]");if(b){{navigator.clipboard.writeText(b.dataset.copy);b.textContent="Copied";}}}});</script>'''
    write('brief.md', md(out))


def build(d):
    hday, hn = health(d)
    search_listings(d)
    G = gaps(d)
    gaps_page(d, G)
    buy_page(d, hday, hn)
    brief_page(d)
