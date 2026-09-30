#!/usr/bin/env python3
"""ORDER_012 Build 2: x402 seller leaderboard data (wknipe.com/x402/sellers/).

A seller qualifies in a week when at least MIN_BUYERS distinct buyers paid it after the Clean Index filters (manufacture,
fan-out, dust). The leaderboard shows the latest week's qualifiers; every seller that ever qualified keeps a page.
Per seller: category (the index's), how it is listed in the CDP Bazaar (name as the seller wrote it, hosts, posted
per-call prices on Base USDC), clean payments / USD / buyers / median paid per week, and the first week it appears in the
cleaned index. Names are self-declared listing text: we never infer who owns an address.

Reads data/x402_index/payees_weekly.csv, payee_classes.csv and the Bazaar snapshots (common.bazaar_snapshots()).
Writes data/x402_sellers/{sellers.json, sellers_latest.csv}. No network, no keys.
Usage: python3 scripts/sellers/build.py [--min-buyers 5]
"""
import argparse, collections, csv, datetime as dt, json, os, statistics, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
import common  # noqa: E402

OUT = os.path.join(common.ROOT, 'data', 'x402_sellers')
MIN_BUYERS = 5


def listings():
    """payTo -> {names, hosts, prices, resources, snapshot} from the latest Bazaar snapshot that lists it."""
    out = {}
    merged = common.first(os.path.join(common.STATE, 'listings_merged_2026-09-28.json.gz'),
                          os.path.join(common.STATE, 'listings_merged_2026-09-28.json'))
    srcs = ([('x402scan+Bazaar pull 2026-09-28', merged)] if os.path.exists(merged) else []) + \
        [(f'CDP Bazaar listing {d}', p) for d, p in common.bazaar_snapshots()]
    for d, p in srcs:  # oldest first: later snapshots overwrite
        per = collections.defaultdict(lambda: {'names': collections.Counter(), 'hosts': collections.Counter(),
                                               'prices': [], 'resources': set()})
        for it in common.jload(p):
            bz = (it.get('extensions') or {}).get('bazaar') or {}
            name = (it.get('serviceName') or (bz.get('info') or {}).get('name') or '').strip()
            host = urllib.parse.urlparse(it.get('resource', '')).hostname or ''
            for acc in it.get('accepts') or []:
                q = (acc.get('payTo') or '').lower()
                if not q or acc.get('network') not in common.BASE_NETS: continue
                x = per[q]
                if name: x['names'][name[:80]] += 1
                if host: x['hosts'][host] += 1
                x['resources'].add(it.get('resource', ''))
                pr = common.base_usdc_price(acc)
                if pr is not None: x['prices'].append(pr)
        for q, x in per.items():
            ps = sorted(x['prices'])
            out[q] = {'snapshot': d, 'listed_as': x['names'].most_common(1)[0][0] if x['names'] else None,
                      'hosts': [h for h, _ in x['hosts'].most_common(3)], 'resources': len(x['resources']),
                      'posted': {'n': len(ps), 'min': round(ps[0], 6), 'median': round(statistics.median(ps), 6), 'max': round(ps[-1], 6)} if ps else None}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--min-buyers', type=int, default=MIN_BUYERS)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(os.path.join(common.OUT, 'payees_weekly.csv'))))
    weeks = sorted({r['week_start'] for r in rows})
    latest = weeks[-1]
    hist = collections.defaultdict(dict)
    for r in rows:
        hist[r['payee']][r['week_start']] = {'usd': float(r['usd']), 'payments': int(r['payments']), 'buyers': int(r['payers']),
                                             'median_paid': float(r['median_payment_usd']), 'category': r['category'],
                                             'category_source': r['category_source']}
    ever = {q for q, h in hist.items() if any(x['buyers'] >= a.min_buyers for x in h.values())}
    lst = listings()
    ex = {r['payee']: r['example'] for r in csv.DictReader(open(os.path.join(common.OUT, 'payee_classes.csv')))}
    sellers = []
    for q in ever:
        h = hist[q]
        last = h.get(latest)
        cur = last or h[max(h)]
        L = lst.get(q)
        label = (L or {}).get('listed_as') or ((L or {}).get('hosts') or [None])[0]
        sellers.append({
            'address': q, 'label': label, 'label_source': L['snapshot'] if L and label else None,
            'hosts': (L or {}).get('hosts', []), 'listed_resources': (L or {}).get('resources', 0),
            'posted_usd': (L or {}).get('posted'), 'example_listing': (ex.get(q) or '')[:200] or None,
            'category': cur['category'], 'category_source': cur['category_source'],
            'qualifies_latest': bool(last and last['buyers'] >= a.min_buyers),
            'latest': last, 'first_seen_week': min(h), 'weeks_in_index': len(h),
            'history': [{'week': w, **{k: h[w][k] for k in ('usd', 'payments', 'buyers', 'median_paid')}} for w in weeks if w in h],
        })
    sellers.sort(key=lambda s: (-((s['latest'] or {}).get('usd') or 0), s['address']))  # address breaks ties deterministically
    rank = 0
    for s in sellers:
        if s['qualifies_latest']: rank += 1; s['rank'] = rank
        else: s['rank'] = None
    os.makedirs(OUT, exist_ok=True)
    doc = {'built': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'latest_week': latest, 'weeks': weeks,
           'min_buyers': a.min_buyers, 'history_starts': weeks[0],
           'note': 'Clean = after the x402 Clean Index filters (docs/X402_INDEX_METHOD.md). Names are as the seller listed '
                   'them in the Coinbase CDP Bazaar; ownership is not verified. Addresses without a listing are shown as addresses.',
           'sellers': sellers}
    json.dump(doc, open(os.path.join(OUT, 'sellers.json'), 'w'), separators=(',', ':'))
    with open(os.path.join(OUT, 'sellers_latest.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rank', 'address', 'listed_as', 'category', 'clean_usd', 'clean_payments', 'buyers', 'median_paid_usd',
                    'posted_median_usd', 'first_seen_week'])
        for s in sellers:
            if not s['qualifies_latest']: continue
            L = s['latest']
            w.writerow([s['rank'], s['address'], s['label'] or '', s['category'], L['usd'], L['payments'], L['buyers'],
                        L['median_paid'], (s['posted_usd'] or {}).get('median', ''), s['first_seen_week']])
    print(f"{latest}: {rank} sellers with >= {a.min_buyers} clean buyers; {len(sellers)} seller pages (ever qualified); "
          f"{sum(1 for s in sellers if s['label'])} with a listing name")


if __name__ == '__main__':
    main()
