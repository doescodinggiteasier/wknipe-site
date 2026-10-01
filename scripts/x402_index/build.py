#!/usr/bin/env python3
"""ORDER_010: build the demand-cleaned x402 (Base) weekly index from collected weeks and listing snapshots.

Pipeline per complete week (STATE/x402_week_<Monday>/ with COMPLETE, or its cached filter result; STATE = common.STATE):
  raw     = payer-resolved USDC transferWithAuthorization settlements sent by a known facilitator (both signature
            variants; Permit2/batch proxy paths, ~$23 in 2026-09-21, are excluded), de-duplicated by tx hash;
  d05     = raw minus D05-approx C1 (self-payment or settlement-graph SCC) and C2 (payer and payee in one funding-linked
            cluster, from Blockscout funding/sweep links of the busiest addresses). Both are LOWER bounds on manufacture;
  clean   = d05 minus S385 dust (payee paid by exactly one distinct payer that week).
  Each payee gets one category (common.CATEGORIES): hand label if any, else the cached model label, else 'unclassed'.
Posted prices: every CDP Bazaar snapshot (common.bazaar_snapshots()) is one observation for the week containing
  its date; median and IQR of exact-scheme Base USDC prices per resource, and a chain-linked Jevons index over
  resources (resource URL + payTo) listed in consecutive snapshot weeks.
Transacted prices: per payee, the median clean payment in the week; Jevons over payees present in consecutive weeks.
Writes data/x402_index/{weekly.csv, prices_weekly.csv, headline.json, payees_weekly.csv}. Needs no keys; Blockscout
funding lookups are cached in STATE/o5/blockscout_links_v2.json.
X402_STRICT=1 (CI): a week whose funding lookups fail on more than 1% of addresses raises instead of publishing.
Usage: python3 scripts/x402_index/build.py [--max-lookups 300]
"""
import argparse, collections, csv, datetime as dt, glob, json, math, os, statistics, sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'o5'))
import bs, common
from x402_filter import sccs, UF, SETTLE

ROOT, OUT = common.ROOT, common.OUT
LINKS = os.path.join(common.STATE, 'o5', 'blockscout_links_v2.json')
WEEKCACHE = os.path.join(common.STATE, 'x402_index')
STRICT = os.environ.get('X402_STRICT') == '1'
CATS = common.CATEGORIES
STAGES = ['raw', 'd05', 'clean']


def links(addr, cache, dirs):
    """Same rule as scripts/o5/x402_filter.py links(), through the rate-limited client. Cache key = address."""
    if addr in cache: return cache[addr]
    out = []
    for f in dirs:
        d = bs.get(f'/api/v2/addresses/{addr}/token-transfers?type=ERC-20&filter={f}&token={common.USDC}')
        if 'items' not in d: raise RuntimeError(f'lookup failed for {addr} ({f})')
        for t in d['items']:
            if (t.get('method') or '') == SETTLE: continue
            cp = t['from'] if f == 'to' else t['to']
            if cp.get('is_contract') or cp.get('name') or cp.get('public_tags') or cp.get('metadata'): continue
            out.append(cp['hash'].lower())
    cache[addr] = sorted(set(out) - {addr})
    return cache[addr]


def week_cache(start):
    """Path of a week's filter cache: existing .json (private repo history) or .json.gz (new, and the public repo)."""
    return common.first(os.path.join(WEEKCACHE, f'week_{start}.json'), os.path.join(WEEKCACHE, f'week_{start}.json.gz'))


def complete_weeks():
    """Weeks with a finished raw collection or an already-built filter cache (the public repo keeps only the latter)."""
    out = set()
    for d in glob.glob(os.path.join(common.STATE, 'x402_week_20??-??-??')):
        if os.path.exists(os.path.join(d, 'COMPLETE')):
            out.add(dt.date.fromisoformat(os.path.basename(d)[-10:]))
    for p in glob.glob(os.path.join(WEEKCACHE, 'week_20??-??-??.json*')):
        out.add(dt.date.fromisoformat(os.path.basename(p)[5:15]))
    return sorted(out)


