#!/usr/bin/env python3
"""ORDER_013 Phase 2-3: market, buyer, price-paid and seller-quality statistics for wknipe.com (Market, Buyers, Sellers).

Per complete index week this reads the raw settlements (STATE/x402_week_<Monday>/txs.jsonl) together with the index's
own filter cache (STATE/x402_index/week_<Monday>.json[.gz]) and fan-out flags, so every payment gets exactly the fate
the index gave it: ours / closed loop (C1) / funding-linked (C2) / fan-out / single-buyer dust / clean. The per-week
result is cached as STATE/x402_index/market_<Monday>.json.gz (compact; the raw week is not needed again, which is how
the public repo and CI rebuild it). Cross-week series (retention, movers, concentration) are computed from the caches.

Writes data/x402_market/: market.json (everything the site charts), one CSV per chart, sellers_extra.json.
No network, no keys. Usage: python3 scripts/x402_market/build.py
"""
import collections, csv, datetime as dt, json, math, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'x402_index'))
sys.path.insert(0, os.path.join(HERE, '..', 'o5'))
import common  # noqa: E402
import build as index_build  # noqa: E402
from x402_filter import sccs  # noqa: E402

OUT = os.path.join(common.ROOT, 'data', 'x402_market')
WEEKCACHE = os.path.join(common.STATE, 'x402_index')
CATS = common.CATEGORIES
MIN_BUYERS = 5  # same threshold as the seller leaderboard
SENS_K = (1, 2, 3, 5)  # ORDER_014: min-genuine-buyer thresholds for the single-buyer sensitivity panel
FATES = ['ours', 'c1', 'c2', 'fanout', 'dust', 'clean']
FATE_LABEL = {'ours': 'My own test and API payments', 'c1': 'Closed loops and self-payments',
              'c2': 'Funding-linked payer and seller', 'fanout': 'Fan-out from shared funders',
              'dust': 'Sellers with a single buyer', 'clean': 'Demand-cleaned'}
# half-decade log bins for payment sizes and spend per buyer, $0.0001 .. $100k
EDGES = [10 ** (k / 2) for k in range(-8, 11)]
TIERS = [(0, 0.1, 'under $0.10'), (0.1, 1, '$0.10–$1'), (1, 10, '$1–$10'), (10, 100, '$10–$100'),
         (100, 1000, '$100–$1k'), (1000, float('inf'), '$1k and up')]
SPB = [(1, 1, '1'), (2, 2, '2'), (3, 5, '3–5'), (6, 10, '6–10'), (11, 10 ** 9, '11+')]


def pct(xs, q):
    return index_build.pct(xs, q)


def hist(values, weights=None):
    counts = [0] * (len(EDGES) - 1); usd = [0.0] * (len(EDGES) - 1)
    for i, v in enumerate(values):
        if v <= 0: continue
        k = min(max(0, int(math.floor(math.log10(v) * 2)) + 8), len(counts) - 1)
        counts[k] += 1; usd[k] += weights[i] if weights else v
    return [{'lo': round(EDGES[k], 6), 'hi': round(EDGES[k + 1], 6), 'n': counts[k], 'usd': round(usd[k], 2)}
            for k in range(len(counts)) if counts[k]]


def facilitator_names():
    return {a.lower(): n for n, a, *_ in json.load(open(os.path.join(common.ROOT, 'data', 'x402', 'base_facilitators_2026-09-27.json')))}


