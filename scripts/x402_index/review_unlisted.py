#!/usr/bin/env python3
"""ORDER_010 (Wes, follow-up): review the top unclassed (unlisted) cleaned sellers by USD, week by week, until
unclassed is < 25% of the week's clean USD, or until the next seller has no evidence that supports a label.

Unlisted sellers have no Bazaar or x402scan listing, no Blockscout name or tag, and their buyers pay no other seller,
so what they sell cannot be read from public data. The only label the evidence supports is:
  large_ticket (UNIDENTIFIED): the seller's median cleaned payment is above the 99th percentile of posted
  per-call prices in the latest Bazaar snapshot (exact-scheme Base USDC). This is a relabel, not an identification:
  chain evidence (2026-09-30) shows such sellers include B2B-sized transfers and consumer-app purchases that may be
  compute jobs. It never assigns content or data, so the tripwire cannot move.
Sellers below that line stay 'unclassed'. Every reviewed seller is written with its evidence (payers, ticket tiers,
where its real USDC is swept) to data/x402_index/unlisted_review.csv, which build.py applies.
Needs week caches from build.py. Usage: python3 scripts/x402_index/review_unlisted.py [--target 0.25]
"""
import argparse, collections, csv, json, os, statistics, sys

sys.path.insert(0, os.path.dirname(__file__))
import bs, common

REVIEW = os.path.join(common.OUT, 'unlisted_review.csv')
FIELDS = ['payee', 'category', 'basis', 'weeks_reviewed', 'median_payment_usd_latest', 'ticket_tiers', 'payers_latest',
          'sweep_summary', 'threshold_usd']


def threshold():
    d, p = common.bazaar_snapshots()[-1]
    ps = sorted(x for it in common.jload(p) for a in it.get('accepts') or [] if (x := common.base_usdc_price(a)) is not None)
    return ps[int(0.99 * (len(ps) - 1))], d


def sweeps(addr):
    """Real-USDC outgoing transfers (newest 50): top destinations with labels. Look-alike tokens are ignored."""
    try:
        d = bs.get(f'/api/v2/addresses/{addr}/token-transfers?type=ERC-20&filter=from&token={common.USDC}', tries=3)
    except Exception as e:  # busy addresses can time out on Blockscout; the sweep summary is evidence only
        return f'lookup failed ({type(e).__name__})'
    usd = collections.Counter(); lab = {}
    for t in d.get('items', []):
        v = int(t['total']['value']) / 1e6
        if v <= 0: continue  # zero-value transfers are address-poisoning spam
        cp = t['to']; k = cp['hash'].lower()
        usd[k] += v
        lab[k] = cp.get('name') or ','.join(x.get('label', '') for x in (cp.get('public_tags') or [])) or ('contract' if cp.get('is_contract') else 'EOA')
    return '; '.join(f'{k[:10]}… ({lab[k]}) ${v:,.0f}' for k, v in usd.most_common(3)) or 'no outgoing USDC in newest 50'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--target', type=float, default=0.25)
    a = ap.parse_args()
    thr, snap = threshold()
    rows = {r['payee']: r for r in csv.DictReader(open(REVIEW))} if os.path.exists(REVIEW) else {}
    import build
    cat, _, _ = build.categories(review=False)  # listing/hand/model labels only (review rows are applied separately)
    report = []
    for w in build.complete_weeks():
        agg = dict(build.filter_week(w, 300)['agg']['clean'])
        for q, f in build.fanout_flags(w, agg).items():
            if f['flagged']: agg.pop(q, None)
        total = sum(x['usd'] for x in agg.values())
        uncl = sorted(((q, x) for q, x in agg.items() if not cat.get(q)), key=lambda t: -t[1]['usd'])
        remaining = sum(x['usd'] for _, x in uncl)
        for q, x in uncl:
            if remaining < a.target * total: break
            med = x['median_atomic'] / 1e6
            if q in rows:
                r = rows[q]
                if str(w) not in r['weeks_reviewed'].split(): r['weeks_reviewed'] += f' {w}'
            else:
                r = rows[q] = {'payee': q, 'weeks_reviewed': str(w), 'sweep_summary': sweeps(q)}
            r.update({'median_payment_usd_latest': round(med, 6), 'payers_latest': len(x['payers']),
                      'threshold_usd': f'{thr} (p99 posted, Bazaar {snap})'})
            if r.get('category') == 'large_ticket' or med > thr:
                r['category'] = 'large_ticket'; r['basis'] = 'UNIDENTIFIED large ticket: median payment above p99 of posted per-call prices'
                remaining -= x['usd']
            else:
                r.setdefault('category', ''); r['basis'] = 'no supporting evidence: median payment within per-call range; left unclassed'
        report.append((str(w), round(total, 2), round(remaining, 2), round(remaining / total, 4) if total else None))
    # ticket tiers from the latest week each seller was reviewed
    for q, r in rows.items():
        wk = r['weeks_reviewed'].split()[-1]
        raw = os.path.join(common.STATE, f'x402_week_{wk}', 'txs.jsonl')
        if not os.path.exists(raw): continue  # raw week not kept here (public repo): keep the recorded tiers
        amts = collections.Counter()
        for line in open(raw):
            if q in line:
                t = json.loads(line)
                if t.get('payee') == q: amts[t['usdc_atomic'] / 1e6] += 1
        r['ticket_tiers'] = ', '.join(f'${k:g}×{v}' for k, v in amts.most_common(4))
    with open(REVIEW, 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS); wr.writeheader()
        for q in sorted(rows, key=lambda q: -float(rows[q]['median_payment_usd_latest'] or 0)): wr.writerow({k: rows[q].get(k, '') for k in FIELDS})
    print('week, clean USD, unclassed USD after review, share')
    for r in report: print(*r, sep='\t')


if __name__ == '__main__':
    main()
