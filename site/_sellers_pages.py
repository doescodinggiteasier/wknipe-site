"""Pre-render step (Build 2): one static page per x402 seller, from data/x402_sellers/sellers.json.

Static Markdown (no JavaScript) so each seller has a permanent, indexable URL: /x402/sellers/<address>.
Generated files (x402/sellers/0x*.qmd) are not committed; every render regenerates them."""
import datetime as dt, glob, html, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data', 'x402_sellers', 'sellers.json')
PAGES = os.path.join(HERE, 'x402', 'sellers')
LABEL = {'content': 'Content', 'data': 'Data', 'search': 'Search', 'compute': 'Compute & tools', 'other': 'Other',
         'large_ticket': 'Large ticket (unidentified)', 'unclassed': 'Unclassed'}
SOURCE = {'model': 'model-read listing', 'hand_o2': 'hand label', 'hand_o10': 'hand label', 'hand_o2+model': 'hand label + model',
          'unlisted_review': 'price-only rule (no listing)', 'none': 'no listing'}


def usd(x):
    if x is None: return '–'
    return f'${x:,.0f}' if abs(x) >= 100 else f'${x:,.2f}'


def price(x):
    if x is None: return '–'
    return (f'${x:.6f}'.rstrip('0').rstrip('.')) if x < 1 else f'${x:,.2f}'


def wk(w):
    return dt.date.fromisoformat(w).strftime('%-d %b %Y')


def spark(hist, weeks, w=240, h=48):
    """Clean USD per week as a small inline SVG (currentColor, so it follows the light/dark theme)."""
    vals = {r['week']: r['usd'] for r in hist}
    ys = [vals.get(x, 0) for x in weeks]
    top = max(ys) or 1
    step = (w - 8) / max(1, len(weeks) - 1)
    pts = [(4 + i * step, h - 6 - (h - 12) * v / top) for i, v in enumerate(ys)]
    path = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    dots = ''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5"><title>{wk(k)}: {usd(v)}</title></circle>'
                   for (x, y), k, v in zip(pts, weeks, ys))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="Clean USD per week, {wk(weeks[0])} to {wk(weeks[-1])}">'
            f'<polyline points="{path}" fill="none" stroke="currentColor" stroke-width="1.8"/>'
            f'<g fill="currentColor">{dots}</g></svg>')