def load_week(start):
    rows, seen = [], set()
    for line in open(os.path.join(common.STATE, f'x402_week_{start}', 'txs.jsonl')):
        r = json.loads(line)
        if r['hash'] in seen: continue
        seen.add(r['hash'])
        if r.get('payer') and r.get('payee') and r.get('usdc_atomic') is not None:
            if r['payer'].lower() in common.OURS or r['payee'].lower() in common.OURS: continue  # our own test traffic
            rows.extend([(r['payer'].lower(), r['payee'].lower(), int(r['usdc_atomic']))] * int(r.get('n', 1)))  # n: grouped Dune rows
    return rows


def filter_week(start, max_lookups, coverage=0.9):
    """Per-payee aggregates by stage for one week; cached in STATE/x402_index/week_<start>.json[.gz]."""
    cp = week_cache(start)
    if os.path.exists(cp): return common.jload(cp)
    rows = load_week(start)
    n = len(rows)
    comp = sccs({(p, q) for p, q, _ in rows})
    c1 = [p == q or (p in comp and comp.get(p) == comp.get(q)) for p, q, _ in rows]
    cnt = collections.Counter()
    for p, q, _ in rows: cnt[p] += 1; cnt[q] += 1
    covered, acc = [], 0
    for addr, c in cnt.most_common():
        if acc >= coverage * 2 * n or len(covered) >= max_lookups: break
        covered.append(addr); acc += c
    cache = json.load(open(LINKS)) if os.path.exists(LINKS) else {}
    payer_set = {p for p, _, _ in rows}; payee_set = {q for _, q, _ in rows}
    uf, failed, new = UF(), 0, 0
    for i, addr in enumerate(covered):
        try:
            if addr not in cache: new += 1
            dirs = tuple(d for d, role in (('to', payer_set), ('from', payee_set)) if addr in role)
            for f in links(addr, cache, dirs): uf.u(addr, f)
        except Exception as e:
            failed += 1; print(start, 'lookup failed', addr, str(e)[:100], flush=True)
        if new and new % 25 == 0: json.dump(cache, open(LINKS, 'w'))
    json.dump(cache, open(LINKS, 'w'))
    if STRICT and failed > max(1, 0.01 * len(covered)):
        raise RuntimeError(f'{start}: {failed} of {len(covered)} funding lookups failed; not publishing this week')
    cov = set(covered)
    c2 = [(not x) and p in cov and q in cov and uf.f(p) == uf.f(q) for (p, q, _), x in zip(rows, c1)]
    d05 = [not (x or y) for x, y in zip(c1, c2)]
    payers_d05 = collections.defaultdict(set)
    for (p, q, _), k in zip(rows, d05):
        if k: payers_d05[q].add(p)
    clean = [k and len(payers_d05[q]) >= 2 for (p, q, _), k in zip(rows, d05)]
    agg = {}
    for stage, mask in (('raw', [True] * n), ('d05', d05), ('clean', clean)):
        per = {}
        for (p, q, a), m in zip(rows, mask):
            if not m: continue
            x = per.setdefault(q, {'n': 0, 'usd': 0.0, 'payers': set(), 'amts': []})
            x['n'] += 1; x['usd'] += a / 1e6; x['payers'].add(p)
            if stage == 'clean': x['amts'].append(a)
        agg[stage] = {q: {'n': x['n'], 'usd': round(x['usd'], 6), 'payers': sorted(x['payers']),
                          **({'median_atomic': statistics.median(x['amts'])} if stage == 'clean' else {})}
                      for q, x in per.items()}
    res = {'week': str(start), 'settlements': n, 'funding_lookups': len(covered), 'new_lookups': new,
           'lookup_failures': failed, 'endpoint_coverage': round(acc / (2 * n), 4) if n else None,
           'c1_payments': sum(c1), 'c2_payments': sum(c2), 'agg': agg}
    common.jdump(res, cp)
    return res


