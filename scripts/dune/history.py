#!/usr/bin/env python3
"""Weekly x402-on-Base history since launch, from the Dune export of analytics/dune/1_x402_base_history.sql.

Same raw definition as the index (settlements sent by the 128 known facilitators) plus the single-buyer filter;
the index's other filters need funding graphs and exist only for the weeks the index covers.
Writes data/x402_history/{base_weekly.csv, base_weekly_by_facilitator.csv, history.json}. No network.
"""
import collections, csv, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'data', 'dune', '1_x402_base_history.csv')
OUT = os.path.join(ROOT, 'data', 'x402_history')
os.makedirs(OUT, exist_ok=True)
rows = list(csv.DictReader(open(SRC)))
W = collections.defaultdict(lambda: {'settlements': 0, 'usd': 0.0, 'usd_after_single_buyer_filter': 0.0, 'facilitators_active': 0, 'top': ('', 0.0)})
byf = []
for r in rows:
    w = r['week'][:10]; x = W[w]; u = float(r['usd'])
    x['settlements'] += int(float(r['settlements'])); x['usd'] += u; x['usd_after_single_buyer_filter'] += float(r['usd_after_single_buyer_filter'])
    x['facilitators_active'] += 1
    if u > x['top'][1]: x['top'] = (r['facilitator'], u)
    byf.append({'week_start': w, 'facilitator': r['facilitator'], 'settlements': int(float(r['settlements'])), 'usd': round(u, 2),
                'median_usd': round(float(r['median_usd']), 6), 'payers': int(float(r['payers'])), 'payees': int(float(r['payees'])),
                'self_payments': int(float(r['self_payments'])), 'usd_after_single_buyer_filter': round(float(r['usd_after_single_buyer_filter']), 2)})
out = [{'week_start': w, 'settlements': x['settlements'], 'usd': round(x['usd'], 2), 'usd_after_single_buyer_filter': round(x['usd_after_single_buyer_filter'], 2),
        'facilitators_active': x['facilitators_active'], 'top_facilitator': x['top'][0], 'top_facilitator_share': round(x['top'][1] / x['usd'], 4) if x['usd'] else None}
       for w, x in sorted(W.items())]
for name, rs in (('base_weekly.csv', out), ('base_weekly_by_facilitator.csv', sorted(byf, key=lambda r: (r['week_start'], -r['usd'])))):
    with open(os.path.join(OUT, name), 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rs[0])); wr.writeheader(); wr.writerows(rs)
json.dump({'source': 'Dune (base.transactions), analytics/dune/1_x402_base_history.sql, run 2026-10-01', 'history': out}, open(os.path.join(OUT, 'history.json'), 'w'))
pk = max(out, key=lambda r: r['usd'])
print(f'{len(out)} weeks {out[0]["week_start"]}..{out[-1]["week_start"]}; peak {pk["week_start"]} ${pk["usd"]:,.0f}')