def page(s, doc, extra, listings):
    """One seller: status, stat cards, weekly charts, quality signals, posted vs realised price, filter removal, listings."""
    import _wk as W
    a = s['address']; short = f'{a[:6]}…{a[-4:]}'
    name = s['label'] or short
    L = s['latest']; lw = doc['latest_week']
    ex = extra.get(a) or {}
    e = ex.get(lw) or (ex[max(ex)] if ex else {})
    ew = lw if lw in ex else (max(ex) if ex else None)
    hist = {h['week']: h for h in s['history']}
    usd_s = [hist.get(w, {}).get('usd', 0) for w in doc['weeks']]; buy_s = [hist.get(w, {}).get('buyers', 0) for w in doc['weeks']]
    prev = hist.get(doc['weeks'][-2]) if len(doc['weeks']) > 1 else None
    g = W.growth(prev['usd'], L['usd']) if (L and prev) else None
    cards = [W.stat_card('Demand-cleaned USD', W.usd(L['usd']) if L else '$0', usd_s, g, tip='USD this seller received from genuine buyers in the week, after the index filters.', weeks=doc['weeks']),
             W.stat_card('Genuine buyers', W.num(L['buyers']) if L else '0', buy_s, W.growth(prev['buyers'], L['buyers']) if (L and prev) else None, tip=W.GL['genuine buyers'] if hasattr(W, 'GL') else 'Distinct payer wallets with a demand-cleaned payment.', weeks=doc['weeks']),
             W.stat_card('Repeat-buyer rate', W.pct(e.get('repeat_buyer_rate')), tip="Share of this seller's genuine buyers who paid it at least twice in the week" + (f' (week of {W.week_label(ew)})' if ew else '') + '.'),
             W.stat_card('Top-buyer share', W.pct(e.get('top_buyer_share')), tip="Share of this seller's demand-cleaned USD from its single largest buyer. A dependence / wash-risk signal, not an accusation."),
             W.stat_card('Paid vs posted', f"{W.usd(L['median_paid'], True) if L else '–'} / {W.usd(s['posted_usd']['median'], True) if s['posted_usd'] else '–'}", tip='Median demand-cleaned payment this week / median posted price per call in its Bazaar listings.')]
    top = e.get('top_buyer_share')
    signal = ''
    if top is not None:
        signal = (f"Its largest buyer accounts for {W.pct(top)} of its demand-cleaned USD" + (' — revenue depends on a single wallet.' if top >= 0.5 else '.') +
                  f" {W.pct(e.get('repeat_buyer_rate'))} of its {W.num(e.get('buyers'))} buyers paid more than once.")
    rm = ''
    if e.get('raw_usd'):
        raw, d05, cl = e['raw_usd'], e.get('d05_usd', 0), e.get('clean_usd', 0)
        rm = (f"<p><b>What the filters removed</b> (week of {W.week_label(ew, True)}): of {W.usd(raw, True)} settled to this address, "
              f"{W.usd(raw - d05, True)} ({W.pct((raw - d05) / raw)}) was manufactured (loops or shared funding)"
              + (f", and the seller was flagged for fan-out manufacture" if e.get('fanout') else '')
              + f"; {W.usd(cl, True)} ({W.pct(cl / raw)}) counts as demand-cleaned.</p>")
    lrows = listings.get(a, [])
    lt = ''
    if lrows:
        lt = W.data_table('listings-table', [{'k': 'what', 'label': 'What it does'}, {'k': 'path', 'label': 'Endpoint'}, {'k': 'category', 'label': 'Category'}, {'k': 'price', 'label': 'Posted', 't': 'price', 'r': 1}],
                          [{'what': r['what'], 'path': (r['host'] + r['path'])[:70], 'category': r['category'], 'price': r['price']} for r in lrows], page_size=10, placeholder='Filter endpoints', csv_name=f'{a}_listings.csv')
    rows = '\n'.join(f"| {dt.date.fromisoformat(r['week']).strftime('%-d %b %y')} | {usd(r['usd'])} | {r['payments']:,} | {r['buyers']:,} | {price(r['median_paid'])} | {W.pct((ex.get(r['week']) or {}).get('repeat_buyer_rate'))} | {W.pct((ex.get(r['week']) or {}).get('top_buyer_share'))} |"
                     for r in reversed(s['history']))
    listing = []
    if s['label']:
        listing.append(f"- **Listed as:** {html.escape(s['label'])} ({s['label_source']}). Names are what the seller wrote in "
                       "its listing; we don't verify who operates an address.")
    if s['hosts']: listing.append('- **Hosts:** ' + ', '.join(f'`{h}`' for h in s['hosts']))
    if s['posted_usd']:
        p = s['posted_usd']
        listing.append(f"- **Posted price per call:** {price(p['median'])} median across {p['n']:,} Base USDC offers "
                       f"(range {price(p['min'])}–{price(p['max'])}), {s['listed_resources']:,} listed resources.")
    if not listing:
        listing.append('- No listing found in any Bazaar or x402scan snapshot we hold, so what it sells is unknown.')
    status = (f"**#{s['rank']}** of {sum(1 for x in doc['sellers'] if x['qualifies_latest'])} sellers with at least "
              f"{doc['min_buyers']} genuine buyers in the week of {wk(lw)}." if s['qualifies_latest'] else
              f"Not on this week's leaderboard (fewer than {doc['min_buyers']} genuine buyers in the week of {wk(lw)}).")
    first = wk(s['first_seen_week']) + (' (the index history starts that week)' if s['first_seen_week'] == doc['history_starts'] else '')
    desc = (f"x402 seller {name} on Base: demand-cleaned payments, genuine buyers, repeat-buyer rate and prices per week"
            + (f"; {usd(L['usd'])} from {L['buyers']} buyers in the week of {wk(lw)}." if L else '.'))
    fr_usd = W.chart_frame('weekly-usd', f"{W.usd(L['usd']) if L else '$0'} demand-cleaned in the week of {W.week_label(lw)}", 'Demand-cleaned USD per week.', 'sellerWeekly',
                           opts={'weeks': doc['weeks'], 'history': s['history'], 'metric': 'usd'}, page=f'/x402/sellers/{a}', through=None)
    fr_b = W.chart_frame('weekly-buyers', f"{W.num(L['buyers']) if L else 0} genuine buyers in the week of {W.week_label(lw)}", 'Distinct buyer wallets per week.', 'sellerWeekly',
                         opts={'weeks': doc['weeks'], 'history': s['history'], 'metric': 'buyers'}, page=f'/x402/sellers/{a}')
    return f'''---
title: "{name.replace('"', "'")}"
subtitle: "x402 seller · {LABEL.get(s['category'], s['category'])}"
description: "{desc.replace('"', "'")}"
body-classes: wide
---

{status} `{a}` · [Basescan](https://basescan.org/address/{a}) · Category: **{LABEL.get(s['category'], s['category'])}** ({SOURCE.get(s['category_source'], s['category_source'])}) · First seen: {first}

{W.md(W.kpis(cards))}

{signal}

{W.md('<div class="grid2">' + fr_usd + fr_b + '</div>' + rm)}

## Listing

{chr(10).join(listing)}

{W.md(lt) if lt else ''}

## By week

::: {{.seller-table}}
| Week of | Clean USD | Payments | Buyers | Median paid | Repeat buyers | Top-buyer share |
|---|--:|--:|--:|--:|--:|--:|
{rows}
:::

"Demand-cleaned" means after the [x402 index](../index.qmd) filters: self-payments, closed loops, funding-linked pairs, fan-out manufacture and single-buyer dust removed. See the [method note](https://github.com/doescodinggiteasier/wknipe-site/blob/main/docs/X402_INDEX_METHOD.md). Badge for this seller: [/badges/](/badges/).

[← All sellers](index.qmd) · Data: [sellers.json](../data/sellers.json) (CC BY 4.0)
'''


def build():
    for p in glob.glob(os.path.join(PAGES, '0x*.qmd')): os.remove(p)
    if not os.path.exists(DATA): return 0
    doc = json.load(open(DATA))
    ep = os.path.join(HERE, '..', 'data', 'x402_market', 'sellers_extra.json')
    extra = json.load(open(ep))['sellers'] if os.path.exists(ep) else {}
    listings = {}
    lp = os.path.join(HERE, '..', 'data', 'x402_prices', 'listings.json')
    if os.path.exists(lp):
        Lj = json.load(open(lp)); ci = {c: i for i, c in enumerate(Lj['cols'])}
        for r in Lj['rows']:
            if r[ci['seller']] is None: continue
            q = Lj['sellers'][r[ci['seller']]][0]
            listings.setdefault(q, []).append({'what': r[ci['what']], 'host': r[ci['host']], 'path': r[ci['path']], 'category': r[ci['category']], 'price': r[ci['price_usd']]})
    for s in doc['sellers']:
        open(os.path.join(PAGES, f"{s['address']}.qmd"), 'w').write(page(s, doc, extra, listings))
    return len(doc['sellers'])
