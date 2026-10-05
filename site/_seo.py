"""ORDER_014 addendum I: search and AI discoverability, applied to the rendered site (called by _postrender.py).

- robots.txt: explicit User-agent / Allow + Sitemap.
- sitemap.xml: canonical URLs (trailing slash, no index.html, no .html), seller pages at low priority; noindex pages,
  drafts and the 404 page left out.
- <link rel="canonical"> on every page.
- JSON-LD: Person (home, About), Dataset (Market, Sellers, Prices, Status, AI access), Article (writing, weekly).
- /llms.txt (llmstxt.org) and /llms-full.txt (method summary + the latest headline numbers), regenerated every build.
"""
import datetime as dt, glob, json, os, re

from _pages import Data, D, rcsv, rjson, f, ROOT
from _wk import usd, num, pct, week_label, METHOD, API, esc
import _conditional

SITE_URL = 'https://wknipe.com'
GITHUB = 'https://github.com/doescodinggiteasier'
REPO = GITHUB + '/wknipe-site'
LICENCE = 'https://creativecommons.org/licenses/by/4.0/'
# TODO(Wes): add your LinkedIn URL to SAME_AS (and nothing you don't want linked to this site).
SAME_AS = [GITHUB]
PERSON = {'@type': 'Person', '@id': SITE_URL + '/#wes', 'name': 'Wes Knipe', 'url': SITE_URL + '/', 'email': 'mailto:wes@wknipe.com',
          'description': 'Analytics consultant. Studied quantitative economics at Cal Poly; worked at financial advisory firms and in early-stage software.',
          'sameAs': SAME_AS}


def url_of(rel):
    """_site-relative file path -> canonical URL (Cloudflare serves foo.html at /foo and dir/index.html at /dir/)."""
    rel = rel.replace(os.sep, '/')
    if rel == 'index.html': return SITE_URL + '/'
    if rel.endswith('/index.html'): return f'{SITE_URL}/{rel[:-len("index.html")]}'
    return f'{SITE_URL}/{rel[:-5]}'


def _ld(obj):
    return '<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', **obj}, ensure_ascii=False).replace('</', '<\\/') + '</script>'


