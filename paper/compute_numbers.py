#!/usr/bin/env python3
"""Pre-render (compute_numbers.py) for paper/x402_measured.qmd: every number and figure in the paper, computed from data/x402_index.

Writes paper/_numbers.yml (read by the paper as metadata; cited in the text as {{< meta n.KEY >}}) and paper/fig/*.svg.
Stdlib only. The paper covers complete weeks from START to END; later weeks in the data are ignored, so the paper does
not drift when the weekly index updates."""
import collections, csv, html, json, math, os, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data', 'x402_index')
FIG = os.path.join(HERE, 'fig')
START, END = '2026-08-01', '2026-09-21'  # first and last week_start (Mondays) in scope
CATS = ['content', 'data', 'search', 'compute', 'other', 'large_ticket', 'unclassed']
LABEL = {'content': 'Content', 'data': 'Data', 'search': 'Search', 'compute': 'Compute & tools', 'other': 'Other',
         'large_ticket': 'Large ticket (unidentified)', 'unclassed': 'Unclassed'}
SHORT = {**LABEL, 'compute': 'Compute', 'large_ticket': 'Large ticket'}
COL = {'content': '#2a78d6', 'data': '#eb6834', 'search': '#1baf7a', 'compute': '#eda100', 'other': '#e87ba4',
       'large_ticket': '#008300', 'unclassed': '#a9aea9', 'raw': '#a9aea9', 'd05': '#eb6834', 'clean': '#2a78d6'}
INK, GRID, FONT = '#121614', '#dde1dd', 'Helvetica, Arial, sans-serif'


def rd(path):
    return list(csv.DictReader(open(os.path.join(DATA, path))))


def usd(x):
    return f'${x:,.0f}' if abs(x) >= 100 else f'${x:,.2f}'


def pct(x, d=1):
    return f'{100 * x:.{d}f}%'


def price(x):
    return f'${x:.4f}'.rstrip('0').rstrip('.') if x < 1 else f'${x:,.2f}'


def wk(w):
    import datetime as dt
    return dt.date.fromisoformat(w).strftime('%-d %b')


# ---------- SVG helpers (inline colours so figures survive into PDF) ----------
def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{FONT}" '
            f'font-size="11" role="img"><title>{title}</title><rect width="{w}" height="{h}" fill="#ffffff"/>{body}</svg>')


def nice(v):
    if v <= 0: return 1
    e = 10 ** math.floor(math.log10(v)); m = v / e
    return (1 if m <= 1 else 2 if m <= 2 else 2.5 if m <= 2.5 else 5 if m <= 5 else 10) * e


def yaxis(L, R, T, H, ymax, fmt, W):
    out = []
    for i in range(5):
        v = ymax * i / 4; y = T + (H - T) * (1 - v / ymax)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>'
                   f'<text x="{L - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{INK}">{fmt(v)}</text>')
    return ''.join(out)


def legend(items, x, y):
    out, cx = [], x
    for key, lab in items:
        out.append(f'<rect x="{cx}" y="{y - 9}" width="10" height="10" rx="2" fill="{COL[key]}"/>'
                   f'<text x="{cx + 14}" y="{y}" fill="{INK}">{html.escape(lab)}</text>')
        cx += 22 + 6.2 * len(lab)
    return ''.join(out)


def fig_stages(weeks, V):
    W, Hh, L, R, T, B = 640, 280, 70, 12, 30, 250
    ymax = nice(max(V(w, 'raw', 'all') for w in weeks) / 1000)
    pw = (W - L - R) / len(weeks); bw = pw * 0.22
    body = [yaxis(L, R, T, B, ymax, lambda v: f'${v:,.0f}k', W)]
    for j, w in enumerate(weeks):
        for i, st in enumerate(('raw', 'd05', 'clean')):
            v = V(w, st, 'all') / 1000; x = L + pw * j + pw * 0.14 + i * (bw + 2); y = T + (B - T) * (1 - v / ymax)
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{B - y:.1f}" rx="1.5" fill="{COL[st]}"/>')
        body.append(f'<text x="{L + pw * j + pw / 2:.1f}" y="{B + 16}" text-anchor="middle" fill="{INK}">{wk(w)}</text>')
    body.append(legend([('raw', 'Raw settlements'), ('d05', 'After manufacture filter'), ('clean', 'Demand-cleaned')], L, 16))
    return svg(W, Hh, ''.join(body), 'Weekly USDC settled before and after each filter')