def week_market(start, cat):
    """One week's per-payment statistics. Needs the raw week; cached afterwards."""
    cp = os.path.join(WEEKCACHE, f'market_{start}.json.gz')
    if os.path.exists(cp): return common.jload(cp)
    raw = os.path.join(common.STATE, f'x402_week_{start}', 'txs.jsonl')
    if not os.path.exists(raw):
        print(f'{start}: no raw week and no market cache; skipped', flush=True); return None
    wc = common.jload(index_build.week_cache(start))
    fan = json.load(open(os.path.join(WEEKCACHE, f'fanout_{start}.json')))
    flagged = {q for q, f in fan.items() if f['flagged']}
    agg = wc['agg']
    d05 = {(p, q) for q, x in agg['d05'].items() for p in x['payers']}
    clean_pre = {(p, q) for q, x in agg['clean'].items() for p in x['payers']}
    rows, seen = [], set()
    for line in open(raw):
        r = json.loads(line)
        if r['hash'] in seen: continue
        seen.add(r['hash'])
        if r.get('payer') and r.get('payee') and r.get('usdc_atomic') is not None:
            rows.append((r['payer'].lower(), r['payee'].lower(), int(r['usdc_atomic']) / 1e6, (r.get('facilitator') or '').lower()))
    theirs = [(p, q) for p, q, _, _ in rows if p not in common.OURS and q not in common.OURS]
    comp = sccs(set(theirs))
    fates = []
    for p, q, a, f in rows:
        if p in common.OURS or q in common.OURS: fates.append('ours')
        elif (p, q) in d05:
            fates.append(('fanout' if q in flagged else 'clean') if (p, q) in clean_pre else 'dust')
        else:
            fates.append('c1' if p == q or (p in comp and comp.get(p) == comp.get(q)) else 'c2')
    wf = {k: {'payments': 0, 'usd': 0.0} for k in FATES}
    names = facilitator_names()
    fac = collections.defaultdict(lambda: {'raw_payments': 0, 'raw_usd': 0.0, 'clean_payments': 0, 'clean_usd': 0.0})
    tick = collections.defaultdict(list)
    buyer = collections.defaultdict(lambda: {'usd': 0.0, 'n': 0, 'sellers': set(), 'cat': collections.Counter()})
    pair = collections.defaultdict(lambda: [0, 0.0])
    for (p, q, a, f), fate in zip(rows, fates):
        wf[fate]['payments'] += 1; wf[fate]['usd'] += a
        if fate == 'ours': continue
        fa = fac[f]; fa['raw_payments'] += 1; fa['raw_usd'] += a
        if fate != 'clean': continue
        fa['clean_payments'] += 1; fa['clean_usd'] += a
        c = cat.get(q) or 'unclassed'
        tick[c].append(a); tick['all'].append(a)
        b = buyer[p]; b['usd'] += a; b['n'] += 1; b['sellers'].add(q); b['cat'][c] += a
        pp = pair[(p, q)]; pp[0] += 1; pp[1] += a
    # per seller: top-buyer share of clean USD, share of buyers paying 2+ times, raw/d05/clean USD (index filter stages)
    per = collections.defaultdict(list)
    for (p, q), (n, u) in pair.items(): per[q].append((n, u))
    sellers = {}
    for q, xs in per.items():
        tot = sum(u for _, u in xs)
        sellers[q] = {'top_buyer_share': round(max(u for _, u in xs) / tot, 4) if tot else None,
                      'repeat_buyer_rate': round(sum(1 for n, _ in xs if n >= 2) / len(xs), 4), 'buyers': len(xs)}
    for q in set(agg['raw']) & (set(per) | {q for q, x in agg['raw'].items() if x['usd'] >= 1}):
        s = sellers.setdefault(q, {})
        s['raw_usd'] = round(agg['raw'][q]['usd'], 2)
        s['d05_usd'] = round(agg['d05'].get(q, {}).get('usd', 0), 2)
        s['clean_usd'] = round(sum(u for _, u in per.get(q, [])), 2)
        s['fanout'] = q in flagged
    tiers = []
    for lo, hi, lab in TIERS:
        bs = [b for b in buyer.values() if lo <= b['usd'] < hi]
        cs = collections.Counter()
        for b in bs: cs.update(b['cat'])
        tiers.append({'tier': lab, 'buyers': len(bs), 'usd': round(sum(b['usd'] for b in bs), 2),
                      'payments': sum(b['n'] for b in bs), 'by_category_usd': {c: round(cs[c], 2) for c in CATS if cs[c]}})
    spb = [{'sellers': lab, 'buyers': sum(1 for b in buyer.values() if lo <= len(b['sellers']) <= hi)} for lo, hi, lab in SPB]
    res = {
        'week': str(start), 'settlements_all': len(rows),
        'waterfall': [{'step': k, 'label': FATE_LABEL[k], 'payments': wf[k]['payments'], 'usd': round(wf[k]['usd'], 2)} for k in FATES],
        'facilitators': sorted(({'facilitator': f, 'name': names.get(f, f[:10]), **{k: round(v, 2) if isinstance(v, float) else v for k, v in x.items()}}
                                for f, x in fac.items()), key=lambda r: -r['raw_usd']),
        'tickets': {c: {'n': len(v), 'p10': pct(v, .1), 'p50': pct(v, .5), 'p90': pct(v, .9), 'hist': hist(v)} for c, v in tick.items()},
        'buyers': {'n': len(buyer), 'spend_p50': pct([b['usd'] for b in buyer.values()], .5),
                   'spend_hist': hist([b['usd'] for b in buyer.values()]), 'sellers_per_buyer': spb,
                   'multi_homing_share': round(sum(1 for b in buyer.values() if len(b['sellers']) >= 2) / len(buyer), 4) if buyer else None,
                   'tiers': tiers},
        'sellers': sellers,
    }
    common.jdump(res, cp)
    print(f'{start}: market cache written ({len(rows)} settlements)', flush=True)
    return res


