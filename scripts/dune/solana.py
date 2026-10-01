#!/usr/bin/env python3
"""x402 on Solana: page data from the Dune exports (analytics/dune/2_, 4_, 5_, x402_solana_weekly). No network.
Writes data/x402_solana/{weekly.csv, solana.json}."""
import collections, csv, datetime as dt, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
D = lambda *p: os.path.join(ROOT, 'data', *p)
rd = lambda p: list(csv.DictReader(open(p)))
f = lambda x: float(x) if x not in ('', None) else None

daily = rd(D('dune', '2_x402_solana_history.csv'))
W = collections.defaultdict(lambda: {'payments': 0, 'usd': 0.0, 'by': collections.Counter()})
for r in daily:
    d = dt.date.fromisoformat(r['day'][:10]); w = (d - dt.timedelta(days=d.weekday())).isoformat()
    x = W[w]; x['payments'] += int(f(r['payments'])); x['usd'] += f(r['usd']); x['by'][r['facilitator']] += f(r['usd'])
wk = rd(D('x402_solana', 'weekly_by_facilitator.csv'))
filt = collections.Counter(); 
for r in wk: filt[r['week'][:10]] += f(r['usd_after_single_buyer_filter'])
weeks = sorted(w for w in W if w <= '2026-09-21' and W[w]['usd'] > 0)
hist = [{'week_start': w, 'settlements': W[w]['payments'], 'usd': round(W[w]['usd'], 2),
         'usd_after_single_buyer_filter': round(filt[w], 2) if w in filt else None,
         'top_facilitator': W[w]['by'].most_common(1)[0][0], 'top_facilitator_share': round(W[w]['by'].most_common(1)[0][1] / W[w]['usd'], 4)} for w in weeks]
with open(D('x402_solana', 'weekly.csv'), 'w', newline='') as fh:
    w_ = csv.DictWriter(fh, fieldnames=list(hist[0])); w_.writeheader(); w_.writerows(hist)
lw = '2026-09-21'
fac = [{'facilitator': r['facilitator'], 'payments': int(f(r['payments'])), 'usd': round(f(r['usd']), 2), 'median_usd': f(r['median_usd']),
        'payers': int(f(r['payers'])), 'payees': int(f(r['payees']))} for r in wk if r['week'][:10] == lw]
tot = sum(x['usd'] for x in fac)
for x in fac: x['share'] = round(x['usd'] / tot, 4)
sel = [{'payee': r['payee'], 'facilitator': r['facilitator'], 'payments': int(f(r['payments'])), 'usd': round(f(r['usd']), 2), 'median_usd': f(r['median_usd']),
        'buyers': int(f(r['buyers'])), 'repeat_buyers': int(f(r['repeat_buyers'])), 'top_buyer_share': round(f(r['top_buyer_share']), 4)} for r in rd(D('dune', '4_x402_solana_sellers.csv'))]
whale = sel[0]
fund = rd(D('dune', '5_x402_solana_funding.csv'))
multi = [r for r in fund if int(f(r['buyers_funded'])) >= 10]
pd = collections.Counter(); 
for r in daily:
    if r['facilitator'] == 'payai': pd[r['day'][:10]] += int(f(r['payments']))
monthly = collections.Counter()
for r in daily: monthly[r['day'][:7]] += f(r['usd'])
pk = max(monthly.items(), key=lambda kv: kv[1])
doc = {'source': 'Dune (tokens_solana.transfers), 27 published x402 facilitator fee payers (x402scan list f205fbe, 2026-08-17)', 'week': lw,
       'history': hist, 'facilitators': fac, 'sellers': sel, 'week_usd': round(tot, 2), 'week_after_single_buyer': round(filt[lw], 2),
       'whale': whale, 'week_ex_whale': round(tot - whale['usd'], 2), 'sellers_5plus': sum(1 for s in sel if s['buyers'] >= 5),
       'funders_10plus': len(multi), 'funders_10plus_usd': round(sum(f(r['their_x402_usd']) for r in multi), 2),
       'peak_month': pk[0], 'peak_month_usd': round(pk[1], 2),
       'payai_before': pd.get('2026-09-07'), 'payai_after_median': sorted(v for d, v in pd.items() if '2026-09-09' <= d <= '2026-09-27')[9] if pd else None,
       'unlisted_candidates': 13}
json.dump(doc, open(D('x402_solana', 'solana.json'), 'w'))
print({k: v for k, v in doc.items() if k not in ('history', 'facilitators', 'sellers', 'whale')})
