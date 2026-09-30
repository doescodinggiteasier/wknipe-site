#!/usr/bin/env python3
"""ORDER_010: render site/x402_index/index.html (one static page, inline SVG charts, no external scripts)
from data/x402_index/{weekly.csv, prices_weekly.csv, headline.json}. The page is written as artifact content
(no <html>/<head>/<body>; the publisher wraps it). Usage: python3 scripts/x402_index/site.py"""
import csv, datetime as dt, html, json, math, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import common

ROOT, OUT = common.ROOT, common.OUT
SITE = os.path.join(ROOT, 'site', 'x402_index', 'index.html')
REPO = 'https://github.com/doescodinggiteasier/wknipe-site/blob/main'
CATS = ['content', 'data', 'search', 'compute', 'other', 'large_ticket', 'unclassed']
LABEL = {'content': 'Content', 'data': 'Data', 'search': 'Search', 'compute': 'Compute & tools', 'other': 'Other', 'large_ticket': 'Large ticket (unidentified)',
         'unclassed': 'Unclassed'}
STAGE = {'raw': 'Raw settlements', 'd05': 'After manufacture filter', 'clean': 'Demand-cleaned'}


def usd(x, dp=None):
    if x is None or x == '': return '–'
    x = float(x)
    if dp is None: dp = 0 if abs(x) >= 100 else 2
    return f'${x:,.{dp}f}'


def price(x):
    if x is None or x == '': return '–'
    x = float(x)
    return f'${x:.4f}'.rstrip('0').rstrip('.') if x < 1 else f'${x:,.2f}'


def nice_max(v):
    if v <= 0: return 1
    e = 10 ** math.floor(math.log10(v)); m = v / e
    return (1 if m <= 1 else 2 if m <= 2 else 2.5 if m <= 2.5 else 5 if m <= 5 else 10) * e


def wk(d):
    return dt.date.fromisoformat(str(d)).strftime('%-d %b')


def bars_chart(weeks, series, title_id, fmt=usd):
    """Stacked columns. series: list of (key, label, {week: value})."""
    W, H, L, R, T, B = 640, 260, 64, 12, 12, 34
    tot = {w: sum(s[2].get(w, 0) for s in series) for w in weeks}
    ymax = nice_max(max(tot.values()) if tot else 1)
    pw = (W - L - R) / max(1, len(weeks)); bw = min(56, pw * 0.62)
    y = lambda v: T + (H - T - B) * (1 - v / ymax)
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="{title_id}" class="chart">']
    for i in range(5):
        v = ymax * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                 f'<text x="{L - 8}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">{fmt(v, 0)}</text>')
    for j, w in enumerate(weeks):
        x = L + pw * j + (pw - bw) / 2; base = 0
        tip = [f'Week of {wk(w)}: {fmt(tot[w])}']
        for key, lab, vals in series:
            v = vals.get(w, 0)
            if v <= 0: continue
            y0, y1 = y(base), y(base + v)
            h = max(0.0, y0 - y1 - 2)  # 2px surface gap between stacked segments
            g.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" class="s-{key}"/>')
            tip.append(f'{lab}: {fmt(v)}')
            base += v
        g.append(f'<rect x="{L + pw * j:.1f}" y="{T}" width="{pw:.1f}" height="{H - T - B}" class="hit"><title>{html.escape(chr(10).join(tip))}</title></rect>')
        g.append(f'<text x="{x + bw / 2:.1f}" y="{H - B + 18}" class="tick" text-anchor="middle">{wk(w)}</text>')
    g.append('</svg>')
    return ''.join(g)