def fig_categories(weeks, V):
    W, Hh, L, R, T, B = 640, 290, 70, 12, 44, 260
    tot = {w: sum(V(w, 'clean', c) for c in CATS) for w in weeks}
    ymax = nice(max(tot.values()) / 1000)
    pw = (W - L - R) / len(weeks); bw = min(60, pw * 0.6)
    body = [yaxis(L, R, T, B, ymax, lambda v: f'${v:,.0f}k', W)]
    for j, w in enumerate(weeks):
        base = 0; x = L + pw * j + (pw - bw) / 2
        for c in CATS:
            v = V(w, 'clean', c) / 1000
            if v <= 0: continue
            y0 = T + (B - T) * (1 - base / ymax); y1 = T + (B - T) * (1 - (base + v) / ymax)
            body.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bw:.1f}" height="{max(0, y0 - y1 - 1):.1f}" fill="{COL[c]}"/>')
            base += v
        body.append(f'<text x="{x + bw / 2:.1f}" y="{B + 16}" text-anchor="middle" fill="{INK}">{wk(w)}</text>')
    body.append(legend([(c, LABEL[c]) for c in CATS[:4]], L, 14))
    body.append(legend([(c, LABEL[c]) for c in CATS[4:]], L, 30))
    return svg(W, Hh, ''.join(body), 'Demand-cleaned USD by seller category per week')


def fig_concentration(shares_by_week):
    W, Hh, L, R, T, B = 640, 270, 56, 110, 16, 236
    N = 30
    body = [yaxis(L, R, T, B, 1.0, lambda v: f'{v * 100:.0f}%', W)]
    for x in (1, 5, 10, 15, 20, 25, 30):
        px = L + (W - L - R) * (x - 1) / (N - 1)
        body.append(f'<text x="{px:.1f}" y="{B + 16}" text-anchor="middle" fill="{INK}">{x}</text>')
    body.append(f'<text x="{L + (W - L - R) / 2:.0f}" y="{Hh - 2}" text-anchor="middle" fill="{INK}">Top N sellers by demand-cleaned USD</text>')
    greys = ['#c9cec9', '#b4bab5', '#9aa19c', '#7c847e', '#5f6862', '#444c47', '#2a78d6']
    weeks = sorted(shares_by_week)
    for i, w in enumerate(weeks):
        cum, acc = [], 0
        for s in shares_by_week[w][:N]:
            acc += s; cum.append(acc)
        pts = ' '.join(f'{L + (W - L - R) * k / (N - 1):.1f},{T + (B - T) * (1 - v):.1f}' for k, v in enumerate(cum))
        colr = '#2a78d6' if w == weeks[-1] else greys[i % (len(greys) - 1)]
        body.append(f'<polyline points="{pts}" fill="none" stroke="{colr}" stroke-width="{2.4 if w == weeks[-1] else 1.4}"/>')
        if w == weeks[-1]:
            body.append(f'<text x="{W - R + 6}" y="{T + (B - T) * (1 - cum[-1]) + 4:.1f}" fill="{colr}">{wk(w)}</text>')
    body.append(f'<text x="{W - R + 6}" y="{T + 40}" fill="#7c847e">grey: earlier</text><text x="{W - R + 6}" y="{T + 54}" fill="#7c847e">weeks</text>')
    return svg(W, Hh, ''.join(body), 'Cumulative share of demand-cleaned USD held by the top N sellers, per week')


