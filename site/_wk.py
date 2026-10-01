"""wknipe.com build-time components (ORDER_013). Every number on a page is computed here from data files at render time;
nothing is hand-typed. Pages include the fragments these functions return (site/_gen/*.md, written by _pages.py).

Components: stat_card, spark_svg, chart_frame, freshness, term, info, data_table, tool_card, decide.
Client behaviour (tooltips, charts, tables, search) lives in site/assets/wk.js and wk-charts.js."""
import datetime as dt, html, json, math

CATS = ['content', 'data', 'search', 'compute', 'other', 'large_ticket', 'unclassed']
CAT_LABEL = {'content': 'Content', 'data': 'Data', 'search': 'Search', 'compute': 'Compute & tools', 'other': 'Other',
             'large_ticket': 'Large ticket (unidentified)', 'unclassed': 'Unclassed', 'all': 'All categories'}
METHOD = 'https://github.com/doescodinggiteasier/wknipe-site/blob/main/docs/X402_INDEX_METHOD.md'
API = 'https://api.wknipe.com'
esc = lambda s: html.escape(str(s if s is not None else ''), quote=True)


# ---------- number formatting (mirrors WK.fmt in wk.js) ----------
def usd(x, full=False):
    if x is None: return '–'
    a = abs(x); s = '−$' if x < 0 else '$'
    if not full and a >= 1e6: return f'{s}{a / 1e6:.2f}M'
    if not full and a >= 1e4: return f'{s}{a / 1e3:,.0f}k'
    if a >= 100: return f'{s}{a:,.0f}'
    if a >= 1: return f'{s}{a:,.2f}'
    if a == 0: return '$0'
    return s + f'{a:.3g}'


def num(x):
    return '–' if x is None else f'{x:,.0f}'


def pct(x, d=0):
    return '–' if x is None else f'{x * 100:.{d}f}%'


def signed_pct(x, d=0):
    return '–' if x is None else f'{"+" if x >= 0 else "−"}{abs(x) * 100:.{d}f}%'


def week_label(w, year=False):
    d = dt.date.fromisoformat(str(w)[:10])
    return d.strftime('%-d %b %Y' if year else '%-d %b')


# ---------- small pieces ----------
def info(tip_html, label='What is this?'):
    return f'<button type="button" class="info" aria-label="{esc(label)}" data-tip="{esc(tip_html)}">ⓘ</button>'


def term(key, text=None):
    return f'<span class="term" data-term="{esc(key)}">{esc(text or key)}</span>'


def decide(text):
    """Kept for call sites; the page subtitle now says what the page is and what it shows."""
    return ''


def freshness(through, cadence='updates Mondays', stale_days=10):
    d = dt.date.fromisoformat(str(through)[:10])
    stale = (dt.date.today() - d).days > stale_days
    return f'<p class="fresh{" stale" if stale else ""}">Data through {d.isoformat()} · {esc(cadence)}</p>'


def spark_svg(values, w=96, h=30, label='trend'):
    vals = [v if v is not None else 0 for v in values]
    if not vals: return ''
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = (w - 8) / max(1, len(vals) - 1)
    pts = [(4 + i * step, h - 5 - (h - 10) * (v - lo) / rng) for i, v in enumerate(vals)]
    path = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    x, y = pts[-1]
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
            f'<polyline points="{path}" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle class="last" cx="{x:.1f}" cy="{y:.1f}" r="3"/></svg>')


def stat_card(label, value, series=None, delta=None, delta_note='WoW', tip=None, foot=None, higher_is=None, weeks=None):
    """label; big number (already formatted); optional 5-week series for the sparkline and the WoW delta.
    delta: fraction (0.12 = +12%). higher_is: 'good' / 'bad' / None (neutral colouring uses arrows only)."""
    d = ''
    if delta is not None:
        up = delta >= 0
        cls = '' if higher_is is None else ('up' if (up == (higher_is == 'good')) else 'down')
        d = f'<span class="d {cls}"><span aria-hidden="true">{"▲" if up else "▼"}</span> {signed_pct(delta)} <small>{esc(delta_note)}</small></span>'
    elif series is not None and len(series) < 2:
        d = '<span class="d"><small>first week</small></span>'
    sp = ''
    if series and len(series) >= 2:
        lab = f'{label}, last {len(series)} weeks' + (f' ({week_label(weeks[0])} to {week_label(weeks[-1])})' if weeks else '')
        sp = spark_svg(series, label=lab)
    return (f'<div class="stat-card"><div class="k"><span>{esc(label)}</span>{info(tip) if tip else ""}</div>'
            f'<div class="v">{value}</div><div class="row2">{d}{sp}</div>{f"<div class=foot>{foot}</div>" if foot else ""}</div>')


