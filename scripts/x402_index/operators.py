#!/usr/bin/env python3
"""Independent-operator count (Wes, 2026-09-30): how many distinct operators, not wallets, buy cleaned content, data and
search on x402 in one week.

Wallets are merged into one operator when they were topped up by the same untagged wallet (newest 50 incoming
non-settlement USDC transfers, the build.links() rule); chains of shared funders merge too (union-find). Exchanges,
bridges, contracts and named/tagged addresses never merge anyone, because they fund unrelated people.
So the count is an UPPER bound on independent operators: two wallets of one operator funded from an exchange, or
funded before their newest 50 transfers, stay separate.
Writes data/x402_index/operators_<week>.json. Usage: python3 scripts/x402_index/operators.py [--week 2026-09-21]
"""
import argparse, collections, datetime as dt, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import build, common

GROUPS = {'content': {'content'}, 'data': {'data'}, 'search': {'search'}, 'content+data+search': {'content', 'data', 'search'}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--week')
    a = ap.parse_args()
    week = dt.date.fromisoformat(a.week) if a.week else build.complete_weeks()[-1]
    cat, _, _ = build.categories()
    clean = dict(build.filter_week(week, 300)['agg']['clean'])
    for q, f in build.fanout_flags(week, clean).items():
        if f['flagged']: clean.pop(q, None)
    target = {q: x for q, x in clean.items() if cat.get(q) in GROUPS['content+data+search']}
    buyers = sorted({p for x in target.values() for p in x['payers']})
    print(f'{week}: {len(target)} sellers, {len(buyers)} buyer wallets', flush=True)
    cache = json.load(open(build.LINKS)) if os.path.exists(build.LINKS) else {}
    uf, failed = build.UF(), 0
    for i, b in enumerate(buyers):
        uf.f(b)
        try:
            for f in build.links(b, cache, ('to',)): uf.u(b, f)
        except Exception as e:
            failed += 1
        if i % 100 == 0:
            json.dump(cache, open(build.LINKS, 'w')); print(f'  {i}/{len(buyers)} looked up, {failed} failed', flush=True)
    json.dump(cache, open(build.LINKS, 'w'))
    # USD per buyer wallet per group, from the per-payment rows
    usd = collections.defaultdict(lambda: collections.Counter())
    seen = set()
    for line in open(os.path.join(common.STATE, f'x402_week_{week}', 'txs.jsonl')):
        r = json.loads(line)
        if r['hash'] in seen or r.get('payee') not in target: continue
        seen.add(r['hash'])
        for g, cats in GROUPS.items():
            if cat.get(r['payee']) in cats: usd[g][r['payer']] += r['usdc_atomic'] * int(r.get('n', 1)) / 1e6
    out = {'week': str(week), 'buyer_wallets_looked_up': len(buyers), 'lookup_failures': failed,
           'method': __doc__.strip().splitlines()[2:6], 'groups': {}}
    for g in GROUPS:
        ops = collections.Counter()
        for b, v in usd[g].items(): ops[uf.f(b)] += v
        tot = sum(ops.values()); vals = sorted(ops.values(), reverse=True)
        cum, n50, n80 = 0, None, None
        for i, v in enumerate(vals, 1):
            cum += v
            if n50 is None and cum >= 0.5 * tot: n50 = i
            if n80 is None and cum >= 0.8 * tot: n80 = i
        multi = collections.Counter(uf.f(b) for b in usd[g])
        out['groups'][g] = {'usd': round(tot, 2), 'buyer_wallets': len(usd[g]), 'operators_upper_bound': len(ops),
                            'operators_with_2plus_wallets': sum(1 for k in multi.values() if k >= 2),
                            'largest_operator_wallets': max(multi.values()) if multi else 0,
                            'operators_spending_1usd_plus': sum(1 for v in vals if v >= 1),
                            'operators_spending_10usd_plus': sum(1 for v in vals if v >= 10),
                            'operators_for_50pct_usd': n50, 'operators_for_80pct_usd': n80,
                            'top_operator_share': round(vals[0] / tot, 4) if tot else None}
    p = os.path.join(common.OUT, f'operators_{week}.json')
    json.dump(out, open(p, 'w'), indent=1)
    print(json.dumps(out['groups'], indent=1))


if __name__ == '__main__':
    main()