def fig_prices(rows):
    W, Hh, L, R, T = 640, 40 + 30 * len(rows), 170, 20, 30
    lo, hi = math.log10(0.0005), math.log10(20)
    X = lambda v: L + (W - L - R) * (math.log10(max(v, 0.0005)) - lo) / (hi - lo)
    body = []
    for v in (0.001, 0.01, 0.1, 1, 10):
        body.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T - 8}" y2="{Hh - 16}" stroke="{GRID}"/>'
                    f'<text x="{X(v):.1f}" y="{Hh - 4}" text-anchor="middle" fill="{INK}">{price(v)}</text>')
    for i, (c, p25, med, p75, tx) in enumerate(rows):
        y = T + 30 * i + 8
        body.append(f'<text x="{L - 8}" y="{y + 4}" text-anchor="end" fill="{INK}">{html.escape(LABEL[c])}</text>')
        if med is not None:
            body.append(f'<line x1="{X(p25):.1f}" x2="{X(p75):.1f}" y1="{y}" y2="{y}" stroke="{COL[c]}" stroke-width="6" stroke-linecap="round" opacity="0.45"/>'
                        f'<circle cx="{X(med):.1f}" cy="{y}" r="4.5" fill="{COL[c]}"/>')
        if tx is not None:
            body.append(f'<path d="M{X(tx) - 5:.1f},{y - 5} L{X(tx) + 5:.1f},{y + 5} M{X(tx) - 5:.1f},{y + 5} L{X(tx) + 5:.1f},{y - 5}" stroke="{INK}" stroke-width="1.6"/>')
    body.append(f'<circle cx="{L}" cy="12" r="4.5" fill="#777"/><text x="{L + 8}" y="16" fill="{INK}">posted median (bar: IQR), Bazaar</text>'
                f'<path d="M{L + 232},7 L{L + 242},17 M{L + 232},17 L{L + 242},7" stroke="{INK}" stroke-width="1.6"/>'
                f'<text x="{L + 248}" y="16" fill="{INK}">median of sellers&#39; median paid, on chain</text>')
    return svg(W, Hh, ''.join(body), 'Posted and paid price per call by category, log scale')