def kpis(cards):
    return '<div class="kpis">' + ''.join(cards) + '</div>'


def chips(key, options, current):
    return '<div class="ctrl" role="group">' + ''.join(
        f'<button type="button" class="chip" data-act="opt" data-k="{esc(key)}" data-v="{esc(v)}" aria-pressed="{str(v == current).lower()}">{esc(lab)}</button>'
        for v, lab in options) + '</div>'


def chart_frame(fid, title, subtitle, kind=None, src=None, opts=None, controls='', body='', csv=None, metric=None,
                through=None, note=None, page='/x402/', table=True):
    """A chart with a finding as its title, the denominator as its subtitle, and the standard footer:
    Download CSV · JSON via API · Cite · Permalink (+ Table view)."""
    cite = f'Wes Knipe, "{title}", wknipe.com{page}#{fid}' + (f', data through {through}' if through else '') + '. CC BY 4.0.'
    foot = []
    if csv: foot.append(f'<a href="{esc(csv)}" download>Download CSV</a>')
    elif kind and table: foot.append('<button type="button" data-act="csv">Download CSV</button>')
    if metric: foot.append(f'<a href="{API}/v1/series?metric={esc(metric)}">JSON via API</a>')
    foot.append(f'<button type="button" data-act="cite" data-cite="{esc(cite)}">Cite</button>')
    foot.append(f'<button type="button" data-act="link">Permalink</button>')
    if kind and table: foot.append('<button type="button" data-act="table" aria-expanded="false">Table</button>')
    if note: foot.append(f'<span class="note">{note}</span>')
    attrs = f' data-chart="{esc(kind)}"' if kind else ''
    if src: attrs += f' data-src="{esc(src)}"'
    if opts: attrs += f" data-opts='{esc(json.dumps(opts))}'"
    return (f'<figure class="chart-frame" id="{esc(fid)}"{attrs}><h2 class="t">{title}</h2><p class="s">{subtitle}</p>{controls}'
            f'<div class="plot">{body or ("<p class=meta>Loading chart…</p>" if kind else "")}</div>'
            f'<figcaption class="foot">{" · ".join(foot)}</figcaption></figure>')


def data_table(tid, cols, rows=None, src=None, path=None, facets=None, sort=None, dir='desc', page_size=25, placeholder='Filter',
               csv_name=None, search=None):
    """Client-side table: sticky header, sort, text filter, facet chips, pagination, CSV export, cards under 640px.
    cols: [{k, label, t: usd|int|pct|pct1|price|text|html, r: right-align}]. html cells carry k_s (sort) and k_t (CSV/search)."""
    cfg = {'cols': cols, 'sort': sort, 'dir': dir, 'pageSize': page_size, 'placeholder': placeholder, 'csvName': csv_name or f'{tid}.csv'}
    if rows is not None: cfg['rows'] = rows
    if src: cfg['src'] = src
    if path: cfg['path'] = path
    if facets: cfg['facets'] = facets
    if search: cfg['search'] = search
    js = json.dumps(cfg, separators=(',', ':'), default=str).replace('</', '<\\/')
    return f'<div class="wk-table" id="{esc(tid)}"><script type="application/json">{js}</script></div>'


def tool_card(kind, name, desc, href, go='Open'):
    return (f'<a class="tool-card" href="{esc(href)}"><span class="kind">{esc(kind)}</span><span class="nm">{esc(name)}</span>'
            f'<span class="ds">{desc}</span><span class="go">{esc(go)} →</span></a>')


def cat_dot(c):
    return f'<i class="cat-dot" style="background:var(--c-{esc(c)})"></i>'


def seller_cell(address, label, sub=None, page=True):
    short = f'{address[:6]}…{address[-4:]}'
    name = esc(label) if label else f'<code>{short}</code>'
    a = f'<a href="/x402/sellers/{address}">{name}</a>' if page else name
    return a + (f'<span class="sub">{esc(sub)}</span>' if sub else (f'<span class="sub"><code>{short}</code></span>' if label else ''))


def md(html_str):
    """Wrap raw HTML so Quarto passes it through untouched."""
    return '```{=html}\n' + html_str + '\n```\n'


def growth(a, b):
    return None if a in (None, 0) or b is None else b / a - 1


def log_bins_label(lo):
    return usd(lo, full=True)