def lines_chart(xs, series, title_id, yfmt=lambda v: f'{v:.0f}', floor0=False):
    """series: list of (key, label, {x: value}); x are ISO dates."""
    W, H, L, R, T, B = 640, 240, 52, 96, 14, 34
    vals = [v for _, _, d in series for v in d.values() if v is not None]
    if not vals: return '<p class="note">Not enough weeks yet.</p>'
    lo, hi = (0 if floor0 else min(vals)), max(vals)
    pad = max(1.0, (hi - lo) * 0.15); lo = 0 if floor0 else math.floor((lo - pad) / 5) * 5; hi = math.ceil((hi + pad) / 5) * 5
    xi = {x: i for i, x in enumerate(xs)}
    X = lambda x: L + (W - L - R) * (xi[x] / max(1, len(xs) - 1) if len(xs) > 1 else 0.5)
    Y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="{title_id}" class="chart">']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                 f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" class="tick" text-anchor="end">{yfmt(v)}</text>')
    for x in xs:
        g.append(f'<text x="{X(x):.1f}" y="{H - B + 18}" class="tick" text-anchor="middle">{wk(x)}</text>')
    for key, lab, d in series:
        pts = [(X(x), Y(d[x])) for x in xs if d.get(x) is not None]
        if len(pts) > 1:
            g.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" class="ln l-{key}"/>')
        for (a, b), x in zip(pts, [x for x in xs if d.get(x) is not None]):
            g.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" class="dot d-{key}"><title>{html.escape(lab)}, week of {wk(x)}: {yfmt(d[x])}</title></circle>')
        if pts:
            g.append(f'<text x="{pts[-1][0] + 10:.1f}" y="{pts[-1][1] + 4:.1f}" class="dlabel">{html.escape(lab)}</text>')
    g.append('</svg>')
    return ''.join(g)


def main():
    weekly = list(csv.DictReader(open(os.path.join(OUT, 'weekly.csv'))))
    prices = list(csv.DictReader(open(os.path.join(OUT, 'prices_weekly.csv'))))
    head = json.load(open(os.path.join(OUT, 'headline.json')))
    weeks = sorted({r['week_start'] for r in weekly})
    last = weeks[-1]
    V = lambda w, st, c, k='usd': float(next(r[k] for r in weekly if r['week_start'] == w and r['stage'] == st and r['category'] == c))

    stage_chart = lines_chart(weeks, [(s, STAGE[s], {w: V(w, s, 'all') / 1000 for w in weeks}) for s in ('raw', 'd05', 'clean')],
                              't-stage', yfmt=lambda v: f'${v:,.0f}k', floor0=True)
    cat_chart = bars_chart(weeks, [(c, LABEL[c], {w: V(w, 'clean', c) for w in weeks}) for c in CATS], 't-cat')
    cd_chart = bars_chart(weeks, [(c, LABEL[c], {w: V(w, 'clean', c) for w in weeks}) for c in ('content', 'data')], 't-cd')

    P = lambda meas, c: {r['week_start']: r for r in prices if r['measure'] == meas and r['category'] == c}
    tx = P('transacted', 'all'); po = P('posted', 'all')
    idx_series = [('transacted', 'Transacted', {w: float(tx[w]['index_jevons']) for w in tx if tx[w]['index_jevons']})]
    pweeks = sorted(set(tx) | set(po))
    if len(po) >= 2:
        idx_series.append(('posted', 'Posted', {w: float(po[w]['index_jevons']) for w in po if po[w]['index_jevons']}))
    idx_chart = lines_chart(pweeks, idx_series, 't-idx', yfmt=lambda v: f'{v:.0f}')

    # latest-week table
    lastpost = max(po) if po else None
    rows = []
    for c in CATS + ['all']:
        pp = P('posted', c).get(lastpost, {}) if lastpost else {}
        tt = P('transacted', c).get(last, {})
        name = 'All categories' if c == 'all' else LABEL[c]
        sw = '' if c == 'all' else f'<span class="sw s-{c}"></span>'
        rows.append(f'<tr class="{"total" if c == "all" else ""}"><th scope="row">{sw}{name}</th>'
                    f'<td>{usd(V(last, "raw", c))}</td><td>{usd(V(last, "clean", c))}</td>'
                    f'<td>{int(V(last, "clean", c, "payments")):,}</td><td>{int(V(last, "clean", c, "payees")):,}</td>'
                    f'<td>{price(tt.get("median_usd"))}</td>'
                    f'<td>{price(pp.get("median_usd"))} <span class="iqr">{price(pp.get("p25_usd"))}–{price(pp.get("p75_usd"))}</span></td>'
                    f'<td>{int(pp["items"]):,}</td></tr>' if pp else
                    f'<tr><th scope="row">{sw}{name}</th><td>{usd(V(last, "raw", c))}</td><td>{usd(V(last, "clean", c))}</td>'
                    f'<td>{int(V(last, "clean", c, "payments")):,}</td><td>{int(V(last, "clean", c, "payees")):,}</td>'
                    f'<td>{price(tt.get("median_usd"))}</td><td>–</td><td>–</td></tr>')

    # weekly history table
    hist = []
    for w in reversed(weeks):
        hist.append(f'<tr><th scope="row">{wk(w)}</th><td>{usd(V(w, "raw", "all"))}</td><td>{usd(V(w, "d05", "all"))}</td>'
                    f'<td>{usd(V(w, "clean", "all"))}</td><td>{usd(V(w, "clean", "content") + V(w, "clean", "data"))}</td>'
                    f'<td>{tx.get(w, {}).get("index_jevons") or "–"}</td></tr>')

    g4 = head.get('tripwire_4week_growth'); gl = head.get('tripwire_loglinear_monthly_growth_last_5_weeks')
    growth = (f'{g4 * 100:+.0f}% over 4 weeks' if g4 is not None else
              (f'{gl * 100:+.0f}% a month (trend)' if gl is not None else 'needs 5 weeks of history'))
    cleanshare = head['clean_usd'] / head['raw_usd'] if head['raw_usd'] else 0
    wend = (dt.date.fromisoformat(last) + dt.timedelta(days=6))
    legend = ''.join(f'<li><span class="sw s-{c}"></span>{LABEL[c]}</li>' for c in CATS)

    page = TEMPLATE.format(
        week=f'{wk(last)}–{wend.strftime("%-d %b %Y")}', nweeks_txt=f'{len(weeks)} week' + ('' if len(weeks) == 1 else 's'),
        raw=usd(head['raw_usd']), clean=usd(head['clean_usd']), share=f'{cleanshare * 100:.0f}%',
        cd=usd(head['tripwire_content_plus_data_clean_usd']), content=usd(head['clean_by_category_usd']['content']),
        growth=growth, payments=f'{head["clean_payments"]:,}', payees=f'{head["clean_payees"]:,}',
        stage_chart=stage_chart, cat_chart=cat_chart, cd_chart=cd_chart, idx_chart=idx_chart, legend=legend,
        rows=''.join(rows), hist=''.join(hist), repo=REPO, lastpost=wk(lastpost) if lastpost else '–',
        posted_weeks=len(po), built=dt.datetime.now(dt.timezone.utc).strftime('%-d %b %Y'))
    os.makedirs(os.path.dirname(SITE), exist_ok=True)
    open(SITE, 'w').write(page)
    print('wrote', SITE, len(page), 'bytes')