def main():
    weekly = rd('weekly.csv'); prices = rd('prices_weekly.csv'); payees = rd('payees_weekly.csv')
    head = json.load(open(os.path.join(DATA, 'headline.json')))
    weeks = sorted({r['week_start'] for r in weekly if START <= r['week_start'] <= END})
    last = weeks[-1]
    idx = {(r['week_start'], r['stage'], r['category']): r for r in weekly}
    V = lambda w, st, c, k='usd': float(idx[(w, st, c)][k])
    n = {'weeks': len(weeks), 'first_week': wk(weeks[0]) + ' ' + weeks[0][:4], 'last_week': wk(last) + ' ' + last[:4],
         'last_week_end': __import__('datetime').date.fromisoformat(last).__add__(__import__('datetime').timedelta(days=6)).strftime('%-d %b %Y')}
    # stages
    raw_t = sum(V(w, 'raw', 'all') for w in weeks); d05_t = sum(V(w, 'd05', 'all') for w in weeks)
    cl_t = sum(V(w, 'clean', 'all') for w in weeks)
    n.update({'raw_total': usd(raw_t), 'd05_total': usd(d05_t), 'clean_total': usd(cl_t), 'clean_share_total': pct(cl_t / raw_t),
              'raw_pay_total': f"{sum(V(w, 'raw', 'all', 'payments') for w in weeks):,.0f}",
              'clean_pay_total': f"{sum(V(w, 'clean', 'all', 'payments') for w in weeks):,.0f}",
              'raw_last': usd(V(last, 'raw', 'all')), 'd05_last': usd(V(last, 'd05', 'all')), 'clean_last': usd(V(last, 'clean', 'all')),
              'clean_share_last': pct(V(last, 'clean', 'all') / V(last, 'raw', 'all')),
              'raw_pay_last': f"{V(last, 'raw', 'all', 'payments'):,.0f}", 'clean_pay_last': f"{V(last, 'clean', 'all', 'payments'):,.0f}",
              'clean_sellers_last': f"{V(last, 'clean', 'all', 'payees'):,.0f}", 'clean_buyers_last': f"{V(last, 'clean', 'all', 'payers'):,.0f}",
              'raw_sellers_last': f"{V(last, 'raw', 'all', 'payees'):,.0f}", 'raw_buyers_last': f"{V(last, 'raw', 'all', 'payers'):,.0f}",
              'clean_min_week': usd(min(V(w, 'clean', 'all') for w in weeks)), 'clean_max_week': usd(max(V(w, 'clean', 'all') for w in weeks))})
    small = sum(1 for w in weeks if 1 - V(w, 'd05', 'all') / V(w, 'raw', 'all') < 0.10)
    n.update({'mf_small_weeks': f'{small} of {len(weeks)}', 'dust_removed_last': pct(1 - V(last, 'clean', 'all') / V(last, 'd05', 'all'), 0),
              'mf_removed_max': pct(max(1 - V(w, 'd05', 'all') / V(w, 'raw', 'all') for w in weeks), 0)})
    f = head['filter']
    c1 = sum(f[w]['c1_payments'] for w in weeks if w in f); c2 = sum(f[w]['c2_payments'] for w in weeks if w in f)
    st = sum(f[w]['settlements'] for w in weeks if w in f)
    n.update({'c1_share': pct(c1 / st), 'c2_share': pct(c2 / st), 'settlements_total': f'{st:,}',
              'fanout_flagged': str(len({q for w in weeks for q in head['fanout_flagged'].get(w, {})})),
              'lookups_per_week': f"{statistics.median(f[w]['funding_lookups'] for w in weeks if w in f):.0f}"})
    # categories
    for c in CATS:
        n[f'cat_{c}_last'] = usd(V(last, 'clean', c)); n[f'cat_{c}_share_last'] = pct(V(last, 'clean', c) / V(last, 'clean', 'all'))
        tot = sum(V(w, 'clean', c) for w in weeks)
        n[f'cat_{c}_total'] = usd(tot); n[f'cat_{c}_share_total'] = pct(tot / cl_t)
        n[f'cat_{c}_sellers_last'] = f"{V(last, 'clean', c, 'payees'):,.0f}"
        n[f'cat_{c}_pay_last'] = f"{V(last, 'clean', c, 'payments'):,.0f}"
    cd = {w: V(w, 'clean', 'content') + V(w, 'clean', 'data') for w in weeks}
    n.update({'cd_last': usd(cd[last]), 'cd_first': usd(cd[weeks[0]]), 'cd_change': pct(cd[last] / cd[weeks[0]] - 1, 0)})
    # concentration
    shares = {}
    conc = {}
    for w in weeks:
        us = sorted((float(r['usd']) for r in payees if r['week_start'] == w), reverse=True)
        t = sum(us); sh = [u / t for u in us]; shares[w] = sh
        cum, n50, n80 = 0, None, None
        for i, s in enumerate(sh, 1):
            cum += s
            if n50 is None and cum >= .5: n50 = i
            if n80 is None and cum >= .8: n80 = i
        conc[w] = {'sellers': len(us), 'top1': sh[0], 'top10': sum(sh[:10]), 'hhi': sum(s * s for s in sh), 'n50': n50, 'n80': n80}
    cl = conc[last]
    n.update({'top1_last': pct(cl['top1']), 'top10_last': pct(cl['top10']), 'hhi_last': f"{cl['hhi'] * 10000:,.0f}",
              'n50_last': str(cl['n50']), 'n80_last': str(cl['n80']),
              'top10_min': pct(min(c['top10'] for c in conc.values())), 'top10_max': pct(max(c['top10'] for c in conc.values()))})
    lp = [r for r in payees if r['week_start'] == last]
    lp.sort(key=lambda r: -float(r['usd']))
    top1 = lp[0]
    n.update({'top1_category': LABEL[top1['category']].lower(), 'top1_buyers': top1['payers'], 'top1_payments': top1['payments'],
              'top1_median': price(float(top1['median_payment_usd']))})
    buyers_per = [int(r['payers']) for r in lp]
    n.update({'sellers_2to4_buyers': pct(sum(1 for b in buyers_per if b < 5) / len(buyers_per), 0),
              'sellers_100plus_buyers': str(sum(1 for b in buyers_per if b >= 100))})
    # prices
    P = {(r['week_start'], r['measure'], r['category']): r for r in prices}
    post_week = max(w for (w, m, c) in P if m == 'posted' and w <= END)  # snapshot inside the paper's window
    prow = []
    for c in CATS[:5]:
        po = P.get((post_week, 'posted', c)); tx = P.get((last, 'transacted', c))
        g = lambda r, k: float(r[k]) if r and r.get(k) not in (None, '') else None
        prow.append((c, g(po, 'p25_usd'), g(po, 'median_usd'), g(po, 'p75_usd'), g(tx, 'median_usd')))
        n[f'posted_{c}'] = price(g(po, 'median_usd')) if po else '–'
        n[f'paid_{c}'] = price(g(tx, 'median_usd')) if tx and g(tx, 'median_usd') is not None else '–'
        n[f'listed_{c}'] = f"{int(po['items']):,}" if po else '0'
    pa = P[(post_week, 'posted', 'all')]
    n.update({'posted_all_median': price(float(pa['median_usd'])), 'posted_all_p25': price(float(pa['p25_usd'])),
              'posted_all_p75': price(float(pa['p75_usd'])), 'listed_all': f"{int(pa['items']):,}",
              'posted_snapshot': P[(post_week, 'posted', 'all')]['source'].split()[-1]})
    meds = [float(r['median_payment_usd']) for r in lp]
    n.update({'sellers_med_below_1c': pct(sum(1 for m in meds if m < 0.01) / len(meds), 0),
              'sellers_med_above_1usd': pct(sum(1 for m in meds if m >= 1) / len(meds), 0)})
    txi = [(w, P.get((w, 'transacted', 'all'), {}).get('index_jevons')) for w in weeks]
    txi = [(w, float(v)) for w, v in txi if v not in (None, '')]
    n['tx_index_last'] = f'{txi[-1][1]:.1f}' if txi else '–'
    # classifier accuracy, from the public hand labels
    model = {r['payee']: r['category'] for r in rd('payee_classes.csv')}
    o2 = list(csv.DictReader(open(os.path.join(DATA, '..', 'o2_payees_reviewed.csv'))))
    hm = {'publisher content': 'content', 'other content': 'content', 'market/crypto data': 'data', 'other data': 'data'}
    coarse = lambda c: c if c in ('content', 'data') else 'not'
    pairs = [(coarse(hm.get(r['hand_class'], 'not')), coarse(model[r['payee'].lower()])) for r in o2 if r['payee'].lower() in model]
    hc = rd('handcheck_30.csv')
    ca = rd('content_audit.csv')
    n.update({'clf_o2_n': str(len(pairs)), 'clf_o2_acc': pct(sum(a == b for a, b in pairs) / len(pairs), 1),
              'clf_blind_n': str(len(hc)), 'clf_blind_exact': str(sum(r['agree'] == 'True' for r in hc)),
              'clf_blind_coarse': str(sum(coarse(r['model_category']) == coarse(r['hand_category']) for r in hc)),
              'content_audit_n': str(len(ca)), 'content_audit_wrong': str(sum(r['agree'] == 'False' for r in ca))})
    # write
    os.makedirs(FIG, exist_ok=True)
    open(os.path.join(FIG, 'stages.svg'), 'w').write(fig_stages(weeks, V))
    open(os.path.join(FIG, 'categories.svg'), 'w').write(fig_categories(weeks, V))
    open(os.path.join(FIG, 'concentration.svg'), 'w').write(fig_concentration(shares))
    open(os.path.join(FIG, 'prices.svg'), 'w').write(fig_prices(prow))
    tbl = ['| Week of | Raw | After manufacture filter | Demand-cleaned | Clean payments | Sellers | Buyers | Top-10 share |', '|---|--:|--:|--:|--:|--:|--:|--:|']
    for w in weeks:
        tbl.append(f"| {wk(w)} | {usd(V(w, 'raw', 'all'))} | {usd(V(w, 'd05', 'all'))} | {usd(V(w, 'clean', 'all'))} | "
                   f"{V(w, 'clean', 'all', 'payments'):,.0f} | {V(w, 'clean', 'all', 'payees'):,.0f} | {V(w, 'clean', 'all', 'payers'):,.0f} | {pct(conc[w]['top10'], 0)} |")
    open(os.path.join(HERE, '_weeks_table.md'), 'w').write('\n'.join(tbl) + '\n')
    ctbl = ['| Category | Clean USD | Share | Sellers | Payments | Posted | Paid |', '|---|--:|--:|--:|--:|--:|--:|']
    for c in CATS:
        ctbl.append(f"| {SHORT[c]} | {n[f'cat_{c}_last']} | {n[f'cat_{c}_share_last']} | {n[f'cat_{c}_sellers_last']} | {n[f'cat_{c}_pay_last']} | "
                    f"{n.get(f'posted_{c}', '–')} | {n.get(f'paid_{c}', '–')} |")
    open(os.path.join(HERE, '_cat_table.md'), 'w').write('\n'.join(ctbl) + '\n')
    with open(os.path.join(HERE, '_numbers.yml'), 'w') as fh:
        fh.write('# generated by compute_numbers.py; do not edit\nn:\n')
        for k, v in n.items(): fh.write(f'  {k}: "{v}"\n')
    print(f'paper numbers: {len(n)} values, weeks {weeks[0]}..{last}; figures in {FIG}')


if __name__ == '__main__':
    main()
