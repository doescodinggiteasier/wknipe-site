"""x402 on Solana (/x402/solana/), from the Dune exports built by scripts/dune/solana.py. Written to _gen/solana.md."""
import datetime as _dt, json, os, shutil

from _wk import *  # noqa: F401,F403

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
GEN = os.path.join(HERE, '_gen')
QUERIES = 'https://github.com/doescodinggiteasier/wknipe-site/blob/main/analytics/dune/'


def solana_page(d):
    p = os.path.join(ROOT, 'data', 'x402_solana', 'solana.json')
    if not os.path.exists(p):
        open(os.path.join(GEN, 'solana.md'), 'w').write(md('<p>Solana data not built yet.</p>')); return
    S = json.load(open(p))
    dst = os.path.join(HERE, 'x402', 'data'); os.makedirs(dst, exist_ok=True)
    json.dump({'history': S['history']}, open(os.path.join(dst, 'solana_history.json'), 'w'))
    json.dump({'fac': [{'label': x['facilitator'], 'value': x['share']} for x in S['facilitators']]}, open(os.path.join(dst, 'solana_charts.json'), 'w'))
    for n in ('weekly.csv', 'weekly_by_facilitator.csv'):
        shutil.copy(os.path.join(ROOT, 'data', 'x402_solana', n), os.path.join(dst, 'solana_' + n))
    lw, wh = S['week'], S['whale']
    through = '2026-09-27'
    cards = [stat_card('Settled through facilitators', usd(S['week_usd']), tip=f'Every USDC transfer on Solana whose fee was paid by one of the 27 published x402 facilitator addresses, week of {week_label(lw)}.'),
             stat_card('After the single-buyer filter', usd(S['week_after_single_buyer']), tip='Removes sellers paid by only one distinct buyer in the week, as on Base.'),
             stat_card('Without the largest seller', usd(S['week_ex_whale']), tip=f'One seller received {usd(wh["usd"])} in {wh["payments"]} payments, {pct(wh["top_buyer_share"])} of it from a single buyer: a large transfer routed through a facilitator, not purchases.'),
             stat_card('Sellers with 5+ buyers', num(S['sellers_5plus']), foot=f'of {num(len(S["sellers"]))} paid in the week'),
             stat_card('Peak month', usd(S['peak_month_usd']), foot=_dt.date.fromisoformat(S['peak_month'] + '-01').strftime('%B %Y'))]
    hs = S['history']
    pm = _dt.date.fromisoformat(S['peak_month'] + '-01').strftime('%B %Y')
    out = [freshness(through, 'from Dune · refreshed by hand'), kpis(cards),
           chart_frame('history', f'x402 on Solana peaked at {usd(S["peak_month_usd"])} in {pm}; last week it settled {usd(S["week_usd"])}, and {usd(S["week_ex_whale"])} without one transfer',
                       f'Every USDC transfer paid for by a known x402 facilitator, per week since launch ({len(hs)} weeks). Log scale. The single-buyer filter is shown for the five weeks it was computed.',
                       'history', '/x402/data/solana_history.json', {'index_weeks': []}, csv='/x402/data/solana_weekly.csv', through=through, page='/x402/solana/',
                       note=f'Source: Dune, <a href="{QUERIES}2_x402_solana_history.sql">2_x402_solana_history.sql</a>. PayAI, once the largest facilitator here, fell from {num(S["payai_before"])} payments on 7 Sep 2026 to about {num(S["payai_after_median"])} a day from 9 Sep.'),
           chart_frame('facilitators', f'{S["facilitators"][0]["facilitator"].title()} settled {pct(S["facilitators"][0]["share"])} of Solana x402 dollars in the week of {week_label(lw)}',
                       f'Share of settled USD by facilitator. Denominator: {usd(S["week_usd"])}.',
                       'bars', '/x402/data/solana_charts.json', {'path': 'fac', 'label': 'label', 'value': 'value', 'pct': True, 'labelName': 'Facilitator', 'valueName': 'Share of USD'},
                       csv='/x402/data/solana_weekly_by_facilitator.csv', through=through, page='/x402/solana/')]
    rows = [{**s, 'seller': f'<code>{esc(s["payee"][:6])}…{esc(s["payee"][-4:])}</code>', 'seller_t': s['payee'], 'seller_s': s['payee']} for s in S['sellers']]
    cols = [{'k': 'seller', 'label': 'Seller', 't': 'html'}, {'k': 'facilitator', 'label': 'Facilitator'}, {'k': 'usd', 'label': 'USD', 't': 'usd', 'r': 1},
            {'k': 'payments', 'label': 'Payments', 't': 'int', 'r': 1}, {'k': 'median_usd', 'label': 'Median', 't': 'price', 'r': 1},
            {'k': 'buyers', 'label': 'Buyers', 't': 'int', 'r': 1}, {'k': 'repeat_buyers', 'label': 'Repeat buyers', 't': 'int', 'r': 1}, {'k': 'top_buyer_share', 'label': 'Top-buyer share', 't': 'pct', 'r': 1}]
    out.append(f'<h2 id="sellers">Sellers, week of {week_label(lw)}</h2><p>Every Solana address paid through a known facilitator that week. The largest received {usd(wh["usd"])} in {wh["payments"]} payments, almost all from one buyer; the next largest took {usd(S["sellers"][1]["usd"])}.</p>'
               + data_table('solana-sellers', cols, rows, sort='usd', page_size=25, placeholder='Search address', csv_name='solana_sellers.csv', search=['seller_t', 'facilitator']))
    out.append(f'''<h2 id="method">How this differs from Base</h2><ul class="meta-list">
<li><b>Same definition, other chain.</b> A settlement is a USDC transfer whose transaction fee was paid by one of the 27 published x402 facilitator addresses (x402's Solana scheme has the facilitator pay the fee). Queries: <a href="{QUERIES}">analytics/dune</a>.</li>
<li><b>Lighter cleaning.</b> Only the single-buyer filter is applied. A first look at funding found no large shared-funding clusters: {S["funders_10plus"]} wallets funded 10 or more buyers, behind {usd(S["funders_10plus_usd"])} in all.</li>
<li><b>Coverage.</b> {S["unlisted_candidates"]} fee payers outside the published list move x402-sized payments, but none can be confirmed (the Bazaar lists no Solana addresses), so they are not counted.</li>
<li><b>Refreshed by hand</b> from Dune, not weekly like the Base index.</li></ul>''')
    open(os.path.join(GEN, 'solana.md'), 'w').write(md('\n'.join(out)))


def build(d):
    solana_page(d)
