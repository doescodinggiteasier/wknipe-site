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


def page(s, doc):
    a = s['address']; short = f'{a[:6]}…{a[-4:]}'
    name = s['label'] or short
    L = s['latest']
    rows = '\n'.join(f"| {dt.date.fromisoformat(r['week']).strftime('%-d %b %y')} | {usd(r['usd'])} | {r['payments']:,} | {r['buyers']:,} | {price(r['median_paid'])} |"
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
    if s['example_listing']:
        e = s['example_listing']
        listing.append(f"- **Example listing:** {html.escape(e)}{'…' if len(e) >= 160 else ''}")
    if not listing:
        listing.append('- No listing found in any Bazaar or x402scan snapshot we hold, so what it sells is unknown.')
    status = (f"**#{s['rank']}** of {sum(1 for x in doc['sellers'] if x['qualifies_latest'])} sellers with at least "
              f"{doc['min_buyers']} clean buyers in the week of {wk(doc['latest_week'])}." if s['qualifies_latest'] else
              f"Not on this week's leaderboard (fewer than {doc['min_buyers']} clean buyers in the week of {wk(doc['latest_week'])}).")
    first = wk(s['first_seen_week']) + (' (the index history starts that week)' if s['first_seen_week'] == doc['history_starts'] else '')
    desc = (f"x402 seller {name} on Base: clean payments, distinct buyers and prices per week"
            + (f"; {usd(L['usd'])} from {L['buyers']} buyers in the week of {wk(doc['latest_week'])}." if L else '.'))
    return f'''---
title: "{name.replace('"', "'")}"
subtitle: "x402 seller · {LABEL.get(s['category'], s['category'])}"
description: "{desc.replace('"', "'")}"
---

{status}

`{a}` · [Basescan](https://basescan.org/address/{a}) · Category: **{LABEL.get(s['category'], s['category'])}** ({SOURCE.get(s['category_source'], s['category_source'])})

<div class="seller-spark"><span>Clean USD per week</span>{spark(s['history'], doc['weeks'])}</div>

## Listing

{chr(10).join(listing)}

## Clean payments by week

::: {{.seller-table}}
| Week of | Clean USD | Payments | Distinct buyers | Median paid |
|---|--:|--:|--:|--:|
{rows}
:::

First seen in the cleaned index: {first}. "Clean" means after the [x402 Clean Index](../index.qmd) filters: self-payments, closed loops, funding-linked pairs, fan-out manufacture and single-buyer dust removed. See the [method note](https://github.com/doescodinggiteasier/wknipe-site/blob/main/docs/X402_INDEX_METHOD.md).

[← All sellers](index.qmd) · Data: [sellers.json](../data/sellers.json) (CC BY 4.0)
'''


def build():
    for p in glob.glob(os.path.join(PAGES, '0x*.qmd')): os.remove(p)
    if not os.path.exists(DATA): return 0
    doc = json.load(open(DATA))
    for s in doc['sellers']:
        open(os.path.join(PAGES, f"{s['address']}.qmd"), 'w').write(page(s, doc))
    return len(doc['sellers'])