def fanout_flags(start, clean, top=20, sample=12, need=8):
    """Fan-out manufacture check (added after the 2026-09-30 dig: 0x8a12... had 874 one-time buyers, 10 of 12 sampled
    funded by 3 wallets). For the `top` cleaned sellers by USD whose buyers mostly pay once (payments/buyers <= 1.25,
    >= 20 buyers), sample `sample` buyers and read their newest 50 incoming non-settlement USDC transfers (same rule as
    links()). Shared funding alone is NOT manufacture: an operator running an agent fleet funds many wallets that buy
    for real (2026-09-30 check: most shared-funder sellers' buyers pay them 6-340 times and also buy from other sellers).
    Flag the seller only when untagged funders that each funded >= 2 sampled buyers together funded >= `need` of them
    AND either (a) circular: the seller's own sweeps go to one of those funders, or (b) isolated: >= 10 of the sampled
    buyers pay no other cleaned seller that week (throwaway wallets). Known case: 0x8a12... (2026-09-21, isolated).
    A lower bound like the rest of the manufacture filter. Cached per week."""
    cp = os.path.join(WEEKCACHE, f'fanout_{start}.json')
    if os.path.exists(cp): return json.load(open(cp))
    import random
    cache = json.load(open(LINKS)) if os.path.exists(LINKS) else {}
    cands = sorted(((q, x) for q, x in clean.items() if len(x['payers']) >= 20 and x['n'] / len(x['payers']) <= 1.25),
                   key=lambda t: -t[1]['usd'])[:top]
    out = {}
    for q, x in cands:
        buyers = sorted(x['payers']); random.Random(q).shuffle(buyers)
        funders = collections.Counter()
        for b in buyers[:sample]:
            try:
                for f in set(links(b, cache, ('to',))): funders[f] += 1
            except Exception as e:
                print(start, 'fanout lookup failed', b, str(e)[:80], flush=True)
        shared = {f: k for f, k in funders.items() if k >= 2}
        s = buyers[:sample]
        isolated = sum(1 for b in s if not any(b in y['payers'] for qq, y in clean.items() if qq != q))
        circular = None
        if sum(shared.values()) >= need:
            try:
                circular = bool(set(shared) & set(links(q, cache, ('from',))))
            except Exception as e:
                print(start, 'sweep lookup failed', q, str(e)[:80], flush=True)
        out[q] = {'buyers': len(x['payers']), 'usd': round(x['usd'], 2), 'sampled': len(s),
                  'shared_funders': dict(sorted(shared.items(), key=lambda t: -t[1])),
                  'buyers_with_shared_funder': sum(shared.values()), 'isolated_buyers': isolated, 'circular': circular,
                  'flagged': sum(shared.values()) >= need and (bool(circular) or isolated >= 10)}
        json.dump(cache, open(LINKS, 'w'))
    json.dump(out, open(cp, 'w'), indent=1)
    return out


