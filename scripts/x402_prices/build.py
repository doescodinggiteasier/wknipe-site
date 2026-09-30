#!/usr/bin/env python3
"""ORDER_013 Phase 3: posted prices, posted-vs-paid and the Price comps data (wknipe.com/x402/prices/).

Reads the latest CDP Bazaar snapshot, the listing classes (classify_listings.py cache), the index's cleaned sellers
(data/x402_index/payees_weekly.csv) and the market stats (data/x402_market/market.json). A listing's posted price is
its exact-scheme USDC amount on Base (else on Solana); "upto" and other schemes have no single price and are kept
unpriced. Buyer evidence joins the listing's Base payTo to the index's demand-cleaned sellers for the latest week.
Posted prices are already public; this file adds only public on-chain aggregates (buyers and median paid per seller).

Writes data/x402_prices/{listings.json, listings_latest.csv.gz, prices.json, posted_vs_paid.csv, posted_by_category.csv}.
No network, no keys. Usage: python3 scripts/x402_prices/build.py
"""
import collections, csv, datetime as dt, gzip, json, os, statistics, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
sys.path.insert(0, HERE)
import common  # noqa: E402
from classify_listings import latest_snapshot, listing_text, key, load_cache  # noqa: E402

OUT = os.path.join(common.ROOT, 'data', 'x402_prices')
SOL_USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
MIN_BUYERS = 5
CATS5 = ['content', 'data', 'search', 'compute', 'other']


def pct(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q; f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 6)


def offer(it):
    """(price_usd, network, scheme, base_payTo, method) for one listing."""
    base = sol = None; schemes = set(); nets = set(); payto = None
    for a in it.get('accepts') or []:
        n = a.get('network') or ''; nets.add('base' if n in common.BASE_NETS else 'solana' if 'solana' in n else n.split(':')[0] or '?')
        schemes.add(a.get('scheme') or '?')
        if n in common.BASE_NETS and a.get('payTo') and not payto: payto = a['payTo'].lower()
        p = common.base_usdc_price(a)
        if p is not None and base is None: base = p
        if 'solana' in n and a.get('asset') == SOL_USDC and a.get('scheme') == 'exact' and sol is None:
            try: sol = int(a.get('amount', a.get('maxAmountRequired'))) / 1e6
            except (TypeError, ValueError): pass
    info = ((it.get('extensions') or {}).get('bazaar') or {}).get('info') or {}
    method = ((info.get('input') or {}).get('method') or '').upper() or None
    price, net = (base, 'base') if base is not None else (sol, 'solana') if sol is not None else (None, None)
    return price, net, sorted(nets), sorted(schemes), payto, method


