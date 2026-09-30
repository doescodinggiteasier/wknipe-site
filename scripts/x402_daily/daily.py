#!/usr/bin/env python3
"""ORDER_013 Phase 4: the daily job. Snapshot the CDP Bazaar listing, diff it against the previous day (listing churn
and posted-price changes), then run the endpoint status monitor on the same listing.

The previous day's price map lives in STATE/bazaar_daily/latest.json.gz (CI keeps it in the Actions cache, not git);
if it is missing, the newest weekly snapshot (STATE/bazaar/) is the baseline and the diff says so in `since`.
Writes data/bazaar_daily/{counts.csv, price_changes.csv}; appends, one row per day.
Usage: python3 scripts/x402_daily/daily.py [--from PATH] [--no-monitor] [--cap 4000]
"""
import argparse, csv, datetime as dt, json, os, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_status'))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_prices'))
import common  # noqa: E402

OUT = os.path.join(common.ROOT, 'data', 'bazaar_daily')
PREV = os.path.join(common.STATE, 'bazaar_daily', 'latest.json.gz')


def fetch():
    import bazaar_snapshot as b
    items, off = [], 0
    while True:
        d = b.get(f'{b.API}?limit=1000&offset={off}')
        page = d.get('items') or []
        items += page
        if len(page) < 1000: break
        off += 1000
        import time; time.sleep(1)
    if len(items) < 1000: raise SystemExit(f'only {len(items)} resources listed; refusing a partial snapshot')
    return items


def price_map(items):
    from classify_listings import listing_text, key, load_cache
    cls = load_cache()
    out = {}
    for it in items:
        for a in it.get('accepts') or []:
            if a.get('network') not in common.BASE_NETS or not a.get('payTo'): continue
            k = f"{it.get('resource', '')}|{a['payTo'].lower()}"
            if k in out: break
            c = cls.get(key(listing_text(it))) or {}
            out[k] = {'p': common.base_usdc_price(a), 'h': urllib.parse.urlparse(it.get('resource', '')).hostname or '', 'c': c.get('category'), 'w': c.get('what')}
            break
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--from', dest='src'); ap.add_argument('--no-monitor', action='store_true')
    ap.add_argument('--cap', type=int, default=4000); ap.add_argument('--date', default=str(dt.datetime.now(dt.timezone.utc).date()))
    a = ap.parse_args()
    items = common.jload(a.src) if a.src else fetch()
    cur = price_map(items)
    if os.path.exists(PREV):
        prev_doc = common.jload(PREV); prev, since = prev_doc['map'], prev_doc['date']
    else:
        d, p = [s for s in common.bazaar_snapshots() if s[0] < a.date][-1]
        prev, since = price_map(common.jload(p)), d
    if since >= a.date:
        print(f'baseline {since} is not before {a.date}; nothing to diff'); prev = {}
    entered = [k for k in cur if k not in prev]; exited = [k for k in prev if k not in cur]
    changes = []
    for k, v in cur.items():
        o = prev.get(k)
        if o and o.get('p') and v.get('p') and abs(o['p'] - v['p']) > 1e-9:
            res, payto = k.rsplit('|', 1)
            changes.append({'date': a.date, 'since': since, 'host': v['h'], 'resource': res[:200], 'pay_to': payto, 'category': v.get('c') or '', 'what': v.get('w') or '',
                            'old_usd': o['p'], 'new_usd': v['p'], 'change': round(v['p'] / o['p'] - 1, 4)})
    os.makedirs(OUT, exist_ok=True)
    cp = os.path.join(OUT, 'counts.csv')
    rows = [r for r in (list(csv.DictReader(open(cp))) if os.path.exists(cp) else []) if r['date'] != a.date]
    rows.append({'date': a.date, 'since': since, 'listings': len(items), 'base_listings': len(cur), 'priced_base': sum(1 for v in cur.values() if v['p']),
                 'entered': len(entered) if prev else '', 'exited': len(exited) if prev else '', 'price_changes': len(changes) if prev else '',
                 'price_up': sum(1 for c in changes if c['change'] > 0) if prev else '', 'price_down': sum(1 for c in changes if c['change'] < 0) if prev else ''})
    with open(cp, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[-1])); w.writeheader(); w.writerows(sorted(rows, key=lambda r: r['date']))
    pp = os.path.join(OUT, 'price_changes.csv')
    old = [r for r in (list(csv.DictReader(open(pp))) if os.path.exists(pp) else []) if r['date'] != a.date]
    with open(pp, 'w', newline='') as f:
        fields = ['date', 'since', 'host', 'resource', 'pay_to', 'category', 'what', 'old_usd', 'new_usd', 'change']
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(old + changes)
    common.jdump({'date': a.date, 'map': cur}, PREV)
    print(json.dumps(rows[-1]))
    if not a.no_monitor:
        import monitor
        monitor.run(items, a.date, a.cap)


if __name__ == '__main__':
    main()
