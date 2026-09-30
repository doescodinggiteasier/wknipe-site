#!/usr/bin/env python3
"""ORDER_010 follow-up analyses (Wes, 2026-09-30: "the highest-EV checks"). Reads the build caches; writes
data/x402_index/analysis.json. Needs build.py to have run. Blockscout calls only for B (cached in the links cache).

A. Tripwire anatomy: content+data cleaned USD by seller per week, concentration, and week-on-week decomposition
   (continuing sellers vs entrants vs exits).
B. Fan-out screen on every content/data cleaned seller with >= 5 buyers and >= $5 that week (build.py screens only the top 20 by USD).
C. Content audit sheet: every cleaned 'content' seller with its listing evidence (hand-checked in the handoff).
D. Filter sensitivity: cleaned USD if the dust threshold were 3 or 5 buyers, without the fan-out check, and
   excluding single payments above $100.
E. Buyer breadth: distinct cleaned buyers, buyers paying >= 2 sellers, smart-wallet share (bytes-signature variant),
   for all categories and for content+data.
Usage: python3 scripts/x402_index/analysis.py
"""
import collections, csv, datetime as dt, json, os, random, statistics, sys

sys.path.insert(0, os.path.dirname(__file__))
import build, common

OUT = os.path.join(common.OUT, 'analysis.json')
CD = ('content', 'data')


def hhi(xs):
    t = sum(xs)
    return round(sum((x / t) ** 2 for x in xs), 4) if t else None


def fanout_all(week, clean, cat, min_buyers=5, min_usd=5.0, sample=12, need_frac=2 / 3):
    cache = json.load(open(build.LINKS)) if os.path.exists(build.LINKS) else {}
    out = {}
    for q, x in clean.items():
        if cat.get(q) not in CD or len(x['payers']) < min_buyers or x['usd'] < min_usd: continue
        buyers = sorted(x['payers']); random.Random(q).shuffle(buyers); s = buyers[:sample]
        funders = collections.Counter()
        for b in s:
            try:
                for f in set(build.links(b, cache, ('to',))): funders[f] += 1
            except Exception as e:
                print('lookup failed', b, str(e)[:80], flush=True)
        shared_f = {f for f, k in funders.items() if k >= 2}
        shared = sum(funders[f] for f in shared_f)
        isolated = sum(1 for b in s if not any(b in y['payers'] for qq, y in clean.items() if qq != q))
        circular = None
        if shared >= need_frac * len(s):
            try:
                circular = bool(shared_f & set(build.links(q, cache, ('from',))))
            except Exception as e:
                print('sweep lookup failed', q, str(e)[:80], flush=True)
        out[q] = {'category': cat.get(q), 'usd': round(x['usd'], 2), 'buyers': len(x['payers']), 'sampled': len(s),
                  'payments_per_buyer': round(x['n'] / len(x['payers']), 2), 'buyers_with_shared_funder': shared,
                  'isolated_buyers': isolated, 'circular': circular,
                  'shared_funding': shared >= need_frac * len(s),
                  'flagged': shared >= need_frac * len(s) and (bool(circular) or isolated >= 10)}
        json.dump(cache, open(build.LINKS, 'w'))
    return out


def raw_rows(week):
    rows, seen = [], set()
    for line in open(os.path.join(common.STATE, f'x402_week_{week}', 'txs.jsonl')):
        r = json.loads(line)
        if r['hash'] in seen or not r.get('payee'): continue
        seen.add(r['hash'])
        if r['payer'] in common.OURS or r['payee'] in common.OURS: continue
        rows.append((r['payer'], r['payee'], r['usdc_atomic'], r['selector'], r['ts']))
    return rows