def main():
    os.makedirs(OUT, exist_ok=True)
    snap, items = latest_snapshot()
    cls = load_cache()
    pw = list(csv.DictReader(open(os.path.join(common.OUT, 'payees_weekly.csv'))))
    latest = max(r['week_start'] for r in pw)
    sel = {r['payee']: r for r in pw if r['week_start'] == latest}
    pages = set()
    sj = os.path.join(common.ROOT, 'data', 'x402_sellers', 'sellers.json')
    if os.path.exists(sj): pages = {s['address'] for s in json.load(open(sj))['sellers']}
    rows = []
    for it in items:
        c = cls.get(key(listing_text(it))) or {}
        price, net, nets, schemes, payto, method = offer(it)
        bz = (it.get('extensions') or {}).get('bazaar') or {}
        u = urllib.parse.urlparse(it.get('resource', ''))
        s = sel.get(payto) if payto else None
        rows.append({'host': u.hostname or '', 'path': (u.path or '/')[:80], 'name': (it.get('serviceName') or (bz.get('info') or {}).get('name') or '')[:80],
                     'what': c.get('what'), 'category': c.get('category') or 'unclassified', 'desc': ' '.join((it.get('description') or (bz.get('info') or {}).get('description') or '').split())[:140],
                     'price_usd': price, 'price_network': net, 'networks': nets, 'schemes': schemes, 'method': method, 'pay_to': payto,
                     'buyers_last_week': int(s['payers']) if s else 0, 'paid_median_usd': float(s['median_payment_usd']) if s else None,
                     'seller_clean_usd': float(s['usd']) if s else 0.0, 'seller_page': payto in pages, 'resource': it.get('resource', '')})
    # compact array form for the browser (column list + rows); payTo deduplicated into a seller table
    sellers = sorted({r['pay_to'] for r in rows if r['pay_to']})
    sidx = {q: i for i, q in enumerate(sellers)}
    cols = ['host', 'path', 'name', 'what', 'category', 'desc', 'price_usd', 'price_network', 'method', 'seller']
    comp = {'snapshot': snap, 'week': latest, 'min_buyers': MIN_BUYERS, 'cols': cols,
            'sellers': [[q, int(sel[q]['payers']) if q in sel else 0, float(sel[q]['median_payment_usd']) if q in sel else None, q in pages] for q in sellers],
            'rows': [[r['host'], r['path'], r['name'], r['what'], r['category'], r['desc'], r['price_usd'], r['price_network'], r['method'], sidx.get(r['pay_to'])] for r in rows]}
    json.dump(comp, open(os.path.join(OUT, 'listings.json'), 'w'), separators=(',', ':'))
    import io
    with gzip.GzipFile(os.path.join(OUT, 'listings_latest.csv.gz'), 'wb', mtime=0) as gz, io.TextIOWrapper(gz, newline='') as f:  # mtime=0: byte-identical rebuilds
        w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k not in ('networks', 'schemes')] + ['networks', 'schemes'])
        w.writeheader()
        for r in rows: w.writerow({**r, 'networks': ' '.join(r['networks']), 'schemes': ' '.join(r['schemes'])})

    # posted distribution per listing category; posted vs paid per category
    priced = [r for r in rows if r['price_usd'] is not None and r['price_usd'] > 0]
    post = []
    for c in CATS5 + ['all']:
        ps = [r['price_usd'] for r in priced if c == 'all' or r['category'] == c]
        withb = [r for r in rows if (c == 'all' or r['category'] == c)]
        post.append({'category': c, 'listings': len(withb), 'priced': len(ps), 'p10_usd': pct(ps, .1), 'median_usd': pct(ps, .5), 'p90_usd': pct(ps, .9),
                     'share_seller_any_buyer': round(sum(1 for r in withb if r['buyers_last_week'] >= 1) / len(withb), 4) if withb else None,
                     'share_seller_5_buyers': round(sum(1 for r in withb if r['buyers_last_week'] >= MIN_BUYERS) / len(withb), 4) if withb else None})
    market = json.load(open(os.path.join(common.ROOT, 'data', 'x402_market', 'market.json')))
    tk = {r['category']: r for r in market['tickets'] if r['week_start'] == latest}
    pvp = []
    for p in post:
        t = tk.get(p['category'])
        pvp.append({'category': p['category'], 'listings': p['priced'], 'posted_median_usd': p['median_usd'],
                    'payments': t['payments'] if t else 0, 'paid_median_usd': t['median_usd'] if t else None,
                    'ratio': round(t['median_usd'] / p['median_usd'], 3) if t and p['median_usd'] else None})
    for name, rs in (('posted_by_category.csv', post), ('posted_vs_paid.csv', pvp)):
        with open(os.path.join(OUT, name), 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rs[0])); w.writeheader(); w.writerows(rs)
    prices_weekly = list(csv.DictReader(open(os.path.join(common.OUT, 'prices_weekly.csv'))))
    doc = {'snapshot': snap, 'week': latest, 'listings': len(rows), 'priced': len(priced),
           'distinct_sellers_base': len(sellers), 'networks': dict(collections.Counter(n for r in rows for n in r['networks'])),
           'schemes': dict(collections.Counter(s for r in rows for s in r['schemes'])),
           'categories': dict(collections.Counter(r['category'] for r in rows)), 'posted_by_category': post, 'posted_vs_paid': pvp,
           'prices_weekly': prices_weekly, 'price_hist': [{'category': c, 'bin_lo_usd': lo, 'n': n} for c, lo, n in hist(priced)]}
    json.dump(doc, open(os.path.join(OUT, 'prices.json'), 'w'), default=str)
    print(json.dumps({k: v for k, v in doc.items() if k not in ('prices_weekly', 'price_hist')}, indent=1, default=str))


def hist(priced):
    import math
    out = collections.Counter()
    for r in priced:
        k = math.floor(math.log10(r['price_usd']) * 2) / 2
        out[(r['category'], round(10 ** k, 6))] += 1
    return sorted((c, lo, n) for (c, lo), n in out.items())


if __name__ == '__main__':
    main()
