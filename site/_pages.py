"""Pre-render (ORDER_013): computes every number and finding from the data files and writes the page fragments that the
.qmd pages include (site/_gen/*.md, not committed), plus client assets built from data (glossary, search indexes) and
the downloadable data files next to each page. Run by _prerender.py on every render."""
import csv, datetime as dt, glob, gzip, json, math, os, re, shutil, statistics, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
GEN = os.path.join(HERE, '_gen')
sys.path.insert(0, HERE)
from _wk import *  # noqa: E402,F401

D = lambda *p: os.path.join(ROOT, 'data', *p)


def rcsv(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def rjson(path, default=None):
    if not os.path.exists(path): return default
    with (gzip.open(path, 'rt') if path.endswith('.gz') else open(path)) as f:
        return json.load(f)


def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def write(name, text):
    os.makedirs(GEN, exist_ok=True)
    open(os.path.join(GEN, name), 'w').write(text)


class Data:
    """Everything the pages read, loaded once."""
    def __init__(self):
        self.head = rjson(D('x402_index', 'headline.json'), {})
        self.weekly = rcsv(D('x402_index', 'weekly.csv'))
        self.payees = rcsv(D('x402_index', 'payees_weekly.csv'))
        self.market = rjson(D('x402_market', 'market.json'), {})
        self.prices = rjson(D('x402_prices', 'prices.json'), {})
        self.sellers = rjson(D('x402_sellers', 'sellers.json'), {'sellers': [], 'weeks': []})
        self.extra = rjson(D('x402_market', 'sellers_extra.json'), {'sellers': {}})
        self.status = rjson(D('x402_status', 'status.json'), None)
        self.access = rjson(D('ai_access', 'access.json'), None)
        self.daily = rcsv(D('bazaar_daily', 'counts.csv'))
        self.weeks = self.market.get('weeks') or self.head.get('weeks_available') or []
        self.latest = self.weeks[-1] if self.weeks else None
        self.through = (dt.date.fromisoformat(self.latest) + dt.timedelta(days=6)).isoformat() if self.latest else None

    def w(self, week, stage, cat, k='usd'):
        for r in self.weekly:
            if r['week_start'] == week and r['stage'] == stage and r['category'] == cat: return f(r[k])
        return None

    def series(self, stage, cat, k='usd'):
        return [self.w(w, stage, cat, k) for w in self.weeks]


# ------------------------------------------------------------------ copies of data files for download
def copy_data(d):
    dst = os.path.join(HERE, 'x402', 'data')
    os.makedirs(dst, exist_ok=True)
    for p in glob.glob(D('x402_market', '*.csv')) + [D('x402_market', 'market.json')]:
        shutil.copy(p, dst)
    for n in ('prices.json', 'posted_vs_paid.csv', 'posted_by_category.csv', 'listings.json', 'listings_latest.csv.gz'):
        if os.path.exists(D('x402_prices', n)): shutil.copy(D('x402_prices', n), dst)
    for sub, names in (('x402_status', ('status.json', 'status_daily.csv', 'status_latest.csv')), ('ai_access', ('access.json', 'access_weekly.csv', 'access_latest.csv')),
                       ('bazaar_daily', ('counts.csv', 'price_changes.csv'))):
        for n in names:
            if os.path.exists(D(sub, n)): shutil.copy(D(sub, n), dst)


# ------------------------------------------------------------------ glossary + search
GLOSSARY = {
    'clean': ('Demand-cleaned', 'What survives every filter: our own payments, closed payment loops, funding-linked payer–seller pairs, fan-out manufacture and single-buyer sellers are removed. An upper bound on genuine demand, because the manufacture filters are lower bounds.', METHOD + '#2-filters-in-this-order'),
    'demand-cleaned': ('Demand-cleaned', 'Same as "clean": what survives every filter. An upper bound on genuine demand.', METHOD + '#2-filters-in-this-order'),
    'manufactured': ('Manufactured volume', 'Payments where buyer and seller are provably the same operator: self-payments and closed loops (C1), payer and seller funded from the same wallets (C2), and fan-out from shared funders to throwaway buyers.', METHOD + '#2-filters-in-this-order'),
    'single-buyer': ('Single-buyer seller', 'A seller paid by exactly one distinct buyer in the week. Its payments are dropped as dust: usually a test, or one operator paying itself with two wallets.', METHOD + '#2-filters-in-this-order'),
    'd05': ('D05 filter', 'The manufacture filter from arXiv 2607.12575 ("D05"), approximated with public Blockscout data: C1 fictitious (loops) and C2 internal (shared funding). It found 85% of Base x402 settlements operator-internal; our approximation removes less, so it is a lower bound.', METHOD + '#2-filters-in-this-order'),
    'posted vs paid': ('Posted vs paid', 'Posted = the price a listing asks for one call in the Coinbase CDP Bazaar. Paid = what demand-cleaned payments actually settled on chain. Posted medians weight each listing equally; paid medians weight each payment.', METHOD + '#4-prices'),
    'posted': ('Posted price', 'The exact-scheme USDC amount a Bazaar listing asks for one call.', METHOD + '#4-prices'),
    'paid': ('Paid price', 'The amount of a demand-cleaned payment on chain (USDC on Base).', METHOD + '#4-prices'),
    'genuine buyer': ('Genuine buyer', 'A payer address with at least one demand-cleaned payment in the week. One operator can run many wallets, so this counts wallets, not companies.', METHOD + '#1-units-and-definitions'),
    'genuine buyers': ('Genuine buyers', 'Payer addresses with at least one demand-cleaned payment in the week. Wallets, not companies.', METHOD + '#1-units-and-definitions'),
    'fan-out': ('Fan-out manufacture', 'Many one-time buyers funded by the same few wallets, paying one seller and nobody else. Flagged only when the funding is shared AND circular or isolated.', METHOD + '#2-filters-in-this-order'),
    'facilitator': ('Facilitator', 'The service that submits an x402 payment on chain for the buyer. We count settlements sent by 128 known facilitator addresses on Base.', METHOD + '#1-units-and-definitions'),
    'hhi': ('HHI', 'Herfindahl–Hirschman index: the sum of squared seller shares (in %), from 0 to 10,000. Above 2,500 is "highly concentrated" under US merger guidelines.', None),
    'effective sellers': ('Effective sellers', '1 ÷ Σ share²: the number of equal-sized sellers that would give the same concentration.', None),
    'jevons': ('Jevons index', 'A chain-linked geometric mean of week-on-week price changes over items present in both weeks; first week = 100.', METHOD + '#4-prices'),
    'tripwire': ('Growth tripwire', 'Our pre-committed rule: the marketplace question reopens if demand-cleaned content + data spend grows more than 20% a month for three months running.', METHOD + '#3a-reading-the-tripwire-analysis-2026-09-30-datax402_indexanalysisjson'),
    'large ticket': ('Large ticket (unidentified)', 'An unlisted seller whose median clean payment is above the 99th percentile of posted per-call prices. A label from price alone, not an identification.', METHOD + '#3-categories'),
    'repeat-buyer rate': ('Repeat-buyer rate', 'Share of a seller\'s genuine buyers who paid it at least twice in the week.', None),
    'top-buyer share': ('Top-buyer share', 'Share of a seller\'s demand-cleaned USD that came from its single largest buyer. High values mean the revenue depends on one wallet; it is a risk signal, not an accusation.', None),
    'multi-homing': ('Multi-homing', 'A buyer paying two or more different sellers in the same week.', None),
    'retention': ('Retention', 'Share of a week\'s new genuine buyers who make another demand-cleaned payment k weeks later.', None),
    'wow': ('WoW', 'Week on week: the change from the previous week.', None),
}


def build_assets(d):
    ad = os.path.join(HERE, 'assets')
    json.dump({k: {'term': t, 'def': dfn, 'href': h} for k, (t, dfn, h) in GLOSSARY.items()}, open(os.path.join(ad, 'glossary.json'), 'w'))
    pages = [
        ('Market', 'x402 market dashboard: demand-cleaned volume, buyers, concentration, ticket sizes, facilitators', '/x402/'),
        ('Sellers', 'x402 seller leaderboard with repeat-buyer rate and top-buyer share', '/x402/sellers/'),
        ('Buyers', 'Genuine buyers per week, retention, spend tiers', '/x402/buyers/'),
        ('Prices', 'Posted vs paid prices per call, price index', '/x402/prices/'),
        ('Price comps', 'Compare your API price with comparable x402 listings and whether they get buyers', '/x402/prices/comps'),
        ('Best execution', 'Cheapest verified x402 endpoint for a task; buy-side router for agents', '/x402/buy/'),
        ('Where to build', 'x402 supply vs demand by listing topic: which kinds of API get genuine buyers', '/x402/gaps/'),
        ('State of x402, one page', 'One-page printable brief: genuine volume, buyers, sellers, prices', '/x402/brief/'),
        ('Endpoint status', 'Do x402 endpoints answer a valid 402? Daily monitor', '/x402/status/'),
        ('AI-policy checker', 'Check any website\'s robots.txt, AI crawler rules, content signals and 402', '/check/'),
        ('State of AI access', 'Share of top websites blocking each AI crawler', '/access/'),
        ('Agent benchmark', 'Which AI models make good purchase decisions', '/agents/'),
        ('API', 'Free JSON series for every chart, paid x402 endpoints, MCP server', '/api/'),
        ('This week in x402', 'Weekly numbers-only report with RSS', '/weekly/'),
        ('Badges', 'Embeddable SVG badges for sellers, publishers and endpoints', '/badges/'),
        ('About', 'About this site, method and privacy', '/about'),
        ('Method note', 'x402 Clean Index method: filters, categories, biases', METHOD),
    ]
    core = [{'t': t, 's': s, 'u': u, 'ty': 'page'} for t, s, u in pages]
    for s in d.sellers['sellers']:
        a = s['address']
        core.append({'t': s['label'] or f'{a[:6]}…{a[-4:]}', 's': f"{CAT_LABEL.get(s['category'], s['category'])} seller" + (f" · {', '.join(s['hosts'][:2])}" if s['hosts'] else ''),
                     'x': ' '.join([a] + s['hosts']), 'u': f'/x402/sellers/{a}', 'ty': 'seller'})
    for k, (t, dfn, h) in GLOSSARY.items():
        if k == t.lower() or k in ('d05', 'hhi', 'wow'):
            core.append({'t': t, 's': dfn[:110], 'u': h or '/x402/', 'ty': 'term'})
    json.dump(core, open(os.path.join(ad, 'search-core.json'), 'w'), separators=(',', ':'))
    lp = D('x402_prices', 'listings.json')
    if os.path.exists(lp):
        L = json.load(open(lp)); ci = {c: i for i, c in enumerate(L['cols'])}
        seen, out = set(), []
        for r in L['rows']:
            k = (r[ci['host']], r[ci['what']])
            if k in seen: continue  # one entry per host + what: listings from one seller are often near-identical
            seen.add(k)
            sel = L['sellers'][r[ci['seller']]] if r[ci['seller']] is not None else None
            u = f"/x402/sellers/{sel[0]}" if sel and sel[3] else f"/x402/prices/comps?find={(r[ci['what']] or r[ci['name']] or '').replace(' ', '+')}"
            out.append({'t': r[ci['name']] or r[ci['what']] or r[ci['host']], 's': f"{r[ci['host']]} · {r[ci['what']] or ''} · {usd(r[ci['price_usd']]) if r[ci['price_usd']] else 'unpriced'}",
                        'x': f"{r[ci['what']] or ''} {r[ci['host']]}", 'u': u})
        json.dump(out, open(os.path.join(ad, 'search-listings.json'), 'w'), separators=(',', ':'))


# ------------------------------------------------------------------ home
TOOLS = [
    ('Data', 'Market', 'Demand-cleaned x402 volume, the raw→clean waterfall, buyers, concentration, ticket sizes and facilitators.', '/x402/'),
    ('Data', 'Sellers', 'Every seller with 5+ genuine buyers, with repeat-buyer rate and top-buyer share.', '/x402/sellers/'),
    ('Data', 'Buyers', 'How many genuine buyers pay each week, whether they come back, and how much they spend.', '/x402/buyers/'),
    ('Data', 'Prices', 'What listings ask versus what buyers actually pay, by category, with a price index.', '/x402/prices/'),
    ('Tool', 'Best execution', 'Tell it what your agent needs: the cheapest x402 endpoint that verifiably answers, and the one buyers use.', '/x402/buy/'),
    ('Tool', 'Price comps', 'Describe your API: see comparable listings, their price range, and whether they get buyers.', '/x402/prices/comps'),
    ('Data', 'Where to build', 'Which kinds of paid API have sellers real buyers use, and which are crowded with listings nobody pays for.', '/x402/gaps/'),
    ('Tool', 'Endpoint status', 'Which x402 endpoints answer a valid 402 with the price they list. Checked daily.', '/x402/status/'),
    ('Tool', 'AI-policy checker', 'What a website tells AI crawlers: robots.txt rules per bot, content signals, licences and 402.', '/check/'),
    ('Data', 'State of AI access', 'Share of the top websites blocking each AI crawler, and who answers 402.', '/access/'),
    ('Benchmark', 'Agent benchmark', 'Which AI models make good purchase decisions, and at what cost per 1,000 decisions.', '/agents/'),
    ('API', 'API & data', 'Free JSON for every chart, CSV downloads, paid x402 endpoints and an MCP server.', '/api/'),
    ('Brief', 'State of x402, one page', 'The numbers investors and journalists ask for first, on one printable, citable page.', '/x402/brief/'),
]


def page_exists(href):
    p = href.strip('/').split('?')[0]
    return any(os.path.exists(os.path.join(HERE, p, n)) for n in ('index.qmd',)) or os.path.exists(os.path.join(HERE, p + '.qmd'))


def writing_posts():
    posts = []
    for p in sorted(glob.glob(os.path.join(HERE, 'writing', '*.qmd'))):
        if p.endswith('index.qmd'): continue
        fm = open(p).read().split('---')[1] if open(p).read().startswith('---') else ''
        if re.search(r'^draft:\s*true', fm, re.M): continue
        t = re.search(r'^title:\s*"?(.*?)"?\s*$', fm, re.M); dd = re.search(r'^date:\s*"?([\d-]+)', fm, re.M)
        posts.append((dd.group(1) if dd else '', t.group(1) if t else os.path.basename(p), '/writing/' + os.path.basename(p)[:-4]))
    return sorted(posts, reverse=True)


def home(d):
    W = d.weeks
    clean = d.series('clean', 'all'); cd = [d.head['content_plus_data_clean_usd_by_week'].get(w) for w in W]
    buyers = [r['active_buyers'] for r in d.market['buyers_weekly']]; buyers = [int(b) for b in buyers]
    sellers = d.series('clean', 'all', 'payees')
    g = lambda s: growth(s[-2], s[-1]) if len(s) >= 2 else None
    lst = d.prices.get('listings')
    daily = [int(r['listings']) for r in d.daily][-35:] if d.daily else []
    cards = [
        stat_card('Demand-cleaned $ / week', usd(clean[-1]), clean, g(clean), tip=f'USD paid through x402 on Base in the week of {week_label(d.latest)}, after removing manufactured, single-buyer and our own payments. <a href="/x402/#waterfall">See the waterfall →</a>', weeks=W),
        stat_card('Content + data $ / week', usd(cd[-1]), cd, g(cd), tip='Demand-cleaned USD paid to sellers of content (articles, reports, media) and data (prices, records, enrichment): the categories our growth tripwire watches.', weeks=W),
        stat_card('Genuine buyers / week', num(buyers[-1]), buyers, g(buyers), tip='Payer wallets with at least one demand-cleaned payment in the week. Wallets, not companies.', weeks=W),
        stat_card('Active sellers / week', num(sellers[-1]), sellers, g(sellers), tip='Seller addresses with demand-cleaned payments from at least two distinct buyers in the week.', weeks=W),
        stat_card('Bazaar listings', num(lst), daily if len(daily) >= 2 else None, growth(daily[-8], daily[-1]) if len(daily) >= 8 else None, delta_note='vs 7 days ago',
                  tip=f'Paid API listings in the Coinbase CDP Bazaar discovery index, snapshot {d.prices.get("snapshot")}. {num(d.prices.get("priced"))} have a single posted USDC price.'),
    ]
    st = next((r for r in (d.status or {}).get('latest', []) if r['scope'] == 'all'), None)
    if st:
        cards.append(stat_card('Endpoints answering 402', pct(f(st['valid_402'])), foot=f'of {num(st["checked"])} checked daily',
                               tip='Share of listed x402 endpoints our unpaid daily check found answering a valid 402 with a parseable payment offer. <a href="/x402/status/">Endpoint status →</a>'))
    live = [t for t in TOOLS if page_exists(t[3]) or t[3].startswith('http')]
    grid = lambda kinds: '<div class="tool-grid">' + ''.join(tool_card(k, n, ds, h) for k, n, ds, h in live if k in kinds) + '</div>'
    tools = ('<h2>Data</h2><p class="meta">Weekly numbers on who buys, who sells and at what price, with manufactured volume removed.</p>' + grid(('Data', 'Brief'))
             + '<h2>Tools</h2><p class="meta">Answer one question for your own API, agent or website.</p>' + grid(('Tool', 'Benchmark', 'API')))
    posts = writing_posts()
    wr = ''
    if posts:
        wr = '<h2>Writing</h2><ul class="rows">' + ''.join(f'<li><a href="{esc(u)}"><span class="d">{esc(dd)}</span><span class="t">{esc(t)}</span><span class="x">→</span></a></li>' for dd, t, u in posts[:5]) + '</ul><p class="more"><a href="/writing/">All writing →</a></p>'
    share = clean[-1] / d.head['raw_usd'] if d.head.get('raw_usd') else None
    out = (f'<p class="eyebrow">Agent payments, measured</p>'
           f'<p class="lede">Independent numbers on what AI agents actually buy and pay for. Of {usd(d.head["raw_usd"])} settled over x402 on Base in the week of {week_label(d.latest)}, '
           f'<b>{pct(share)} survives</b> removing manufactured, single-buyer and test payments.</p>'
           + freshness(d.through) + kpis(cards) + tools + wr)
    write('home.md', md(out))


# ------------------------------------------------------------------ market
def market(d):
    M, W, lw = d.market, d.weeks, d.latest
    wf = [r for r in M['waterfall'] if r['week_start'] == lw]
    raw_all = sum(r['usd'] for r in wf); clean = next(r['usd'] for r in wf if r['step'] == 'clean')
    cuts = sorted((r for r in wf if r['step'] != 'clean' and r['usd'] > 0), key=lambda r: -r['usd'])
    big = cuts[0] if cuts else None
    manuf = sum(r['usd'] for r in wf if r['step'] in ('c1', 'c2', 'fanout'))
    week_opts = [(w, week_label(w)) for w in W]
    mix_l = [r for r in M['category_mix'] if r['week_start'] == lw]
    tot = sum(float(r['usd']) for r in mix_l)
    top_cat = max(mix_l, key=lambda r: float(r['usd']))
    content = next((float(r['usd']) for r in mix_l if r['category'] == 'content'), 0)
    conc = {r['category']: r for r in M['concentration'] if r['week_start'] == lw}
    ca = conc['all']
    most_conc = max((r for c, r in conc.items() if c != 'all' and r['sellers'] >= 3), key=lambda r: r['top1_share'])
    bw = M['buyers_weekly'][-1]
    ret = [r for r in M['retention'] if r['week_1'] not in ('', None)]
    ret1 = statistics.median(float(r['week_1']) for r in ret) if ret else None
    tk = {r['category']: r for r in M['tickets'] if r['week_start'] == lw}
    fac = {}
    for r in M['facilitators']:
        if r['week_start'] != lw: continue
        x = fac.setdefault(r['name'], [0, 0]); x[0] += r['raw_usd']; x[1] += r['clean_usd']
    R = sum(v[0] for v in fac.values()); K = sum(v[1] for v in fac.values())
    top_raw = max(fac.items(), key=lambda kv: kv[1][0]); top_clean = max(fac.items(), key=lambda kv: kv[1][1])
    tw = M['tripwire']; g4 = d.head.get('tripwire_4week_growth'); gm = d.head.get('tripwire_loglinear_monthly_growth_last_5_weeks')
    mv = M['movers']; entered = [m for m in mv if m['kind'] == 'entered']; exited = [m for m in mv if m['kind'] == 'exited']
    names = {s['address']: s['label'] for s in d.sellers['sellers']}
    pages = {s['address'] for s in d.sellers['sellers']}

    clean_s = d.series('clean', 'all'); raw_s = d.series('raw', 'all'); buyers_s = [int(r['active_buyers']) for r in M['buyers_weekly']]
    sellers_s = d.series('clean', 'all', 'payees'); share_s = [c / r for c, r in zip(clean_s, raw_s)]
    g = lambda s: growth(s[-2], s[-1]) if len(s) >= 2 else None
    cards = [
        stat_card('Settled through facilitators', usd(raw_all), raw_s, g(raw_s), tip='Every USDC settlement on Base sent by one of 128 known x402 facilitators in the week, before any filter.', weeks=W),
        stat_card('Demand-cleaned', usd(clean), clean_s, g(clean_s), tip=GLOSSARY['clean'][1], weeks=W),
        stat_card('Share that survives cleaning', pct(clean / raw_all), share_s, None, tip='Demand-cleaned USD ÷ all settled USD.', weeks=W),
        stat_card('Genuine buyers', num(bw['active_buyers']), buyers_s, g(buyers_s), tip=GLOSSARY['genuine buyers'][1], weeks=W),
        stat_card('Active sellers', num(sellers_s[-1]), sellers_s, g(sellers_s), tip='Sellers with demand-cleaned payments from 2+ distinct buyers.', weeks=W),
    ]
    through = d.through
    csvp = '/x402/data/'
    parts = [decide('whether x402 demand is real enough to build on, which categories and facilitators carry it, and how concentrated it is — with manufactured and single-buyer volume already removed.'),
             freshness(through), kpis(cards)]
    parts.append(chart_frame('waterfall', f'{pct(clean / raw_all)} of settled x402 dollars survive cleaning; {big["label"].lower()} remove the most ({usd(big["usd"])})' if big else 'Raw to clean',
        f'USD settled on Base in the week of {week_label(lw, True)} ({num(sum(r["payments"] for r in wf))} payments), and what each filter removes, in the order the index applies them. Manufactured volume (loops, shared funding, fan-out) is {usd(manuf)} ({pct(manuf / raw_all, 1)}).',
        'waterfall', '/x402/data/market.json', {'week': lw}, chips('week', week_opts, lw), csv=csvp + 'waterfall.csv', metric='waterfall', through=through,
        note=f'Filters are lower bounds on manufacture, so "demand-cleaned" is an upper bound on genuine demand. Our own payments: {usd(next(r["usd"] for r in wf if r["step"] == "ours"))} this week. {term("d05", "What is D05?")}'))
    parts.append(chart_frame('mix', f'{CAT_LABEL[top_cat["category"]]} is {pct(float(top_cat["usd"]) / tot)} of demand-cleaned spend; publisher-style content is {usd(content)} ({pct(content / tot, 2)})',
        f'Demand-cleaned USD (or payments) per week by what the seller sells, {week_label(W[0])} – {week_label(lw)} ({len(W)} weeks). Categories come from sellers\' own listings; "unclassed" sellers have none.',
        'mix', '/x402/data/market.json', {'metric': 'usd'}, chips('metric', [('usd', 'USD'), ('payments', 'Payments')], 'usd'), csv=csvp + 'category_mix.csv', metric='category_mix', through=through))
    parts.append(chart_frame('concentration', f'The top 10 sellers take {pct(ca["top10_share"])} of demand-cleaned spend; in {CAT_LABEL[most_conc["category"]].lower()}, one seller takes {pct(most_conc["top1_share"])}',
        f'Share of demand-cleaned USD earned by the largest seller and the 10 largest, per week. Week of {week_label(lw)}: {num(ca["sellers"])} sellers, {term("hhi", "HHI")} {num(ca["hhi"])}, {ca["effective_sellers"]} {term("effective sellers")}.',
        'concentration', '/x402/data/market.json', {'cat': 'all'}, chips('cat', [('all', 'All')] + [(c, CAT_LABEL[c].split(' (')[0]) for c in CATS if c in conc], 'all'),
        csv=csvp + 'concentration.csv', metric='concentration', through=through))
    parts.append('<div class="grid2">' + chart_frame('buyers', f'{num(bw["active_buyers"])} {term("genuine buyers")} paid in the week of {week_label(lw)}; {pct(int(bw["new_buyers"]) / int(bw["active_buyers"]))} were new',
        f'Distinct payer wallets with a demand-cleaned payment, split by whether they paid the week before. The first week has no history. Median {term("retention", "week-1 retention")} of new buyers: {pct(ret1)}.' if ret1 is not None else 'Distinct payer wallets per week.',
        'buyers', '/x402/data/market.json', csv=csvp + 'buyers_weekly.csv', metric='buyers_weekly', through=through)
        + chart_frame('multihoming', f'{pct(1 - bw["multi_homing_share"])} of genuine buyers pay only one seller',
        f'Genuine buyers in the week of {week_label(lw)} by how many distinct sellers they paid ({term("multi-homing")}). Denominator: {num(bw["active_buyers"])} buyers.',
        'spb', '/x402/data/market.json', {'week': lw}, csv=csvp + 'sellers_per_buyer.csv', metric='sellers_per_buyer', through=through) + '</div>')
    parts.append(chart_frame('spend', f'The median genuine buyer spent {usd(float(bw["median_spend_usd"]), True)} in the week',
        f'Genuine buyers by total demand-cleaned spend in the week of {week_label(lw)}, log bins. Denominator: {num(bw["active_buyers"])} buyers. <a href="/x402/buyers/">Buyers page →</a>',
        'hist', '/x402/data/market.json', {'week': lw, 'src': 'buyer_spend_histogram', 'y': 'buyers', 'xlabel': 'USD spent in the week (log bins)'}, csv=csvp + 'buyer_spend_histogram.csv', metric='buyer_spend_histogram', through=through))
    hi = max((r for c, r in tk.items() if c not in ('all',) and r['payments'] >= 20), key=lambda r: r['median_usd'])
    parts.append(chart_frame('tickets', f'The median demand-cleaned payment is {usd(tk["all"]["median_usd"], True)}; {CAT_LABEL[hi["category"]].lower()} runs {hi["median_usd"] / tk["all"]["median_usd"]:.0f}× that',
        f'Payment size per category in the week of {week_label(lw)}: bar = p10 to p90, dot = median. Denominator: {num(tk["all"]["payments"])} demand-cleaned payments; categories with under 20 payments are hidden.',
        'tickets', '/x402/data/market.json', {'week': lw}, csv=csvp + 'tickets.csv', metric='tickets', through=through))
    parts.append(chart_frame('facilitators', f'{top_clean[0].title()} settles {pct(top_clean[1][1] / K)} of demand-cleaned dollars; {top_raw[0]} carries {pct(top_raw[1][0] / R)} of raw but {pct(top_raw[1][1] / K, 1)} of clean' if top_raw[0] != top_clean[0] else f'{top_clean[0].title()} settles {pct(top_clean[1][1] / K)} of demand-cleaned dollars',
        f'Share of all settled USD (grey) vs demand-cleaned USD (gold) by {term("facilitator")}, week of {week_label(lw)}. Addresses grouped by facilitator name. Denominators: {usd(R)} raw, {usd(K)} clean.',
        'facilitators', '/x402/data/market.json', {'week': lw, 'metric': 'usd'}, chips('metric', [('usd', 'USD'), ('payments', 'Payments')], 'usd'), csv=csvp + 'facilitators.csv', metric='facilitators', through=through))
    below = (gm is None) or gm < 0.2
    parts.append(chart_frame('tripwire', f'Content + data: {usd(tw[-1]["content_plus_data_usd"])} this week, {signed_pct(g4)} over 4 weeks — {"below" if below else "above"} the reopen threshold',
        f'Demand-cleaned USD to content and data sellers per week vs the path of +20% a month from the first week. Log-linear trend over the last 5 weeks: {signed_pct(gm)} a month. The {term("tripwire")} needs +20%/month for 3 months running.',
        'tripwire', '/x402/data/market.json', csv=csvp + 'tripwire.csv', metric='tripwire', through=through,
        note='One data reseller was 64% of content + data in the week of 7 Sep; single-seller swings move this line more than market growth does.'))
    # movers
    def mrow(m):
        a = m['payee']
        return {'seller': seller_cell(a, names.get(a), page=a in pages), 'seller_s': names.get(a) or a, 'seller_t': names.get(a) or a, 'category': m['category'],
                'cat': cat_dot(m['category']) + esc(CAT_LABEL[m['category']].split(' (')[0]), 'cat_s': m['category'], 'cat_t': m['category'], 'kind': m['kind'],
                'usd_prev': m['usd_prev'], 'usd_now': m['usd_now'], 'usd_change': m['usd_change'], 'buyers_prev': m['buyers_prev'], 'buyers_now': m['buyers_now'], 'address': a}
    gain = sorted((m for m in mv if m['usd_change'] > 0), key=lambda m: -m['usd_change'])
    loss = sorted((m for m in mv if m['usd_change'] < 0), key=lambda m: m['usd_change'])
    cols = [{'k': 'seller', 'label': 'Seller', 't': 'html'}, {'k': 'cat', 'label': 'Category', 't': 'html'}, {'k': 'kind', 'label': 'Status'},
            {'k': 'usd_prev', 'label': 'Prev week', 't': 'usd', 'r': 1}, {'k': 'usd_now', 'label': 'This week', 't': 'usd', 'r': 1},
            {'k': 'usd_change', 'label': 'Change', 't': 'usd', 'r': 1}, {'k': 'buyers_now', 'label': 'Buyers', 't': 'int', 'r': 1}]
    parts.append(f'<h2 id="movers">Movers</h2><p>{len(entered)} sellers crossed {M["min_buyers"]} genuine buyers in the week of {week_label(lw)} and {len(exited)} dropped below it. '
                 f'Biggest gain: {esc(names.get(gain[0]["payee"]) or gain[0]["payee"][:10] + "…")} ({usd(gain[0]["usd_change"])}); biggest loss: {esc(names.get(loss[0]["payee"]) or loss[0]["payee"][:10] + "…")} ({usd(loss[0]["usd_change"])}). '
                 f'Only sellers with at least {M["min_buyers"]} genuine buyers in either week are listed.</p>' if gain and loss else '<h2 id="movers">Movers</h2>')
    parts.append(data_table('movers-table', cols, [mrow(m) for m in mv], facets=[{'k': 'kind', 'labels': {'entered': 'Entered', 'exited': 'Exited', 'continuing': 'Continuing'}, 'order': ['entered', 'exited', 'continuing']}, {'k': 'category', 'dot': 1, 'order': CATS}],
                             sort='usd_change', page_size=15, placeholder='Filter sellers', csv_name='movers.csv', search=['seller_t', 'address', 'category']))
    parts.append(f'<p class="meta">Everything above is also free as JSON: <a href="/api/">API docs</a> · all CSVs in <a href="https://github.com/doescodinggiteasier/wknipe-site/tree/main/data">the public repo</a> (CC BY 4.0) · method: <a href="{METHOD}">X402_INDEX_METHOD.md</a>.</p>')
    write('market.md', md('\n'.join(parts)))


# ------------------------------------------------------------------ sellers leaderboard
def sellers_page(d):
    S = d.sellers; lw = S['latest_week']; ex = d.extra['sellers']
    rows = []
    for s in S['sellers']:
        if not s['qualifies_latest']: continue
        a, L = s['address'], s['latest']; e = (ex.get(a) or {}).get(lw) or {}
        prev = next((h for h in s['history'] if h['week'] < lw), None)
        hist = {h['week']: h['usd'] for h in s['history']}
        prev_usd = hist.get(S['weeks'][-2]) if len(S['weeks']) >= 2 else None
        rows.append({'rank': s['rank'], 'seller': seller_cell(a, s['label'], ', '.join(s['hosts'][:2]) or None), 'seller_s': (s['label'] or a).lower(), 'seller_t': s['label'] or a,
                     'address': a, 'hosts': ' '.join(s['hosts']), 'category': s['category'], 'cat': cat_dot(s['category']) + esc(CAT_LABEL[s['category']].split(' (')[0]), 'cat_s': s['category'], 'cat_t': s['category'],
                     'usd': L['usd'], 'wow': growth(prev_usd, L['usd']) if prev_usd else None, 'buyers': L['buyers'], 'payments': L['payments'],
                     'repeat': e.get('repeat_buyer_rate'), 'top': e.get('top_buyer_share'),
                     'posted': (s['posted_usd'] or {}).get('median'), 'paid': L['median_paid'], 'first': s['first_seen_week'],
                     'spark': spark_svg([hist.get(w, 0) for w in S['weeks']], w=72, h=22, label='clean USD by week'), 'spark_s': L['usd'], 'spark_t': ''})
    n = len(rows); tot = sum(r['usd'] for r in rows)
    named = sum(1 for s in S['sellers'] if s['qualifies_latest'] and s['label'])
    hi_top = sum(1 for r in rows if (r['top'] or 0) >= 0.5)
    rep = [r['repeat'] for r in rows if r['repeat'] is not None]
    cols = [{'k': 'rank', 'label': '#', 't': 'int', 'r': 1}, {'k': 'seller', 'label': 'Seller', 't': 'html'}, {'k': 'cat', 'label': 'Category', 't': 'html'},
            {'k': 'usd', 'label': 'Clean USD', 't': 'usd', 'r': 1}, {'k': 'wow', 'label': 'WoW', 't': 'pct', 'r': 1}, {'k': 'spark', 'label': 'Trend', 't': 'html'},
            {'k': 'buyers', 'label': 'Buyers', 't': 'int', 'r': 1}, {'k': 'repeat', 'label': 'Repeat buyers', 't': 'pct', 'r': 1},
            {'k': 'top', 'label': 'Top-buyer share', 't': 'pct', 'r': 1}, {'k': 'posted', 'label': 'Posted', 't': 'price', 'r': 1}, {'k': 'paid', 'label': 'Paid median', 't': 'price', 'r': 1},
            {'k': 'first', 'label': 'First seen'}]
    cards = [stat_card('Sellers with 5+ genuine buyers', num(n), tip=f'Sellers paid by at least {S["min_buyers"]} distinct genuine buyers in the week of {week_label(lw)}.'),
             stat_card('Their demand-cleaned USD', usd(tot), tip='Sum of the listed sellers\' demand-cleaned USD for the week.'),
             stat_card('Median repeat-buyer rate', pct(statistics.median(rep)) if rep else '–', tip=GLOSSARY['repeat-buyer rate'][1]),
             stat_card('Depend on one buyer for half+', f'{hi_top} of {n}', tip=GLOSSARY['top-buyer share'][1]),
             stat_card('Named in a listing', f'{named} of {n}', tip='Names are what the seller wrote in its Bazaar listing. We never infer who owns an address.')]
    out = [decide('who actually gets paid by genuine buyers, whether those buyers come back, and how dependent each seller is on its single largest buyer.'),
           freshness(d.through), kpis(cards),
           data_table('sellers-table', cols, rows, facets=[{'k': 'category', 'dot': 1, 'order': CATS}], sort='usd', page_size=50,
                      placeholder='Search name, host or address', csv_name=f'x402_sellers_{lw}.csv', search=['seller_t', 'address', 'hosts', 'category']),
           f'<p class="meta">{term("repeat-buyer rate", "Repeat buyers")}: share of its buyers who paid it twice or more in the week. {term("top-buyer share", "Top-buyer share")}: share of its clean USD from the single largest buyer — a concentration risk, stated neutrally. '
           f'Posted = median listed price per call; paid = median clean payment. Names are self-declared; we never speculate on ownership. Data: <a href="/x402/data/sellers.json">sellers.json</a> · <a href="/x402/data/sellers_latest.csv">CSV</a> · <a href="/api/">API</a>.</p>']
    write('sellers.md', md('\n'.join(out)))


# ------------------------------------------------------------------ buyers
def buyers_page(d):
    M, lw = d.market, d.latest
    bw = M['buyers_weekly']; b = bw[-1]
    tiers = [t for t in M['buyer_tiers'] if t['week_start'] == lw]
    nb = sum(t['buyers'] for t in tiers); nu = sum(t['usd'] for t in tiers)
    whale = [t for t in tiers if t['tier'] in ('$100–$1k', '$1k and up')]
    wb = sum(t['buyers'] for t in whale); wu = sum(t['usd'] for t in whale)
    small = next(t for t in tiers if t['tier'] == 'under $0.10')
    ret = M['retention']
    series = [int(r['active_buyers']) for r in bw]
    cards = [stat_card('Genuine buyers', num(b['active_buyers']), series, growth(series[-2], series[-1]) if len(series) > 1 else None, tip=GLOSSARY['genuine buyers'][1], weeks=d.weeks),
             stat_card('New this week', num(b['new_buyers']), foot=f'{pct(int(b["new_buyers"]) / int(b["active_buyers"]))} of active', tip='Wallets never seen in any earlier week of the index (history starts ' + week_label(d.weeks[0], True) + ').'),
             stat_card('Median weekly spend', usd(float(b['median_spend_usd']), True), tip='Half of genuine buyers spent less than this in the week (demand-cleaned USD).'),
             stat_card('Pay 2+ sellers', pct(b['multi_homing_share'], 1), tip=GLOSSARY['multi-homing'][1]),
             stat_card(f'Buyers spending $100+', num(wb), foot=f'{pct(wb / nb, 1)} of buyers, {pct(wu / nu)} of USD', tip='Buyer wallets whose demand-cleaned spend in the week was $100 or more.')]
    # retention heatmap (static HTML)
    head = '<tr><th>New in week of</th><th class="r">New buyers</th>' + ''.join(f'<th class="r">+{k} wk</th>' for k in range(1, 5)) + '</tr>'
    body = ''
    for r in ret:
        cells = ''
        for k in range(1, 5):
            v = r[f'week_{k}']
            if v in ('', None): cells += '<td class="r meta">–</td>'
            else:
                v = float(v); cells += f'<td class="r" style="background:color-mix(in srgb, var(--series-primary) {v * 90:.0f}%, transparent);color:{"var(--surface)" if v > 0.45 else "var(--ink)"}">{pct(v)}</td>'
        body += f'<tr><td>{week_label(r["cohort_week"], True)}</td><td class="r">{num(r["new_buyers"])}</td>{cells}</tr>'
    rt = f'<div class="seller-table"><table class="table">{head}{body}</table></div>'
    w1 = [float(r['week_1']) for r in ret if r['week_1'] not in ('', None)]
    tier_rows = []
    for t in tiers:
        cats = sorted(((c, t.get(f'usd_{c}', 0)) for c in CATS), key=lambda x: -float(x[1] or 0))
        topc = ', '.join(f'{CAT_LABEL[c].split(" (")[0]} {pct(float(v) / t["usd"])}' for c, v in cats[:3] if t['usd'] and float(v) > 0)
        tier_rows.append({'tier': t['tier'], 'buyers': t['buyers'], 'bshare': t['buyers'] / nb if nb else None, 'usd': t['usd'], 'ushare': t['usd'] / nu if nu else None,
                          'payments': t['payments'], 'per': t['usd'] / t['buyers'] if t['buyers'] else None, 'cats': esc(topc), 'cats_t': topc})
    tcols = [{'k': 'tier', 'label': 'Weekly spend'}, {'k': 'buyers', 'label': 'Buyers', 't': 'int', 'r': 1}, {'k': 'bshare', 'label': 'Share of buyers', 't': 'pct', 'r': 1},
             {'k': 'usd', 'label': 'USD', 't': 'usd', 'r': 1}, {'k': 'ushare', 'label': 'Share of USD', 't': 'pct', 'r': 1}, {'k': 'payments', 'label': 'Payments', 't': 'int', 'r': 1},
             {'k': 'cats', 'label': 'What they buy (share of tier USD)', 't': 'html'}]
    csvp = '/x402/data/'
    out = [decide('how big the paying customer base really is, whether buyers stick, and whether spend comes from many small agents or a few large wallets.'),
           freshness(d.through), kpis(cards),
           chart_frame('buyers', f'{num(b["active_buyers"])} genuine buyers in the week of {week_label(lw)}: {num(b["returning_buyers"])} returning, {num(b["new_buyers"])} new',
                       'Distinct payer wallets with at least one demand-cleaned payment, by whether they also paid the previous week. The first week of history cannot tell new from returning.',
                       'buyers', '/x402/data/market.json', csv=csvp + 'buyers_weekly.csv', metric='buyers_weekly', through=d.through),
           chart_frame('retention', f'A median {pct(statistics.median(w1)) if w1 else "–"} of each week\'s new buyers buy again the next week',
                       'Share of each week\'s new genuine buyers who make a demand-cleaned payment 1, 2, 3 and 4 weeks later. Denominator: the cohort size (second column). Cohorts start the second week of history.',
                       body=rt, csv=csvp + 'retention.csv', metric='retention', through=d.through),
           chart_frame('tiers', f'{pct(small["buyers"] / nb)} of buyers spend under $0.10 a week; the {num(wb)} spending $100+ bring {pct(wu / nu)} of the money',
                       f'Genuine buyers in the week of {week_label(lw)} grouped by their demand-cleaned spend. Denominators: {num(nb)} buyers, {usd(nu)}.',
                       body=data_table('tiers-table', tcols, tier_rows, page_size=10, csv_name='buyer_tiers.csv'), csv=csvp + 'buyer_tiers.csv', metric='buyer_tiers', through=d.through, table=False),
           '<div class="grid2">' + chart_frame('spend', f'The median buyer spent {usd(float(b["median_spend_usd"]), True)}', f'Buyers by weekly demand-cleaned spend (log bins). Denominator: {num(nb)} buyers.',
                       'hist', '/x402/data/market.json', {'week': lw, 'src': 'buyer_spend_histogram', 'y': 'buyers', 'xlabel': 'USD spent in the week (log bins)'}, csv=csvp + 'buyer_spend_histogram.csv', metric='buyer_spend_histogram', through=d.through)
           + chart_frame('multihoming', f'{pct(b["multi_homing_share"], 1)} of buyers pay two or more sellers', f'Buyers by distinct sellers paid in the week. Denominator: {num(nb)} buyers.',
                       'spb', '/x402/data/market.json', {'week': lw}, csv=csvp + 'sellers_per_buyer.csv', metric='sellers_per_buyer', through=d.through) + '</div>',
           '<div class="callout callout-note" style="padding:12px 16px"><b>Privacy.</b> This page shows aggregates only; no buyer address is listed anywhere on the site. '
           'Buyer wallets are public on-chain, but one person or company can run many wallets and one wallet can serve many users, so "buyers" counts wallets, not customers.</div>']
    write('buyers.md', md('\n'.join(out)))


# ------------------------------------------------------------------ prices
def prices_page(d):
    P, M = d.prices, d.market
    pvp = {r['category']: r for r in P['posted_vs_paid']}; pbc = {r['category']: r for r in P['posted_by_category']}
    a = pvp['all']
    L = rjson(D('x402_prices', 'listings.json'))
    sellers = L['sellers'] if L else []
    s_any = sum(1 for s in sellers if s[1] >= 1); s5 = sum(1 for s in sellers if s[1] >= 5)
    lowest = min((r for c, r in pvp.items() if c != 'all' and r['ratio']), key=lambda r: r['ratio'])
    changes = rcsv(D('bazaar_daily', 'price_changes.csv'))
    cards = [stat_card('Bazaar listings', num(P['listings']), tip=f'Paid API listings in the Coinbase CDP Bazaar snapshot {P["snapshot"]}, all networks.'),
             stat_card('Median posted price', usd(a['posted_median_usd'], True), foot=f'{num(a["listings"])} priced listings', tip=GLOSSARY['posted'][1]),
             stat_card('Median paid', usd(a['paid_median_usd'], True), foot=f'{num(a["payments"])} clean payments', tip=GLOSSARY['paid'][1]),
             stat_card('Listed sellers with 5+ buyers', f'{num(s5)} of {num(len(sellers))}', foot=f'{pct(s5 / len(sellers))} of sellers listed on Base', tip='Distinct Base payTo addresses in the Bazaar whose seller had at least 5 genuine buyers in the latest index week.')]
    # posted ranges chart re-uses the "tickets" renderer shape
    ranges = {'week_start': P['week'], 'latest_week': P['week'], 'tickets': [{'week_start': P['week'], 'category': r['category'], 'payments': r['priced'], 'p10_usd': r['p10_usd'], 'median_usd': r['median_usd'], 'p90_usd': r['p90_usd']} for r in P['posted_by_category'] if r['priced']]}
    json.dump(ranges, open(os.path.join(HERE, 'x402', 'data', 'posted_ranges.json'), 'w'))
    csvp = '/x402/data/'
    out = [decide('what to charge per call, whether posted prices are what buyers actually pay, and which kinds of listings attract genuine buyers at all.'),
           freshness(d.through, f'listings snapshot {P["snapshot"]} · updates daily'), kpis(cards),
           f'<p><a class="wk-btn" href="/x402/prices/comps">Open Price comps →</a> <span class="meta">&nbsp;Describe your API and see comparable listings, their price range, and whether they get buyers.</span></p>',
           chart_frame('posted-vs-paid', f'Buyers pay less than listings ask: the median clean payment is {a["ratio"]:.1f}× the median posted price; {CAT_LABEL[lowest["category"]].lower()} is lowest at {lowest["ratio"]:.1f}×',
                       f'Median posted price per listing (Bazaar {P["snapshot"]}) vs median demand-cleaned payment (week of {week_label(P["week"])}), by category. Posted weights each listing equally; paid weights each payment, so cheap high-volume calls pull it down. {term("posted vs paid", "Posted vs paid")}.',
                       'postedPaid', '/x402/data/prices.json', csv=csvp + 'posted_vs_paid.csv', metric='posted_vs_paid', through=d.through,
                       note='Listing categories come from each listing\'s own text; paid categories from the seller\'s. They use the same five definitions.'),
           chart_frame('posted-ranges', f'Half of priced listings ask {usd(pbc["all"]["median_usd"], True)} or less per call; the top tenth ask {usd(pbc["all"]["p90_usd"], True)}+',
                       f'Posted price per call by listing category: bar = p10 to p90, dot = median. Denominator: {num(pbc["all"]["priced"])} listings with a single exact USDC price (Base, else Solana).',
                       'tickets', '/x402/data/posted_ranges.json', csv=csvp + 'posted_by_category.csv', metric='posted_by_category', through=P['snapshot']),
           chart_frame('index', 'Price per call, chain-linked (first week = 100)', 'Posted: Bazaar listings present in consecutive snapshots. Paid: each demand-cleaned seller\'s median payment, sellers present in consecutive weeks. Geometric mean of changes (' + term('jevons', 'Jevons') + ').',
                       'jevons', '/x402/data/prices.json', {'cat': 'all'}, chips('cat', [('all', 'All')] + [(c, CAT_LABEL[c].split(' (')[0]) for c in CATS[:5]], 'all'), csv='/x402/data/prices_weekly.csv', metric='prices_weekly', through=d.through,
                       note='Posted-price history starts 2026-09-21 (the Bazaar has no history API); the paid index is backfilled from chain data.')]
    if changes:
        cols = [{'k': 'date', 'label': 'Date'}, {'k': 'host', 'label': 'Host'}, {'k': 'what', 'label': 'What it does'}, {'k': 'old_usd', 'label': 'Was', 't': 'price', 'r': 1}, {'k': 'new_usd', 'label': 'Now', 't': 'price', 'r': 1}, {'k': 'change', 'label': 'Change', 't': 'pct', 'r': 1}]
        rows = [{**r, 'old_usd': f(r['old_usd']), 'new_usd': f(r['new_usd']), 'change': f(r['change'])} for r in changes][-500:]
        up = sum(1 for r in rows if (r['change'] or 0) > 0); dn = sum(1 for r in rows if (r['change'] or 0) < 0)
        out.append(f'<h2 id="price-changes">Price changes</h2><p>{num(len(rows))} listings changed their posted price since daily snapshots began ({up} up, {dn} down). From the daily Bazaar diff. <a href="/x402/prices/changes.xml">RSS feed of price changes</a>.</p>'
                   + data_table('changes-table', cols, rows, sort='date', page_size=15, csv_name='price_changes.csv'))
    else:
        out.append('<h2 id="price-changes">Price changes</h2><p class="meta">Daily Bazaar snapshots started on 2026-09-30; the first price changes appear after the second daily snapshot.</p>')
    write('prices.md', md('\n'.join(out)))


def comps_page(d):
    P = d.prices
    opts = ''.join(f'<option value="{c}">{CAT_LABEL[c]}</option>' for c in CATS[:5])
    ui = f'''{decide('what to charge for a new API: what comparable listings ask, and whether comparable sellers actually get genuine buyers at that price.')}
{freshness(d.through, f"listings snapshot {P['snapshot']} · buyers week of {week_label(P['week'])}")}
<form id="comps-form" class="card-wk" role="search" style="display:grid;gap:10px;margin-bottom:20px" onsubmit="return false">
<label for="comps-q" style="font-weight:600">Describe what one paid call returns</label>
<input id="comps-q" type="search" placeholder='e.g. "token price lookup", "scrape a web page to markdown", "news article"' autocomplete="off">
<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><label for="comps-cat" class="meta">Category</label><select id="comps-cat" class="wk-select"><option value="">Any</option>{opts}</select>
<span class="meta" id="comps-status">Loading {num(P['listings'])} listings…</span></div>
<div class="ctrl" id="comps-examples"></div></form>
<div id="comps-out" hidden>
<div class="kpis" id="comps-kpis"></div>
<figure class="chart-frame" id="comps-dist"><h2 class="t" id="comps-title"></h2><p class="s" id="comps-sub"></p><div class="plot"></div>
<figcaption class="foot"><button type="button" id="comps-csv">Download CSV</button> · <button type="button" data-act="link">Permalink</button><span class="note">Comparables = the 60 best text matches, at most 3 per seller. Buyers = distinct genuine buyers of the listing's seller (all its endpoints) in the week of {week_label(P['week'])}; realised price = that seller's median clean payment.</span></figcaption></figure>
<div id="comps-table"></div></div>
<p class="meta">Posted prices are public in the Coinbase CDP Bazaar; buyer counts and realised prices are public on-chain aggregates per seller from the <a href="/x402/">Clean Index</a>. This tool is a public, lite version of a seller price benchmark: it never shows non-public data. <a href="/x402/data/listings_latest.csv.gz">All listings (CSV.gz)</a>.</p>
<script defer src="/assets/comps.js?v={int(dt.datetime.now().timestamp())}"></script>'''
    write('comps.md', md(ui))


# ------------------------------------------------------------------ API
def api_page(d):
    data = rjson(os.path.join(ROOT, 'apps', 'x402-index-api', 'src', 'data.json'), {})
    mets = data.get('metrics') or {}
    rows = ''.join(f'<tr><td><code>{esc(k)}</code></td><td>{esc(v["about"])}</td><td class="r">{num(len(v["rows"]))}</td><td><a href="{API}/v1/series?metric={esc(k)}">JSON</a></td></tr>' for k, v in mets.items())
    out = f'''{decide('whether to pull this data into your own dashboards, models or agents. Every chart on this site has a free JSON series and a CSV.')}
<h2>Free: every chart series</h2>
<p>One call per metric, no key, CORS open, cached for an hour, CC BY 4.0 (cite wknipe.com). Optional filters: <code>&amp;week=YYYY-MM-DD</code>, <code>&amp;category=data</code>.</p>
<pre><code>curl -s "{API}/v1/metrics"                       # list every metric
curl -s "{API}/v1/series?metric=waterfall&amp;week={d.latest}"
curl -s "{API}/v1/series?metric=concentration&amp;category=data"
curl -s "{API}/v1/latest"                        # headline numbers for the latest week
curl -s "{API}/v1/check?domain=theguardian.com"  # AI-policy check (rate-limited, cached 24 h)
curl -s "{API}/v1/probe?url=https://api.wknipe.com/v1/sellers"  # unpaid x402 endpoint check (cached 10 min)
curl -s "{API}/v1/badge/policy?domain=theguardian.com"          # AI-policy badge (SVG)</code></pre>
<div class="seller-table"><table class="table"><thead><tr><th>metric</th><th>What it is</th><th class="r">Rows</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Paid over x402: full series and sellers</h2>
<p>Two endpoints cost <b>$0.001 per call</b> in USDC on Base, paid with the x402 protocol (any x402 client or agent wallet). Our own payments are excluded from the index.</p>
<pre><code>GET {API}/v1/series?stage=clean&amp;category=all   # stage x category weekly series + price index
GET {API}/v1/sellers?category=data&amp;n=50         # top demand-cleaned sellers, latest week
# without payment both return HTTP 402 with the payment requirements:
curl -si "{API}/v1/sellers?n=5" | grep -i payment-required</code></pre>
<h2>MCP server</h2>
<p>An MCP server exposes the index to AI assistants (tools: latest numbers, series, sellers, method). Source and setup: <a href="https://github.com/doescodinggiteasier/wknipe-site/tree/main/apps/x402-index-mcp">apps/x402-index-mcp</a>.</p>
<h2>Bulk data</h2>
<p>All CSVs live in the public repo under <a href="https://github.com/doescodinggiteasier/wknipe-site/tree/main/data">data/</a> and update every Monday. Chart CSVs are also linked under each chart. Code MIT, data CC BY 4.0.</p>'''
    write('api.md', md(out))


# ------------------------------------------------------------------ /design/
def design_page(d):
    src = open(os.path.join(HERE, 'theme-base.scss')).read()
    pal = {}
    for mode in ('light', 'dark'):
        m = re.search(mode + r':\s*\((.*?)\n\s*\)', src, re.S)
        pal[mode] = dict(re.findall(r'([\w-]+):\s*(#[0-9A-Fa-f]{6})', re.sub(r'//[^\n]*', '', m.group(1))))
    try:
        ct = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'site', 'contrast_check.py'), '--md'], capture_output=True, text=True)
        contrast = ct.stdout
    except Exception as e:
        contrast = str(e)
    rows = [l for l in contrast.splitlines() if l.startswith('| ') and not l.startswith('| Mode') and not l.startswith('|---')]
    ctab = '<div class="seller-table"><table class="table"><thead><tr><th>Mode</th><th>Foreground</th><th>Background</th><th class="r">Ratio</th><th class="r">Needs</th><th>Result</th><th>Use</th></tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td{" class=r" if i in (3, 4) else ""}>{esc(c.strip()).replace("`", "")}</td>' for i, c in enumerate(l.strip('|').split('|'))) + '</tr>' for l in rows) + '</tbody></table></div>'
    summary = contrast.strip().splitlines()[-1] if contrast.strip() else ''

    def sw(mode):
        return '<div class="swatch-row">' + ''.join(f'<div class="swatch"><div class="c" style="background:{v}"></div><div class="l">{k}<span>{v}</span></div></div>' for k, v in pal[mode].items()) + '</div>'
    lw = d.latest; W = d.weeks
    clean = d.series('clean', 'all')
    sample_card = stat_card('Demand-cleaned $ / week', usd(clean[-1]), clean, growth(clean[-2], clean[-1]), tip='Example tooltip: a definition plus a link. <a href="/x402/#waterfall">Method →</a>', weeks=W, higher_is='good')
    sample_card2 = stat_card('Share that survives cleaning', '55%', [0.6, 0.58, 0.5, 0.52, 0.55], -0.04, tip='Negative delta, coloured because higher_is=good.', higher_is='good')

    def panel(mode):
        return f'''<div class="wk-{mode}"><p class="eyebrow">{mode} mode</p>
<h3 style="margin-top:0">Type: Inter 650 / 400, JetBrains Mono for data labels</h3>
<p style="font:650 34px/1.15 Inter;letter-spacing:-.025em;margin:0">Headline 34</p><p style="font:650 22px/1.3 Inter;margin:6px 0">Section 22</p><p style="margin:0">Body 16 with a <a href="#">purple link</a> and a {term("clean", "glossary term")}.</p>
<p class="meta">Mono 12–13 · tabular figures 1,234,567.89</p>
<div class="kpis" style="grid-template-columns:1fr 1fr">{sample_card}{sample_card2}</div>
<p>{freshness(d.through)}</p>
<p><a class="wk-btn" href="#">Primary</a> <a class="wk-btn ghost" href="#">Secondary</a> <button class="chip" aria-pressed="true">Selected</button> <button class="chip" aria-pressed="false">Chip</button> <span class="pill gold">gold pill</span> <span class="pill ok">OK 402</span> <span class="pill bad">No 402</span></p>
<div class="legend">{''.join(f'<span><i style="background:var(--c-{c})"></i>{CAT_LABEL[c].split(" (")[0]}</span>' for c in CATS)}</div>
{chart_frame(f'design-waterfall-{mode}', 'Chart frame: the title states the finding', 'Subtitle gives the denominator and source. Footer: CSV · API · Cite · Permalink · Table.', 'waterfall', '/x402/data/market.json', {'week': lw}, csv='/x402/data/waterfall.csv', metric='waterfall', page='/design/')}
{chart_frame(f'design-mix-{mode}', 'Categorical colours are fixed per category site-wide', 'Stacked area, demand-cleaned USD.', 'mix', '/x402/data/market.json', {'metric': 'usd'}, page='/design/')}
<div class="tool-grid" style="grid-template-columns:1fr">{tool_card('Tool', 'Tool card', 'Every tool and dataset on the home page uses this card.', '#')}</div>
{sw(mode)}</div>'''
    table_demo = data_table('design-table', [{'k': 'name', 'label': 'Name'}, {'k': 'category', 'label': 'Category'}, {'k': 'usd', 'label': 'USD', 't': 'usd', 'r': 1}, {'k': 'share', 'label': 'Share', 't': 'pct', 'r': 1}],
                            [{'name': f'Example seller {i}', 'category': CATS[i % 5], 'usd': 1000 / (i + 1), 'share': 1 / (i + 2)} for i in range(40)],
                            facets=[{'k': 'category', 'dot': 1, 'order': CATS}], sort='usd', page_size=8, placeholder='Filter the demo table')
    ia = '''<ul><li><b>Data</b>: Market (/x402/) · Sellers (/x402/sellers/) · Buyers (/x402/buyers/) · Prices (/x402/prices/) · State of AI access (/access/) · This week (/weekly/)</li>
<li><b>Tools</b>: Price comps (/x402/prices/comps) · Endpoint status (/x402/status/) · AI-policy checker (/check/) · Agent benchmark (/agents/) · API (/api/) · Badges (/badges/)</li>
<li><b>Writing</b> (/writing/) · <b>About</b> (/about) · ⌘K search everywhere</li></ul>'''
    out = f'''<p class="lede">The wknipe.com design system: purple for action, gold for emphasis, one palette file. Both modes are shown side by side; the page itself follows your system setting.</p>
<p class="meta">Tokens live in <code>site/theme-base.scss</code> (<code>$wk-palette</code>): a shade change is one edit. Charts read the same tokens at render time. This page is not linked from the navigation and is marked noindex.</p>
<h2>Palette, type and components</h2><div class="design-panels">{panel("light")}{panel("dark")}</div>
<h2>Data table</h2><p>Sticky header, click-to-sort, text filter, facet chips, pagination, CSV export; collapses to cards under 640px.</p>{table_demo}
<h2>Chart palette</h2><p>Categories keep one colour on every page. Validated with the dataviz palette validator (light surface #FFFFFF and dark surface #1D1928): lightness band, chroma floor, colour-blind separation ΔE ≥ 20 (target 8), normal-vision ΔE ≥ 20, every slot ≥ 3:1 on its surface. Unclassed uses a neutral grey on purpose (it has no identity) and is always labelled. Gold as a chart colour is darkened to #B08A12 in light mode so the "clean" series passes 3:1; brand gold #C9A227 is kept for rules and underlines, where it is decorative.</p>
<h2>WCAG contrast</h2><p>{esc(summary)}. Command: <code>python3 scripts/site/contrast_check.py</code> (exit 1 on any failing pair).</p>{ctab}
<h2>Information architecture</h2>{ia}'''
    write('design.md', md(out))


def build():
    d = Data()
    if not d.market or not d.weeks:
        print('market data missing: run scripts/x402_market/build.py'); return 'skipped'
    copy_data(d)
    build_assets(d)
    home(d); market(d); sellers_page(d); buyers_page(d)
    if d.prices: prices_page(d); comps_page(d)
    api_page(d); design_page(d)
    try:
        import _pages4
        _pages4.build(d)
    except ImportError:
        pass
    import _pages5
    _pages5.build(d)
    return 'ok'


if __name__ == '__main__':
    print(build())