def write_csv(name, rows):
    if not rows: return
    with open(os.path.join(OUT, name), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    cat, _, _ = index_build.categories()
    weeks = [str(w) for w in index_build.complete_weeks()]
    M = {w: m for w in weeks if (m := week_market(w, cat))}
    weeks = [w for w in weeks if w in M]
    weekly = list(csv.DictReader(open(os.path.join(common.OUT, 'weekly.csv'))))
    payees = list(csv.DictReader(open(os.path.join(common.OUT, 'payees_weekly.csv'))))
    head = json.load(open(os.path.join(common.OUT, 'headline.json')))
    fan = {w: {q for q, f in json.load(open(os.path.join(WEEKCACHE, f'fanout_{w}.json'))).items() if f['flagged']} for w in weeks}

    # consistency: clean USD in the waterfall must equal the index's published clean USD
    for w in weeks:
        pub = next(float(r['usd']) for r in weekly if r['week_start'] == w and r['stage'] == 'clean' and r['category'] == 'all')
        got = next(s['usd'] for s in M[w]['waterfall'] if s['step'] == 'clean')
        assert abs(pub - got) < 0.05 + 1e-6 * pub, f'{w}: waterfall clean {got} != index clean {pub}'

    # ORDER_014: sensitivity of clean USD to the single-buyer filter. Clean = d05 sellers with >= 2 distinct payers, minus
    # fan-out sellers; here the payer threshold is 1 / 2 (published) / 3 / 5, everything else unchanged.
    sens = []
    for w in weeks:
        d05 = common.jload(index_build.week_cache(dt.date.fromisoformat(w)))['agg']['d05']
        for k in SENS_K:
            xs = [x for q, x in d05.items() if len(x['payers']) >= k and q not in fan[w]]
            sens.append({'week_start': w, 'min_buyers': k, 'clean_usd': round(sum(x['usd'] for x in xs), 2), 'sellers': len(xs),
                         'payments': sum(x['n'] for x in xs), 'published': k == 2})
        pub = next(float(r['usd']) for r in weekly if r['week_start'] == w and r['stage'] == 'clean' and r['category'] == 'all')
        got = next(r['clean_usd'] for r in sens if r['week_start'] == w and r['min_buyers'] == 2)
        assert abs(pub - got) < 0.05 + 1e-6 * pub, f'{w}: sensitivity k=2 {got} != index clean {pub}'

    # buyer sets per week (clean, after fan-out), from the index caches
    bsets = {}
    for w in weeks:
        agg = common.jload(index_build.week_cache(dt.date.fromisoformat(w)))['agg']['clean']
        bsets[w] = set().union(*[set(x['payers']) for q, x in agg.items() if q not in fan[w]]) if agg else set()
    buyers_weekly, seen = [], set()
    for i, w in enumerate(weeks):
        prev = bsets[weeks[i - 1]] if i else set()
        new = bsets[w] - seen
        buyers_weekly.append({'week_start': w, 'active_buyers': len(bsets[w]),
                              'new_buyers': len(new) if i else '', 'returning_buyers': len(bsets[w] & prev) if i else '',
                              'reactivated_buyers': len((bsets[w] & seen) - prev) if i else '',
                              'median_spend_usd': round(M[w]['buyers']['spend_p50'] or 0, 4),
                              'multi_homing_share': M[w]['buyers']['multi_homing_share']})
        seen |= bsets[w]
    retention, seen = [], set()
    for i, w in enumerate(weeks):
        coh = bsets[w] - seen if i else set()
        seen |= bsets[w]
        if not i: continue  # the first week has no "new" cohort (history starts there)
        row = {'cohort_week': w, 'new_buyers': len(coh)}
        for k in range(1, 5):
            j = i + k
            row[f'week_{k}'] = round(len(coh & bsets[weeks[j]]) / len(coh), 4) if j < len(weeks) and coh else ''
        retention.append(row)

    # concentration per category per week (clean USD by seller)
    conc = []
    by = collections.defaultdict(list)
    for r in payees: by[(r['week_start'], r['category'])].append(float(r['usd'])); by[(r['week_start'], 'all')].append(float(r['usd']))
    for w in weeks:
        for c in CATS + ['all']:
            xs = sorted(by.get((w, c), []), reverse=True); tot = sum(xs)
            if not xs or tot <= 0: continue
            conc.append({'week_start': w, 'category': c, 'sellers': len(xs), 'usd': round(tot, 2),
                         'top1_share': round(xs[0] / tot, 4), 'top10_share': round(sum(xs[:10]) / tot, 4),
                         'hhi': round(sum((x / tot * 100) ** 2 for x in xs)), 'effective_sellers': round(1 / sum((x / tot) ** 2 for x in xs), 1)})

    # movers: latest vs previous week, sellers with >= MIN_BUYERS buyers
    movers = []
    if len(weeks) >= 2:
        a, b = weeks[-2], weeks[-1]
        pw = {w: {r['payee']: r for r in payees if r['week_start'] == w} for w in (a, b)}
        q5 = {w: {q for q, r in pw[w].items() if int(r['payers']) >= MIN_BUYERS} for w in (a, b)}
        for q in q5[b] - q5[a]:
            r = pw[b][q]; movers.append({'kind': 'entered', 'payee': q, 'category': r['category'], 'usd_prev': float(pw[a][q]['usd']) if q in pw[a] else 0.0,
                                         'usd_now': float(r['usd']), 'buyers_prev': int(pw[a][q]['payers']) if q in pw[a] else 0, 'buyers_now': int(r['payers'])})
        for q in q5[a] - q5[b]:
            r = pw[a][q]; movers.append({'kind': 'exited', 'payee': q, 'category': r['category'], 'usd_prev': float(r['usd']),
                                         'usd_now': float(pw[b][q]['usd']) if q in pw[b] else 0.0, 'buyers_prev': int(r['payers']),
                                         'buyers_now': int(pw[b][q]['payers']) if q in pw[b] else 0})
        for q in q5[a] & q5[b]:
            ra, rb = pw[a][q], pw[b][q]
            movers.append({'kind': 'continuing', 'payee': q, 'category': rb['category'], 'usd_prev': float(ra['usd']), 'usd_now': float(rb['usd']),
                           'buyers_prev': int(ra['payers']), 'buyers_now': int(rb['payers'])})
        for m in movers: m['usd_change'] = round(m['usd_now'] - m['usd_prev'], 2)
        movers.sort(key=lambda m: (-abs(m['usd_change']), m['payee']))

    # tripwire series (content + data, clean) with the reopen threshold: +20%/month compounding from the first week
    cd = head['content_plus_data_clean_usd_by_week']
    tw = [{'week_start': w, 'content_plus_data_usd': cd[w], 'content_usd': float(next(r['usd'] for r in weekly if r['week_start'] == w and r['stage'] == 'clean' and r['category'] == 'content')),
           'data_usd': float(next(r['usd'] for r in weekly if r['week_start'] == w and r['stage'] == 'clean' and r['category'] == 'data')),
           'threshold_usd': round(cd[weeks[0]] * 1.2 ** ((dt.date.fromisoformat(w) - dt.date.fromisoformat(weeks[0])).days / 30.44), 2)} for w in weeks if w in cd]

    wf_rows = [{'week_start': w, **s, 'label': FATE_LABEL[s['step']]} for w in weeks for s in M[w]['waterfall']]  # labels from code, not the week cache
    fac_rows = [{'week_start': w, **{k: v for k, v in f.items()}} for w in weeks for f in M[w]['facilitators']]
    tick_rows = [{'week_start': w, 'category': c, 'payments': t['n'], 'p10_usd': t['p10'], 'median_usd': t['p50'], 'p90_usd': t['p90']}
                 for w in weeks for c, t in sorted(M[w]['tickets'].items())]
    tick_hist = [{'week_start': w, 'category': c, 'bin_lo_usd': h['lo'], 'bin_hi_usd': h['hi'], 'payments': h['n'], 'usd': h['usd']}
                 for w in weeks for c, t in sorted(M[w]['tickets'].items()) for h in t['hist']]
    spend_hist = [{'week_start': w, 'bin_lo_usd': h['lo'], 'bin_hi_usd': h['hi'], 'buyers': h['n'], 'usd': h['usd']} for w in weeks for h in M[w]['buyers']['spend_hist']]
    spb = [{'week_start': w, **x} for w in weeks for x in M[w]['buyers']['sellers_per_buyer']]
    tiers = [{'week_start': w, 'tier': t['tier'], 'buyers': t['buyers'], 'usd': t['usd'], 'payments': t['payments'],
              **{f'usd_{c}': t['by_category_usd'].get(c, 0) for c in CATS}} for w in weeks for t in M[w]['buyers']['tiers']]
    mix = [{k: r[k] for k in ('week_start', 'category', 'payments', 'usd', 'payees', 'payers')} for r in weekly if r['stage'] == 'clean' and r['category'] != 'all']
    for name, rows in (('waterfall.csv', wf_rows), ('facilitators.csv', fac_rows), ('tickets.csv', tick_rows),
                       ('ticket_histogram.csv', tick_hist), ('buyers_weekly.csv', buyers_weekly), ('retention.csv', retention),
                       ('buyer_spend_histogram.csv', spend_hist), ('sellers_per_buyer.csv', spb), ('buyer_tiers.csv', tiers),
                       ('concentration.csv', conc), ('movers.csv', movers), ('tripwire.csv', tw), ('category_mix.csv', mix),
                       ('buyer_threshold_sensitivity.csv', sens)):
        write_csv(name, rows)

    # per-seller extras for seller pages
    extra = collections.defaultdict(dict)
    for w in weeks:
        for q, s in M[w]['sellers'].items():
            if s.get('buyers') or s.get('raw_usd', 0) >= 1: extra[q][w] = s
    common.jdump({'weeks': weeks, 'sellers': extra}, os.path.join(OUT, 'sellers_extra.json'))
    doc = {'weeks': weeks, 'latest_week': weeks[-1], 'min_buyers': MIN_BUYERS,
           'fate_labels': FATE_LABEL, 'waterfall': wf_rows, 'facilitators': fac_rows, 'tickets': tick_rows, 'ticket_histogram': tick_hist,
           'buyers_weekly': buyers_weekly, 'retention': retention, 'buyer_spend_histogram': spend_hist, 'sellers_per_buyer': spb,
           'buyer_tiers': tiers, 'concentration': conc, 'movers': movers, 'tripwire': tw, 'category_mix': mix,
           'buyer_threshold_sensitivity': sens}
    json.dump(doc, open(os.path.join(OUT, 'market.json'), 'w'), default=str)
    lw = weeks[-1]
    print(json.dumps({'weeks': weeks, 'waterfall_latest': M[lw]['waterfall'], 'buyers_latest': buyers_weekly[-1],
                      'retention': retention, 'facilitators_top3': M[lw]['facilitators'][:3]}, indent=1, default=str))


if __name__ == '__main__':
    main()