TEMPLATE = '''<title>x402 Clean Index</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;600;800&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a single ledger column; one summary strip, then charts, then the tables they summarise. */
:root {{
  --bg: #f6f7f5; --panel: #ffffff; --ink: #121614; --ink-2: #4d5550; --ink-3: #79817c; --rule: #dde1dd; --accent: #0f6b4f;
  --s-content: #2a78d6; --s-data: #eb6834; --s-search: #1baf7a; --s-compute: #eda100; --s-other: #e87ba4; --s-large_ticket: #008300; --s-unclassed: #a9aea9;
  --l-raw: #a9aea9; --l-d05: #eb6834; --l-clean: #2a78d6; --l-transacted: #2a78d6; --l-posted: #eb6834;
  --display: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
  --body: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #121614; --panel: #1a1f1c; --ink: #eef1ee; --ink-2: #b9c0bb; --ink-3: #8a938d; --rule: #2d3430; --accent: #4fc39a;
  --s-content: #3987e5; --s-data: #d95926; --s-search: #199e70; --s-compute: #c98500; --s-other: #d55181; --s-large_ticket: #2f9a2f; --s-unclassed: #6b726d;
  --l-raw: #6b726d; --l-d05: #d95926; --l-clean: #3987e5; --l-transacted: #3987e5; --l-posted: #d95926; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #121614; --panel: #1a1f1c; --ink: #eef1ee; --ink-2: #b9c0bb; --ink-3: #8a938d; --rule: #2d3430; --accent: #4fc39a;
  --s-content: #3987e5; --s-data: #d95926; --s-search: #199e70; --s-compute: #c98500; --s-other: #d55181; --s-large_ticket: #2f9a2f; --s-unclassed: #6b726d;
  --l-raw: #6b726d; --l-d05: #d95926; --l-clean: #3987e5; --l-transacted: #3987e5; --l-posted: #d95926; color-scheme: dark }}
* {{ box-sizing: border-box }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.55 var(--body); margin: 0 }}
.wrap {{ max-width: 920px; margin: 0 auto; padding-inline: 16px; padding-block: 32px 64px; display: grid; gap: 40px }}
header {{ display: grid; gap: 10px }}
.eyebrow {{ font: 500 12px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent) }}
h1 {{ font: 800 clamp(30px, 5vw, 44px)/1.05 var(--display); letter-spacing: -.02em; margin: 0; text-wrap: balance }}
h2 {{ font: 600 20px/1.25 var(--display); margin: 0; text-wrap: balance }}
p {{ margin: 0; max-width: 68ch; color: var(--ink-2) }}
a {{ color: var(--accent) }}
a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px }}
.strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1px; background: var(--rule); border: 1px solid var(--rule); border-radius: 6px; overflow: hidden }}
.stat {{ background: var(--panel); padding: 16px; display: grid; gap: 4px; align-content: start }}
.stat .k {{ font: 500 11px/1.3 var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--ink-3) }}
.stat .v {{ font: 600 26px/1.1 var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -.02em }}
.stat .n {{ font-size: 13px; color: var(--ink-2) }}
section {{ display: grid; gap: 12px; min-width: 0 }}
.cwrap {{ overflow-x: auto }}
.chart {{ width: 100%; min-width: 560px; height: auto; display: block; background: var(--panel); border: 1px solid var(--rule); border-radius: 6px }}
.grid {{ stroke: var(--rule); stroke-width: 1 }}
.tick {{ fill: var(--ink-3); font: 11px var(--mono) }}
.dlabel {{ fill: var(--ink-2); font: 12px var(--body) }}
.hit {{ fill: transparent }} .hit:hover {{ fill: var(--ink); fill-opacity: .04 }}
.ln {{ fill: none; stroke-width: 2 }} .dot {{ stroke: var(--panel); stroke-width: 2 }}
.s-content {{ fill: var(--s-content); background: var(--s-content) }} .s-data {{ fill: var(--s-data); background: var(--s-data) }}
.s-search {{ fill: var(--s-search); background: var(--s-search) }} .s-compute {{ fill: var(--s-compute); background: var(--s-compute) }}
.s-other {{ fill: var(--s-other); background: var(--s-other) }} .s-large_ticket {{ fill: var(--s-large_ticket); background: var(--s-large_ticket) }} .s-unclassed {{ fill: var(--s-unclassed); background: var(--s-unclassed) }}
.l-raw {{ stroke: var(--l-raw); stroke-dasharray: 5 4 }} .l-d05 {{ stroke: var(--l-d05) }} .l-clean {{ stroke: var(--l-clean) }}
.l-transacted {{ stroke: var(--l-transacted) }} .l-posted {{ stroke: var(--l-posted) }}
.d-raw {{ fill: var(--l-raw) }} .d-d05 {{ fill: var(--l-d05) }} .d-clean {{ fill: var(--l-clean) }}
.d-transacted {{ fill: var(--l-transacted) }} .d-posted {{ fill: var(--l-posted) }}
.legend {{ list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--ink-2) }}
.legend li {{ display: flex; align-items: center; gap: 6px }}
.sw {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px }}
.legend .sw {{ margin: 0 }}
.tbl {{ overflow-x: auto; border: 1px solid var(--rule); border-radius: 6px; background: var(--panel) }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; min-width: 640px }}
th, td {{ padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--rule); white-space: nowrap }}
td {{ font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 13px }}
thead th {{ font: 500 11px/1.3 var(--mono); letter-spacing: .05em; text-transform: uppercase; color: var(--ink-3); vertical-align: bottom }}
tbody th, thead th:first-child {{ text-align: left; font-weight: 600 }}
tr.total th, tr.total td {{ border-bottom: 0; font-weight: 600 }}
.iqr {{ color: var(--ink-3); font-size: 12px }}
.note {{ font-size: 13px; color: var(--ink-3) }}
.method {{ display: grid; gap: 10px; border-top: 1px solid var(--rule); padding-top: 24px }}
.method ul {{ margin: 0; padding-left: 20px; color: var(--ink-2); max-width: 72ch; display: grid; gap: 6px }}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">x402 on Base · week of {week}</div>
  <h1>x402 Clean Index</h1>
  <p>What AI agents actually pay for on the x402 payment network, with wash trading, self-payments and single-buyer dust removed and every seller sorted into a category. Weekly, from public chain data and the public Bazaar listing.</p>
</header>

<div class="strip" aria-label="Latest week">
  <div class="stat"><span class="k">Raw settlements</span><span class="v">{raw}</span><span class="n">what a raw tracker would show</span></div>
  <div class="stat"><span class="k">Demand-cleaned</span><span class="v">{clean}</span><span class="n">{share} of raw · {payments} payments to {payees} sellers</span></div>
  <div class="stat"><span class="k">Content + data, cleaned</span><span class="v">{cd}</span><span class="n">{growth}</span></div>
  <div class="stat"><span class="k">Content, cleaned</span><span class="v">{content}</span><span class="n">articles, reports, media, courses</span></div>
</div>

<section>
  <h2 id="t-stage">Most raw volume doesn't survive cleaning</h2>
  <p>Weekly USDC settled, in thousands of dollars, before and after each filter. {nweeks_txt} so far.</p>
  <div class="cwrap">{stage_chart}</div>
</section>

<section>
  <h2 id="t-cat">Cleaned spend by category</h2>
  <ul class="legend">{legend}</ul>
  <div class="cwrap">{cat_chart}</div>
  <p class="note">Hover a column for the split. Categories come from each seller's Bazaar or x402scan listing; sellers with no listing are unclassed.</p>
</section>

<section>
  <h2 id="t-cd">Content and data only</h2>
  <ul class="legend"><li><span class="sw s-content"></span>Content</li><li><span class="sw s-data"></span>Data</li></ul>
  <div class="cwrap">{cd_chart}</div>
  <p class="note">This is the growth tripwire: the marketplace question reopens if this line grows more than 20% a month for three months running.</p>
</section>

<section>
  <h2 id="t-idx">Price per call, chain-linked (first week = 100)</h2>
  <div class="cwrap">{idx_chart}</div>
  <p class="note">Transacted: each cleaned seller's median payment, geometric mean of week-on-week changes for sellers paid in both weeks. Posted: exact-scheme Base USDC prices in the Coinbase Bazaar listing, same method over resources listed in both weeks ({posted_weeks} weekly snapshots so far).</p>
</section>

<section>
  <h2>Latest week by category</h2>
  <div class="tbl"><table>
    <thead><tr><th>Category</th><th>Raw USD</th><th>Clean USD</th><th>Clean payments</th><th>Sellers</th><th>Median paid</th><th>Posted median (IQR), {lastpost}</th><th>Listed</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>

<section>
  <h2>Every week</h2>
  <div class="tbl"><table>
    <thead><tr><th>Week of</th><th>Raw USD</th><th>After manufacture filter</th><th>Demand-cleaned</th><th>Content + data</th><th>Transacted price index</th></tr></thead>
    <tbody>{hist}</tbody>
  </table></div>
</section>

<section class="method">
  <h2>How it's built</h2>
  <ul>
    <li>Settlements are USDC <code>transferWithAuthorization</code> calls sent by 128 known x402 facilitators on Base, read from Blockscout.</li>
    <li>The manufacture filter drops self-payments, closed payment loops and payer–payee pairs linked by funding or sweep transfers (after arXiv 2607.12575). It only removes what it can prove, so cleaned figures are an upper bound on genuine demand.</li>
    <li>The dust filter drops sellers paid by a single buyer in the week.</li>
    <li>A small language model (Mistral Small 3.2) reads each seller's listing and picks a category. It matched 87% of 355 earlier hand labels on content / data / neither, but only 80% (24 of 30) in a blind hand check of new sellers, so treat category splits as approximate.</li>
    <li>Sellers with no listing stay unclassed, except the largest ones whose typical payment is above what 99% of listed API calls cost. Those are shown as large ticket (unidentified): a label from price alone, not an identification.</li>
    <li>Base only. Solana x402 and off-chain credit schemes are not counted.</li>
  </ul>
  <p>Full definitions and known biases: <a href="{repo}/docs/X402_INDEX_METHOD.md">method note</a>. Data: <a href="{repo}/data/x402_index/weekly.csv">weekly.csv</a>, <a href="{repo}/data/x402_index/prices_weekly.csv">prices_weekly.csv</a>. Built {built}.</p>
</section>
</div>
'''

if __name__ == '__main__':
    main()