def datasets(d):
    lw, W = d.latest, d.weeks
    cov = f'{W[0]}/{d.through}' if W else None
    base = {'creator': PERSON, 'license': LICENCE, 'isAccessibleForFree': True, 'temporalCoverage': cov,
            'dateModified': d.through, 'includedInDataCatalog': {'@type': 'DataCatalog', 'name': 'wknipe.com data', 'url': SITE_URL + '/api/'}}
    dl = lambda name, path: {'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'name': name, 'contentUrl': SITE_URL + path}
    api = lambda metric: {'@type': 'DataDownload', 'encodingFormat': 'application/json', 'name': f'{metric} (JSON API)', 'contentUrl': f'{API}/v1/series?metric={metric}'}
    clean = d.w(lw, 'clean', 'all'); raw = d.w(lw, 'raw', 'all')
    st = d.status or {}; A = d.access or {}
    out = {
        '/x402/': {'name': 'x402 Clean Index: demand-cleaned agent payments on Base',
                   'description': f'Weekly USDC settlements sent by known x402 facilitators on Base, before and after removing self-payments, closed loops, funding-linked pairs, fan-out manufacture and single-buyer sellers. Week of {week_label(lw, True)}: {usd(raw)} settled, {usd(clean)} demand-cleaned. Includes category mix, concentration, buyers, retention, ticket sizes and facilitator shares.',
                   'distribution': [dl('Weekly series', '/x402/data/weekly.csv'), dl('Waterfall', '/x402/data/waterfall.csv'), dl('Single-buyer threshold sensitivity', '/x402/data/buyer_threshold_sensitivity.csv'), api('weekly'), api('waterfall')]},
        '/x402/sellers/': {'name': 'x402 seller leaderboard',
                           'description': 'Every x402 seller (payTo address on Base) with at least five genuine buyers in the latest index week: demand-cleaned USD, buyers, repeat-buyer rate, top-buyer share, posted and paid median price. Updated weekly.',
                           'distribution': [dl('Sellers, latest week', '/x402/data/sellers_latest.csv')]},
        '/x402/prices/': {'name': 'x402 posted prices per call',
                          'description': 'Posted USDC prices per call for every x402 listing in the Coinbase CDP Bazaar, by category; a chain-linked Jevons price index of posted and transacted prices; and daily posted-price changes.',
                          'distribution': [dl('Posted price by category', '/x402/data/posted_by_category.csv'), dl('Price index', '/x402/data/prices_weekly.csv'), dl('Price changes', '/x402/data/price_changes.csv'), api('prices_weekly')]},
        '/x402/status/': {'name': 'x402 endpoint status monitor',
                          'description': 'A daily unpaid check of listed x402 endpoints: whether each answers HTTP 402 with a valid payment request, and whether its live price and payTo match the listing.' + (f' Latest check {st.get("latest_day")}.' if st.get('latest_day') else ''),
                          'temporalCoverage': None, 'distribution': [dl('Daily status', '/x402/data/status_daily.csv'), dl('Latest check per endpoint', '/x402/data/status_latest.csv'), api('status_daily')]},
        '/access/': {'name': 'State of AI access: AI-crawler rules of the top 1,000 websites',
                     'description': 'Weekly census of the Tranco top 1,000 domains: which AI crawlers each robots.txt blocks by name, and adoption of machine-readable access signals (content signals, licences, llms.txt, HTTP 402 pricing).',
                     'temporalCoverage': None, 'distribution': [dl('Weekly shares', '/x402/data/access_weekly.csv'), dl('Latest per domain', '/x402/data/access_latest.csv'), api('access_weekly')]},
    }
    res = {}
    for path, x in out.items():
        obj = {'@type': 'Dataset', 'url': SITE_URL + path, **base, **x}
        res[path] = {k: v for k, v in obj.items() if v is not None}
    return res


def articles(site):
    res = {}
    for qmd in glob.glob(os.path.join(os.path.dirname(site), 'writing', '*.qmd')) + glob.glob(os.path.join(os.path.dirname(site), 'weekly', '20*.qmd')):
        fm = open(qmd).read().split('---')[1]
        if re.search(r'^draft:\s*true', fm, re.M): continue
        t = re.search(r'^title:\s*"?(.*?)"?\s*$', fm, re.M); dd = re.search(r'^date:\s*"?([\d-]+)', fm, re.M)
        rel = os.path.relpath(qmd, os.path.dirname(site))[:-4] + '.html'
        res[url_of(rel)[len(SITE_URL):]] = {'@type': 'Article', 'headline': t.group(1) if t else '', 'datePublished': dd.group(1) if dd else None,
                                            'author': PERSON, 'url': url_of(rel), 'license': LICENCE}
    return res


def apply(site):
    d = Data()
    ld = {path: [obj] for path, obj in datasets(d).items()}
    for path, obj in articles(site).items(): ld.setdefault(path, []).append(obj)
    person = {**PERSON}
    ld.setdefault('/', []).append(person); ld.setdefault('/about', []).append(person)
    urls = []
    for p in sorted(glob.glob(os.path.join(site, '**', '*.html'), recursive=True)):
        rel = os.path.relpath(p, site)
        if rel in ('404.html',) or rel.startswith('site_libs'): continue
        html = open(p, encoding='utf-8').read()
        if '</head>' not in html: continue
        u = url_of(rel); path = u[len(SITE_URL):]
        noindex = 'name="robots" content="noindex"' in html
        add = ''
        if 'rel="canonical"' not in html: add += f'<link rel="canonical" href="{esc(u)}">'
        if 'application/ld+json' not in html: add += ''.join(_ld(o) for o in ld.get(path, []))
        if add: open(p, 'w', encoding='utf-8').write(html.replace('</head>', add + '</head>', 1))
        if not noindex: urls.append((u, os.path.getmtime(p), rel))
    pri = lambda u, rel: '1.0' if u == SITE_URL + '/' else '0.3' if rel.startswith('x402/sellers/0x') or rel.startswith('weekly/20') else '0.8'
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, t, rel in sorted(urls, key=lambda x: (pri(x[0], x[2]) != '1.0', pri(x[0], x[2]) == '0.3', x[0])):
        sm.append(f'  <url><loc>{esc(u)}</loc><lastmod>{dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()}</lastmod><priority>{pri(u, rel)}</priority></url>')
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap.xml'), 'w').write('\n'.join(sm) + '\n')
    open(os.path.join(site, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n')
    llms(d, site)
    return len(urls)


PAGES = [  # (title, path, one line) for llms.txt
    ('Market dashboard', '/x402/', 'Weekly x402 volume on Base before and after cleaning, category mix, concentration, buyers, facilitators.'),
    ('Sellers', '/x402/sellers/', 'Every seller with 5+ genuine buyers: revenue, repeat buyers, top-buyer share.'),
    ('Buyers', '/x402/buyers/', 'Genuine buyers per week, retention, spend tiers.'),
    ('Prices', '/x402/prices/', 'Posted prices per call, price index, daily price changes.'),
    ('Price comps', '/x402/prices/comps', 'Comparable x402 listings for a described API, their prices and whether their sellers have buyers.'),
    ('Endpoint status', '/x402/status/', 'Daily unpaid check that listed endpoints answer a valid 402 at their listed price.'),
    ('State of AI access', '/access/', 'Which of the top 1,000 websites block AI crawlers, and which state a price.'),
    ('Agent benchmark', '/agents/', 'How sensibly AI models make purchase decisions, and what they cost.'),
    ('Weekly report', '/weekly/', 'The numbers in one short note each Monday.'),
    ('One-page brief', '/x402/brief/', 'State of x402 on one printable page.'),
    ('x402 in 60 seconds', '/x402/explained/', 'Plain-English explainer for readers who know markets better than crypto.'),
    ('Prediction ledger', '/predictions/', 'Timestamped forecasts, scored when they resolve.'),
    ('About', '/about', 'Who I am, the research question, résumé and contact.'),
]


def headline(d):
    lw = d.latest; raw = d.w(lw, 'raw', 'all'); clean = d.w(lw, 'clean', 'all')
    bw = d.market['buyers_weekly'][-1]
    return [f'Week of {week_label(lw, True)} (data through {d.through}):',
            f'- Settled through x402 facilitators on Base: {usd(raw)} ({num(d.w(lw, "raw", "all", "payments"))} payments).',
            f'- Demand-cleaned: {usd(clean)} ({pct(clean / raw)} of settled), {num(d.w(lw, "clean", "all", "payees"))} sellers with 2+ genuine buyers.',
            f'- Genuine buyer wallets: {num(int(bw["active_buyers"]))}, of which {num(int(bw["new_buyers"]))} new; median weekly spend {usd(float(bw["median_spend_usd"]), True)}.']


def llms(d, site):
    intro = ('I am Wes Knipe, an analytics consultant with a background in quantitative economics (Cal Poly), financial advisory firms and early-stage software. '
             'This site is my independent research on how AI agents pay for things. It measures x402, a web standard for paying per request in USDC on the Base network: '
             'how much of the reported volume is genuine demand once self-payments, loops, tests and single-customer sellers are removed, who buys and comes back, what calls cost, '
             'and whether sellers deliver. Data is public, CC BY 4.0; code is MIT.')
    L = ['# Wes Knipe', '', f'> {intro}', '', '## Key pages', '']
    L += [f'- [{t}]({SITE_URL}{p}): {x}' for t, p, x in PAGES if _conditional.show(p)]
    L += ['', '## Method and API', '',
          f'- [Method note]({METHOD}): every filter, category rule and known bias of the x402 Clean Index.',
          f'- [API docs]({SITE_URL}/api/): free JSON for every chart series (rate-limited), paid x402 endpoints for bulk history and routing.',
          f'- [MCP server]({REPO}/tree/main/apps/x402-index-mcp): the index as tools for AI assistants.',
          f'- [Full text for LLMs]({SITE_URL}/llms-full.txt): method summary and the latest headline numbers.',
          '', '## Datasets', '',
          f'- [Weekly series (CSV)]({SITE_URL}/x402/data/weekly.csv): payments, USD, sellers, buyers by filter stage and category.',
          f'- [Waterfall (CSV)]({SITE_URL}/x402/data/waterfall.csv): USD each filter removes, per week.',
          f'- [Sellers (CSV)]({SITE_URL}/x402/data/sellers_latest.csv): sellers with 5+ genuine buyers, latest week.',
          f'- [Endpoint status (CSV)]({SITE_URL}/x402/data/status_daily.csv): daily share of endpoints answering a valid 402.',
          f'- [AI access (CSV)]({SITE_URL}/x402/data/access_weekly.csv): share of top sites blocking each AI crawler.',
          f'- [All data (GitHub)]({REPO}/tree/main/data): every published CSV and JSON, updated weekly.',
          '', '## Optional', '',
          f'- [Résumé (PDF)]({SITE_URL}/files/wes-knipe-resume.pdf)', '- Contact: wes@wknipe.com']
    open(os.path.join(site, 'llms.txt'), 'w').write('\n'.join(L) + '\n')
    m = open(os.path.join(ROOT, 'docs', 'X402_INDEX_METHOD.md')).read()
    secs = {p.split('\n', 1)[0].strip(): p.split('\n', 1)[1].strip() for p in m.split('\n## ')[1:]}
    keep = [k for k in secs if k.split('.')[0] in ('1', '2', '3', '6')]
    F = ['# Wes Knipe: how AI agents pay for things (full text for LLMs)', '', f'> {intro}', '', f'Source: {SITE_URL}/ · generated {dt.date.today().isoformat()} at build', '',
         '## Latest headline numbers', ''] + headline(d) + ['', '## Method summary (x402 Clean Index)', '', f'Full method note: {METHOD}', '']
    for k in keep: F += [f'### {k}', '', secs[k], '']
    F += ['## Pages', ''] + [f'- {t}: {SITE_URL}{p} ({x})' for t, p, x in PAGES if _conditional.show(p)]
    open(os.path.join(site, 'llms-full.txt'), 'w').write('\n'.join(F) + '\n')