def main():
    cat, src, _ = build.categories()
    weeks = build.complete_weeks()
    res = {'weeks': [str(w) for w in weeks], 'A_tripwire': {}, 'B_fanout_content_data': {}, 'C_content_audit': [],
           'D_sensitivity': {}, 'E_buyers': {}}
    prev = None
    for w in weeks:
        W = build.filter_week(w, 300)
        clean = dict(W['agg']['clean'])
        flagged = {q for q, f in build.fanout_flags(w, clean).items() if f['flagged']}
        for q in flagged: clean.pop(q, None)
        # A
        cd = {q: x['usd'] for q, x in clean.items() if cat.get(q) in CD}
        tot = sum(cd.values()); top = sorted(cd.items(), key=lambda t: -t[1])
        a = {'usd': round(tot, 2), 'sellers': len(cd), 'hhi': hhi(list(cd.values())),
             'top1_share': round(top[0][1] / tot, 4) if tot else None,
             'top5_share': round(sum(v for _, v in top[:5]) / tot, 4) if tot else None,
             'top5': [{'payee': q, 'category': cat.get(q), 'usd': round(v, 2), 'buyers': len(clean[q]['payers']),
                       'payments': clean[q]['n']} for q, v in top[:5]]}
        if prev:
            pw, pcd = prev
            cont = set(cd) & set(pcd)
            a['change_vs_prev'] = {'total': round(tot - sum(pcd.values()), 2),
                                   'continuing_sellers': round(sum(cd[q] - pcd[q] for q in cont), 2),
                                   'entrants': round(sum(v for q, v in cd.items() if q not in pcd), 2),
                                   'exits': round(-sum(v for q, v in pcd.items() if q not in cd), 2),
                                   'n_continuing': len(cont)}
        res['A_tripwire'][str(w)] = a
        prev = (w, cd)
        # B
        res['B_fanout_content_data'][str(w)] = fanout_all(w, clean, cat)
        # D (dust variants from the d05 stage)
        d05 = W['agg']['d05']
        def clean_usd(k, fan=True, cats=None):
            return round(sum(x['usd'] for q, x in d05.items() if len(x['payers']) >= k and (not fan or q not in flagged)
                             and (cats is None or cat.get(q) in cats)), 2)
        rows = raw_rows(w)
        big = collections.Counter()
        for p, q, amt, _, _ in rows:
            if amt > 100_000_000: big[q] += amt / 1e6
        base = clean_usd(2)
        res['D_sensitivity'][str(w)] = {
            'clean_usd_base (dust>=2, fan-out on)': base, 'dust>=3': clean_usd(3), 'dust>=5': clean_usd(5),
            'fan-out off': clean_usd(2, fan=False),
            'base minus single payments >$100': round(base - sum(v for q, v in big.items() if q in clean), 2),
            'content+data base': clean_usd(2, cats=CD), 'content+data dust>=5': clean_usd(5, cats=CD)}
        # E
        sel = collections.defaultdict(set); smart = collections.Counter(); tot_n = collections.Counter(); hours = collections.defaultdict(set)
        for p, q, amt, s, ts in rows:
            if q not in clean: continue
            g = 'content+data' if cat.get(q) in CD else 'other categories'
            sel[p].add(q)
            for k in (g, 'all'):
                tot_n[k] += 1; smart[k] += s == '0xcf092995'
        buyers = {'all': set(sel)}
        buyers['content+data'] = {p for p, qs in sel.items() if any(cat.get(q) in CD for q in qs)}
        res['E_buyers'][str(w)] = {k: {'buyers': len(b), 'buyers_paying_2plus_sellers': sum(len(sel[p]) >= 2 for p in b),
                                       'smart_wallet_payment_share': round(smart[k] / tot_n[k], 4) if tot_n[k] else None}
                                   for k, b in buyers.items()}
    # C: content sellers in any cleaned week, with evidence
    ev = common.payee_texts()
    seen = set()
    for w in weeks:
        for r in csv.DictReader(open(os.path.join(common.OUT, 'payees_weekly.csv'))):
            if r['week_start'] == str(w) and r['category'] == 'content' and r['payee'] not in seen:
                seen.add(r['payee'])
                res['C_content_audit'].append({'payee': r['payee'], 'source': r['category_source'], 'usd_week': float(r['usd']),
                                               'week': str(w), 'buyers': int(r['payers']),
                                               'evidence': ' || '.join(t[:200] for t in ev.get(r['payee'], [])[:3])})
    json.dump(res, open(OUT, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('C_content_audit', 'B_fanout_content_data')}, indent=1))
    for w, b in res['B_fanout_content_data'].items():
        print(w, 'screened', len(b), 'shared funding', sum(v['shared_funding'] for v in b.values()),
              'manufactured', {q[:10]: (v['category'], v['usd'], 'circular' if v['circular'] else 'isolated') for q, v in b.items() if v['flagged']})
    print('content sellers to audit:', len(res['C_content_audit']))


if __name__ == '__main__':
    main()