def categories(review=True):
    model = {r['payee']: r['category'] for r in csv.DictReader(open(os.path.join(OUT, 'payee_classes.csv')))} \
        if os.path.exists(os.path.join(OUT, 'payee_classes.csv')) else {}
    hand = common.hand_classes()
    cat, src, conflicts = {}, {}, 0
    for p in set(model) | set(hand):
        m = model.get(p)
        if p in hand:
            s, h = hand[p]
            if s == 'o10' or h in common.HAND_MAP:
                cat[p] = common.HAND_MAP.get(h, h); src[p] = f'hand_{s}'
            else:  # ORDER_002 'not content/data': keep the model's split unless it contradicts the hand label
                if m in ('content', 'data') or m is None:
                    conflicts += m is not None
                    cat[p] = 'other'
                else:
                    cat[p] = m
                src[p] = 'hand_o2+model'
        else:
            cat[p], src[p] = m, 'model'
    rp = os.path.join(OUT, 'unlisted_review.csv')
    if review and os.path.exists(rp):  # unlisted sellers reviewed by scripts/x402_index/review_unlisted.py
        for r in csv.DictReader(open(rp)):
            if r['category'] and not cat.get(r['payee']):
                cat[r['payee']], src[r['payee']] = r['category'], 'unlisted_review'
    return cat, src, conflicts


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def pct(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q; f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def jevons_chain(obs):
    """obs: {week: {key: price}} -> {week: (index, basket_n, entered, exited)} with the first week = 100."""
    weeks = sorted(obs); out = {}
    idx = 100.0
    for i, w in enumerate(weeks):
        if i == 0:
            out[w] = (idx, len(obs[w]), len(obs[w]), 0); continue
        prev = obs[weeks[i - 1]]; cur = obs[w]
        both = [k for k in cur if k in prev and prev[k] > 0 and cur[k] > 0]
        if both:
            idx *= math.exp(sum(math.log(cur[k] / prev[k]) for k in both) / len(both))
        out[w] = (idx if both else None, len(both), len(set(cur) - set(prev)), len(set(prev) - set(cur)))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--max-lookups', type=int, default=300)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    cat, src, conflicts = categories()
    weeks = complete_weeks()
    print('complete weeks:', [str(w) for w in weeks], flush=True)
    W = {w: filter_week(w, a.max_lookups) for w in weeks}
    FAN = {}
    for w in weeks:  # fan-out manufacture: move flagged sellers out of 'clean'
        FAN[w] = fanout_flags(w, W[w]['agg']['clean'])
        for q, f in FAN[w].items():
            if f['flagged']: W[w]['agg']['clean'].pop(q, None)

    # ---- weekly.csv: stage x category
    wrows, prow = [], []
    for w in weeks:
        r = W[w]
        for stage in STAGES:
            by = {c: {'payments': 0, 'usd': 0.0, 'payees': 0, 'payers': set()} for c in CATS + ['all']}
            for q, x in r['agg'][stage].items():
                c = cat.get(q) or 'unclassed'
                for k in (c, 'all'):
                    by[k]['payments'] += x['n']; by[k]['usd'] += x['usd']; by[k]['payees'] += 1; by[k]['payers'].update(x['payers'])
            for c in CATS + ['all']:
                wrows.append({'week_start': w, 'week_end': w + dt.timedelta(days=6), 'stage': stage, 'category': c,
                              'payments': by[c]['payments'], 'usd': round(by[c]['usd'], 2), 'payees': by[c]['payees'],
                              'payers': len(by[c]['payers'])})
        for q, x in r['agg']['clean'].items():
            prow.append({'week_start': w, 'payee': q, 'category': cat.get(q) or 'unclassed', 'category_source': src.get(q, 'none'),
                         'payments': x['n'], 'usd': round(x['usd'], 2), 'payers': len(x['payers']),
                         'median_payment_usd': x['median_atomic'] / 1e6})
    with open(os.path.join(OUT, 'weekly.csv'), 'w', newline='') as f:
        w_ = csv.DictWriter(f, fieldnames=list(wrows[0])); w_.writeheader(); w_.writerows(wrows)
    with open(os.path.join(OUT, 'payees_weekly.csv'), 'w', newline='') as f:
        w_ = csv.DictWriter(f, fieldnames=list(prow[0])); w_.writeheader()
        w_.writerows(sorted(prow, key=lambda x: (x['week_start'], -x['usd'])))

    # ---- prices_weekly.csv
    prices = []
    # posted (Bazaar snapshots)
    posted = {}  # week -> {(resource, payTo): price}
    snapdate = {}
    for d, p in common.bazaar_snapshots():
        wk = monday(dt.date.fromisoformat(d))
        obs = collections.defaultdict(list)
        for it in common.jload(p):
            for acc in it.get('accepts') or []:
                pr = common.base_usdc_price(acc)
                if pr is not None and acc.get('payTo'):
                    obs[(it.get('resource', ''), acc['payTo'].lower())].append(pr)
        posted[wk] = {k: statistics.median(v) for k, v in obs.items()}  # a later snapshot in the same week replaces it
        snapdate[wk] = d
    for c in CATS + ['all']:
        sub = {wk: {k: v for k, v in o.items() if c == 'all' or (cat.get(k[1]) or 'unclassed') == c} for wk, o in posted.items()}
        ch = jevons_chain(sub)
        for wk in sorted(sub):
            ps = list(sub[wk].values())
            prices.append({'week_start': wk, 'measure': 'posted', 'source': f'CDP Bazaar snapshot {snapdate[wk]}', 'category': c,
                           'items': len(ps), 'median_usd': pct(ps, .5), 'p25_usd': pct(ps, .25), 'p75_usd': pct(ps, .75),
                           'index_jevons': round(ch[wk][0], 3) if ch[wk][0] is not None else '', 'basket_items': ch[wk][1],
                           'entered': ch[wk][2], 'exited': ch[wk][3]})
    # transacted (clean payments on chain)
    for c in CATS + ['all']:
        sub = {w: {q: x['median_atomic'] / 1e6 for q, x in W[w]['agg']['clean'].items()
                   if c == 'all' or (cat.get(q) or 'unclassed') == c} for w in weeks}
        ch = jevons_chain(sub)
        for w in weeks:
            ps = list(sub[w].values())
            prices.append({'week_start': w, 'measure': 'transacted', 'source': 'Base chain, clean payments, payee median',
                           'category': c, 'items': len(ps), 'median_usd': pct(ps, .5), 'p25_usd': pct(ps, .25),
                           'p75_usd': pct(ps, .75), 'index_jevons': round(ch[w][0], 3) if ch[w][0] is not None else '',
                           'basket_items': ch[w][1], 'entered': ch[w][2], 'exited': ch[w][3]})
    for r in prices:
        for k in ('median_usd', 'p25_usd', 'p75_usd'):
            r[k] = round(r[k], 6) if r[k] is not None else ''
    with open(os.path.join(OUT, 'prices_weekly.csv'), 'w', newline='') as f:
        w_ = csv.DictWriter(f, fieldnames=list(prices[0])); w_.writeheader(); w_.writerows(prices)

    # ---- headline + tripwire
    get = lambda w, st, c, k='usd': next(r[k] for r in wrows if r['week_start'] == w and r['stage'] == st and r['category'] == c)
    last = weeks[-1]
    cd = {w: get(w, 'clean', 'content') + get(w, 'clean', 'data') for w in weeks}
    four = weeks[-5] if len(weeks) >= 5 and (last - weeks[-5]).days == 28 else None
    slope = None
    recent = [w for w in weeks if (last - w).days <= 28]
    if len(recent) >= 3 and all(cd[w] > 0 for w in recent):
        xs = [(w - recent[0]).days for w in recent]; ys = [math.log(cd[w]) for w in recent]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    head = {
        'latest_week': f'{last}..{last + dt.timedelta(days=6)}', 'weeks_available': [str(w) for w in weeks],
        'raw_usd': get(last, 'raw', 'all'), 'raw_payments': get(last, 'raw', 'all', 'payments'),
        'd05_usd': get(last, 'd05', 'all'), 'clean_usd': get(last, 'clean', 'all'),
        'clean_payments': get(last, 'clean', 'all', 'payments'), 'clean_payees': get(last, 'clean', 'all', 'payees'),
        'clean_by_category_usd': {c: get(last, 'clean', c) for c in CATS},
        'tripwire_content_plus_data_clean_usd': round(cd[last], 2),
        'tripwire_4week_growth': round(cd[last] / cd[four] - 1, 4) if four and cd[four] else None,
        'tripwire_4week_base_week': str(four) if four else None,
        'tripwire_loglinear_monthly_growth_last_5_weeks': round(math.exp(slope * 30.44) - 1, 4) if slope is not None else None,
        'content_plus_data_clean_usd_by_week': {str(w): round(v, 2) for w, v in cd.items()},
        'category_sources': dict(sorted(collections.Counter(src.values()).items())), 'hand_o2_model_conflicts_set_to_other': conflicts,
        'fanout_flagged': {str(w): {q: f for q, f in FAN[w].items() if f['flagged']} for w in weeks},
        'fanout_checked': {str(w): len(FAN[w]) for w in weeks},
        'excluded_own_addresses': sorted(common.OURS),
        'filter': {str(w): {k: W[w][k] for k in ('settlements', 'funding_lookups', 'new_lookups', 'lookup_failures',
                                                  'endpoint_coverage', 'c1_payments', 'c2_payments')} for w in weeks},
    }
    json.dump(head, open(os.path.join(OUT, 'headline.json'), 'w'), indent=1, default=str)
    print(json.dumps({k: v for k, v in head.items() if k != 'filter'}, indent=1, default=str))


if __name__ == '__main__':
    main()
